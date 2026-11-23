from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
import re
import zipfile

from datetime import datetime
from app.models.plagiarism_check import PlagiarismCheck
from app.services.plagiarism_service import check_paper_similarity

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from docx import Document
from pypdf import PdfReader

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

from app.database import get_db
from app.models.analysis_report import AnalysisReport
from app.models.research_paper import ResearchPaper
from app.services.groq_service import analyze_research_paper
from app.services.session_service import get_current_user

import traceback

router = APIRouter(tags=["Research Papers"])

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(
    directory=BASE_DIR / "app" / "templates"
)

MAX_FILE_SIZE = 15 * 1024 * 1024

SECTION_HEADINGS = {
    "abstract",
    "introduction",
    "related work",
    "literature review",
    "background",
    "methodology",
    "research methodology",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "references",
    "bibliography",
    "acknowledgements",
    "acknowledgments",
    "appendix",
}


def extract_pdf_text(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    text_parts = []

    for page in reader.pages:
        text_parts.append(page.extract_text() or "")

    return "\n".join(text_parts)


def extract_docx_text(file_path: Path) -> str:
    document = Document(str(file_path))

    paragraphs = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n".join(paragraphs)


def clean_metadata_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_paper_metadata(
    extracted_text: str,
    page_count: int = None,
) -> dict:
    lines = [
        line.strip()
        for line in extracted_text.splitlines()
        if line.strip()
    ]

    if not lines:
        return {
            "paper_title": None,
            "abstract": None,
            "keywords": None,
            "references_text": None,
            "page_count": page_count,
            "word_count": 0,
        }

    paper_title = None
    abstract = None
    keywords = None
    references_text = None

    ignored_title_lines = {
        "research paper",
        "original research article",
        "article",
        "abstract",
        "introduction",
    }

    for line in lines[:10]:
        cleaned = clean_metadata_text(line)

        if (
            cleaned.lower() not in ignored_title_lines
            and len(cleaned) >= 5
            and not cleaned.lower().startswith(
                ("doi:", "https://", "http://", "www.")
            )
        ):
            paper_title = cleaned[:500]
            break

    def get_section(section_names):
        start_index = None
        content = []

        for index, line in enumerate(lines):
            normalized = re.sub(
                r"^\d+(\.\d+)*\.?\s*",
                "",
                line.lower().strip(),
            ).strip(" :.-")

            for section_name in section_names:
                if normalized == section_name:
                    start_index = index + 1
                    break

                prefix = section_name + ":"
                if line.lower().startswith(prefix):
                    content.append(line[len(prefix):].strip())
                    start_index = index + 1
                    break

            if start_index is not None:
                break

        if start_index is None:
            return None

        for line in lines[start_index:]:
            normalized = re.sub(
                r"^\d+(\.\d+)*\.?\s*",
                "",
                line.lower().strip(),
            ).strip(" :.-")

            if normalized in SECTION_HEADINGS:
                break

            content.append(line)

        result = clean_metadata_text(" ".join(content))
        return result or None

    abstract = get_section({"abstract"})

    for index, line in enumerate(lines):
        match = re.match(
            r"^(?:keywords?|index terms)\s*:\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )

        if match:
            keyword_parts = [match.group(1)]

            for following_line in lines[index + 1:]:
                normalized = following_line.lower().strip(" :.-")

                if normalized in SECTION_HEADINGS:
                    break

                if len(" ".join(keyword_parts)) > 1000:
                    break

                keyword_parts.append(following_line)

            keywords = clean_metadata_text(" ".join(keyword_parts))
            break

    if not keywords:
        keywords = get_section({"keywords", "index terms"})

    references_text = get_section({"references", "bibliography"})

    word_count = len(
        re.findall(r"\b[\w'-]+\b", extracted_text)
    )

    return {
        "paper_title": paper_title,
        "abstract": abstract,
        "keywords": keywords,
        "references_text": references_text,
        "page_count": page_count,
        "word_count": word_count,
    }


def safe_issue_list(value) -> list:
    if not isinstance(value, list):
        return []

    cleaned_issues = []

    for item in value:
        if not isinstance(item, dict):
            continue

        issue = {
            "original_text": str(item.get("original_text") or "").strip(),
            "issue": str(item.get("issue") or "").strip(),
            "explanation": str(item.get("explanation") or "").strip(),
            "suggestion": str(item.get("suggestion") or "").strip(),
        }

        if any(issue.values()):
            cleaned_issues.append(issue)

    return cleaned_issues


def safe_text_list(value) -> list:
    if not isinstance(value, list):
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    return [
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    ]


def safe_section_analysis(value) -> list:
    if not isinstance(value, list):
        return []

    sections = []

    for item in value:
        if not isinstance(item, dict):
            continue

        section = {
            "section": str(item.get("section") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "observation": str(item.get("observation") or "").strip(),
        }

        if any(section.values()):
            sections.append(section)

    return sections


def parse_manual_keywords(value: str) -> list:
    if not value or not value.strip():
        return []

    keywords = []
    seen = set()

    for keyword in value.split(","):
        cleaned = keyword.strip()

        if not cleaned:
            continue

        normalized = cleaned.casefold()

        if normalized not in seen:
            keywords.append(cleaned)
            seen.add(normalized)

    return keywords

def safe_keyword_list(value) -> list:
    if not value:
        return []

    if isinstance(value, str):
        items = re.split(r"[,;\n]+", value)
    elif isinstance(value, list):
        items = value
    else:
        return []

    keywords = []
    seen = set()

    for item in items:
        cleaned = str(item).strip()

        if not cleaned:
            continue

        normalized = cleaned.casefold()

        if normalized not in seen:
            keywords.append(cleaned)
            seen.add(normalized)

    return keywords

@router.get("/history")
def history_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    search = request.query_params.get("search", "").strip()
    quality = request.query_params.get("quality", "").strip().lower()
    sort = request.query_params.get("sort", "newest").strip().lower()

    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1

    per_page = 10

    query = (
        db.query(AnalysisReport, ResearchPaper)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .filter(
            AnalysisReport.user_id == current_user.id,
            ResearchPaper.user_id == current_user.id,
        )
    )

    if search:
        query = query.filter(
            ResearchPaper.original_filename.ilike(f"%{search}%")
        )

    if quality == "excellent":
        query = query.filter(AnalysisReport.overall_score >= 80)
    elif quality == "good":
        query = query.filter(
            AnalysisReport.overall_score >= 60,
            AnalysisReport.overall_score < 80,
        )
    elif quality == "low":
        query = query.filter(AnalysisReport.overall_score < 60)
    elif quality == "unscored":
        query = query.filter(
            AnalysisReport.overall_score.is_(None)
        )

    total_reports = query.count()
    total_pages = max(
        1,
        (total_reports + per_page - 1) // per_page,
    )
    page = min(page, total_pages)

    if sort == "oldest":
        query = query.order_by(
            AnalysisReport.created_at.asc(),
            AnalysisReport.id.asc(),
        )
    else:
        sort = "newest"
        query = query.order_by(
            AnalysisReport.created_at.desc(),
            AnalysisReport.id.desc(),
        )

    history_rows = (
        query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    history_reports = [
        {"report": report, "paper": paper}
        for report, paper in history_rows
    ]

    average_score = (
        db.query(func.avg(AnalysisReport.overall_score))
        .filter(
            AnalysisReport.user_id == current_user.id,
            AnalysisReport.overall_score.isnot(None),
        )
        .scalar()
    )

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "history_reports": history_reports,
            "total_reports": total_reports,
            "average_score": (
                round(float(average_score), 1)
                if average_score is not None else None
            ),
            "search": search,
            "quality": quality,
            "sort": sort,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/upload")
def upload_page(
    request: Request,
    current_user=Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
        },
    )

@router.post("/upload")
async def upload_research_paper(
    request: Request,
    file: UploadFile = File(...),
    manual_keywords: str = Form(default=""),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_filename = Path(file.filename or "").name

    if not original_filename:
        raise HTTPException(
            status_code=400,
            detail="Please select a file to upload.",
        )

    extension = Path(original_filename).suffix.lower()

    if extension not in {".pdf", ".docx"}:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    stored_filename = f"{uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / stored_filename
    file_size = 0

    try:
        with file_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File size must not exceed 15 MB.",
                    )

                destination.write(chunk)

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        if extension == ".pdf":
            with file_path.open("rb") as uploaded_file:
                if not uploaded_file.read(5).startswith(b"%PDF-"):
                    raise HTTPException(
                        status_code=400,
                        detail="The uploaded file is not a valid PDF.",
                    )

            pdf_reader = PdfReader(str(file_path))
            page_count = len(pdf_reader.pages)
            extracted_text = "\n".join(
                page.extract_text() or ""
                for page in pdf_reader.pages
            )
        else:
            if not zipfile.is_zipfile(file_path):
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded file is not a valid DOCX document.",
                )

            extracted_text = extract_docx_text(file_path)
            page_count = None

        metadata = extract_paper_metadata(
            extracted_text,
            page_count=page_count,
        )

        entered_keywords = parse_manual_keywords(manual_keywords)

        if entered_keywords:
            paper_keywords = ", ".join(entered_keywords)
        else:
            paper_keywords = metadata["keywords"]

        paper = ResearchPaper(
            user_id=current_user.id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            file_type=extension.lstrip("."),
            file_size=file_size,
            processing_status="extracted",
            extracted_text=extracted_text,
            paper_title=metadata["paper_title"],
            abstract=metadata["abstract"],
            keywords=paper_keywords,
            references_text=metadata["references_text"],
            page_count=metadata["page_count"],
            word_count=metadata["word_count"],
        )

        db.add(paper)
        db.commit()
        db.refresh(paper)

        return templates.TemplateResponse(
            request=request,
            name="upload.html",
            context={
                "app_name": "ResearchLens",
                "current_user": current_user,
                "success_message": (
                    f"{original_filename} uploaded successfully. "
                    "Document text has been extracted."
                ),
            },
        )

    except HTTPException:
        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise

    except Exception:
        db.rollback()

        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to process this document. "
                "Please check the file and try again."
            ),
        )

    finally:
        await file.close()


@router.get("/my-papers")
def my_papers_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    papers = (
        db.query(ResearchPaper)
        .filter(ResearchPaper.user_id == current_user.id)
        .order_by(ResearchPaper.uploaded_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="my_papers.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "papers": papers,
        },
    )


@router.get("/reports")
def reports_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    reports = (
        db.query(AnalysisReport, ResearchPaper)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .filter(
            AnalysisReport.user_id == current_user.id,
            ResearchPaper.user_id == current_user.id,
        )
        .order_by(AnalysisReport.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "reports": reports,
        },
    )

@router.post("/analyze/{paper_id}")
def analyze_paper(
    paper_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    paper = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    if not paper.extracted_text or not paper.extracted_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No extracted text is available for this paper.",
        )

    try:
        matching_reports = []
        if not force:
            matching_reports = (
                db.query(AnalysisReport)
                .join(
                    ResearchPaper,
                    AnalysisReport.paper_id == ResearchPaper.id,
                )
                .filter(
                    AnalysisReport.user_id == current_user.id,
                    ResearchPaper.user_id == current_user.id,
                    ResearchPaper.extracted_text == paper.extracted_text,
                    ResearchPaper.keywords == paper.keywords,
                )
                .order_by(
                    AnalysisReport.created_at.desc(),
                    AnalysisReport.id.desc(),
                )
                .all()
            )
        required_analysis_fields = [
            "paper_summary",
            "keywords",
            "grammar_issues",
            "spelling_issues",
            "clarity_issues",
            "writing_tips",
            "citation_summary",
            "citation_issues",
            "missing_references",
            "uncited_references",
            "citation_format_issues",
            "structure_summary",
            "detected_sections",
            "section_analysis",
            "formatting_issues",
        ]


        canonical_report = None

        for candidate in matching_reports:
            if all(
                getattr(candidate, field, None) is not None
                for field in required_analysis_fields
            ):
                canonical_report = candidate
                break

        report_fields = [
            "summary",
            "paper_summary",
            "methodology",
            "findings",
            "limitations",
            "future_work",
            "overall_score",
            "structure_score",
            "writing_score",
            "methodology_score",
            "abstract_score",
            "conclusion_score",
            "references_score",
            "structure_feedback",
            "structure_summary",
            "detected_sections",
            "section_analysis",
            "formatting_issues",
            "writing_feedback",
            "methodology_feedback",
            "abstract_feedback",
            "conclusion_feedback",
            "references_feedback",
            "strengths",
            "weaknesses",
            "missing_sections",
            "recommendations",
            "keywords",
            "grammar_issues",
            "spelling_issues",
            "clarity_issues",
            "writing_tips",
            "citation_summary",
            "citation_issues",
            "missing_references",
            "uncited_references",
            "citation_format_issues",
        ]

        if canonical_report:
            existing_report = next(
                (
                    report
                    for report in matching_reports
                    if report.paper_id == paper.id
                ),
                None,
            )

            if existing_report:
                if existing_report.id != canonical_report.id:
                    for field in report_fields:
                        setattr(
                            existing_report,
                            field,
                            getattr(canonical_report, field),
                        )

                    db.commit()
                    db.refresh(existing_report)

                return RedirectResponse(
                    url=f"/report/{existing_report.id}",
                    status_code=303,
                )

            reused_report = AnalysisReport(
                paper_id=paper.id,
                user_id=current_user.id,
                **{
                    field: getattr(canonical_report, field)
                    for field in report_fields
                },
            )

            db.add(reused_report)
            db.commit()
            db.refresh(reused_report)

            return RedirectResponse(
                url=f"/report/{reused_report.id}",
                status_code=303,
            )

        result = analyze_research_paper(
            paper.extracted_text,
            references_text=paper.references_text,
            )

        
        report = AnalysisReport(
            paper_id=paper.id,
            user_id=current_user.id,
            summary=result.get("summary"),
            paper_summary=result.get("paper_summary"),
            methodology=None,
            findings=None,
            limitations=None,
            future_work=None,
            overall_score=result.get("overall_score"),
            structure_score=result.get("structure_score"),
            writing_score=result.get("writing_score"),
            methodology_score=result.get("methodology_score"),
            abstract_score=result.get("abstract_score"),
            conclusion_score=result.get("conclusion_score"),
            references_score=result.get("references_score"),
            structure_feedback=result.get("structure_feedback"),
            structure_summary=result.get("structure_summary"),
            detected_sections=safe_text_list(
                result.get("detected_sections")
            ),
            section_analysis=safe_section_analysis(
                result.get("section_analysis")
            ),

            formatting_issues=safe_text_list(
                result.get("formatting_issues")
            ),
            writing_feedback=result.get("writing_feedback"),
            methodology_feedback=result.get("methodology_feedback"),
            abstract_feedback=result.get("abstract_feedback"),
            conclusion_feedback=result.get("conclusion_feedback"),
            references_feedback=result.get("references_feedback"),
            strengths=safe_text_list(result.get("strengths")),
            weaknesses=safe_text_list(result.get("weaknesses")),
            missing_sections=safe_text_list(
                result.get("missing_sections")
            ),
            recommendations=safe_text_list(
                result.get("recommendations")
            ),
            keywords=(
                parse_manual_keywords(paper.keywords)
                if paper.keywords and paper.keywords.strip()
                else safe_keyword_list(result.get("keywords"))
            ),
            grammar_issues=safe_issue_list(
                result.get("grammar_issues")
            ),
            spelling_issues=safe_issue_list(
                result.get("spelling_issues")
            ),
            clarity_issues=safe_issue_list(
                result.get("clarity_issues")
            ),
            writing_tips=safe_text_list(
                result.get("writing_tips")
            ),
            citation_summary=result.get("citation_summary"),
            citation_issues=safe_issue_list(
                result.get("citation_issues")
            ),
            missing_references=safe_text_list(
                result.get("missing_references")
            ),
            uncited_references=safe_text_list(
                result.get("uncited_references")
            ),
            citation_format_issues=safe_text_list(
                result.get("citation_format_issues")
            ),
        )


        db.add(report)
        db.commit()
        db.refresh(report)

        return RedirectResponse(
            url=f"/report/{report.id}",
            status_code=303,
        )

    except ValueError as exc:
        db.rollback()
        print("ANALYSIS VALUE ERROR:", str(exc))
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        print("ANALYSIS UNEXPECTED ERROR:", str(exc))
        traceback.print_exc()
        raise HTTPException(
           status_code=500,
           detail="Unable to analyze this paper. Please check the server terminal.",
        )

@router.post("/plagiarism/check/{paper_id}")
def run_plagiarism_check(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    paper = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    if not paper.extracted_text or len(paper.extracted_text.split()) < 30:
        raise HTTPException(
            status_code=400,
            detail="The paper does not contain enough extracted text.",
        )

    latest_report = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.paper_id == paper.id,
            AnalysisReport.user_id == current_user.id,
        )
        .order_by(
            AnalysisReport.created_at.desc(),
            AnalysisReport.id.desc(),
        )
        .first()
    )

    if not latest_report:
        raise HTTPException(
            status_code=400,
            detail="Please analyze this paper before checking similarity.",
        )

    plagiarism_check = PlagiarismCheck(
        paper_id=paper.id,
        user_id=current_user.id,
        status="pending",
    )

    db.add(plagiarism_check)
    db.commit()
    db.refresh(plagiarism_check)

    check_id = plagiarism_check.id

    try:
        result = check_paper_similarity(
            paper_text=paper.extracted_text,
            title=paper.paper_title,
            abstract=paper.abstract,
            keywords=safe_keyword_list(paper.keywords),
        )

        plagiarism_check.status = "completed"
        plagiarism_check.similarity_score = result.get("similarity_score")
        plagiarism_check.plagiarism_summary = result.get("plagiarism_summary")
        plagiarism_check.similarity_sources = result.get("similarity_sources")
        plagiarism_check.matched_passages = result.get("matched_passages")
        plagiarism_check.error_message = None
        plagiarism_check.checked_at = datetime.now()

        db.commit()

    except Exception as exc:
        db.rollback()

        failed_check = (
            db.query(PlagiarismCheck)
            .filter(
                PlagiarismCheck.id == check_id,
                PlagiarismCheck.user_id == current_user.id,
            )
            .first()
        )

        if failed_check:
            failed_check.status = "failed"
            failed_check.error_message = str(exc)[:2000]
            failed_check.checked_at = datetime.now()
            db.commit()

        traceback.print_exc()

    return RedirectResponse(
        url=f"/report/{latest_report.id}",
        status_code=303,
    )

@router.get("/report/{report_id}")
def view_analysis_report(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    report = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.id == report_id,
            AnalysisReport.user_id == current_user.id,
        )
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Analysis report not found.",
        )

    paper = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == report.paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    plagiarism_check = (
        db.query(PlagiarismCheck)
        .filter(
            PlagiarismCheck.paper_id == paper.id,
            PlagiarismCheck.user_id == current_user.id,
        )
        .order_by(
            PlagiarismCheck.created_at.desc(),
            PlagiarismCheck.id.desc(),
        )
        .first()
    )

    return templates.TemplateResponse(
        request=request,
        name="analysis_report.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "report": report,
            "paper": paper,
            "plagiarism_check": plagiarism_check,
        },
    )


@router.get("/reports/compare")
def compare_analysis_reports(
    request: Request,
    report_id_1: int,
    report_id_2: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if report_id_1 == report_id_2:
        raise HTTPException(
            status_code=400,
            detail="Please select two different reports.",
        )

    report_a = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.id == report_id_1,
            AnalysisReport.user_id == current_user.id,
        )
        .first()
    )

    report_b = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.id == report_id_2,
            AnalysisReport.user_id == current_user.id,
        )
        .first()
    )

    if not report_a or not report_b:
        raise HTTPException(
            status_code=404,
            detail="One or both analysis reports were not found.",
        )

    paper_a = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == report_a.paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    paper_b = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == report_b.paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    if not paper_a or not paper_b:
        raise HTTPException(
            status_code=404,
            detail="One or both research papers were not found.",
        )

    score_fields = [
        ("Overall Quality", "overall_score"),
        ("Structure & Organization", "structure_score"),
        ("Writing Quality", "writing_score"),
        ("Methodology", "methodology_score"),
        ("Abstract Quality", "abstract_score"),
        ("Conclusion Quality", "conclusion_score"),
        ("References & Citations", "references_score"),
    ]

    comparisons = []

    for label, field in score_fields:
        score_a = getattr(report_a, field)
        score_b = getattr(report_b, field)

        difference = None
        if score_a is not None and score_b is not None:
            difference = score_b - score_a

        comparisons.append(
            {
                "label": label,
                "score_a": score_a,
                "score_b": score_b,
                "difference": difference,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="compare_reports.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "report_a": report_a,
            "report_b": report_b,
            "paper_a": paper_a,
            "paper_b": paper_b,
            "comparisons": comparisons,
        },
    )

def pdf_text(value):
    if value is None:
        return ""

    text = str(value)

    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2026": "...",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return escape(text)

def pdf_list(value) -> list:
    if not value:
        return []

    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        result = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                continue
            item_text = str(item).strip()
            if item_text:
                result.append(item_text)
        return result

    return []


def append_writing_issue_section(
    story: list,
    section_title: str,
    issues,
    styles,
):
    story.append(
        Paragraph(
            pdf_text(section_title),
            styles["SectionHeading"],
        )
    )

    cleaned_issues = safe_issue_list(issues)

    if not cleaned_issues:
        story.append(
            Paragraph(
                "No issues identified.",
                styles["BodyTextCustom"],
            )
        )
        return

    for index, issue in enumerate(cleaned_issues, start=1):
        story.append(
            Paragraph(
                f"<b>{index}. Original text:</b> "
                f"{pdf_text(issue['original_text'] or 'Not provided')}",
                styles["BodyTextCustom"],
            )
        )

        if issue["issue"]:
            story.append(
                Paragraph(
                    f"<b>Issue:</b> {pdf_text(issue['issue'])}",
                    styles["BodyTextCustom"],
                )
            )

        if issue["explanation"]:
            story.append(
                Paragraph(
                    f"<b>Explanation:</b> {pdf_text(issue['explanation'])}",
                    styles["BodyTextCustom"],
                )
            )

        if issue["suggestion"]:
            story.append(
                Paragraph(
                    f"<b>Suggested correction:</b> "
                    f"{pdf_text(issue['suggestion'])}",
                    styles["BodyTextCustom"],
                )
            )

        story.append(Spacer(1, 2 * mm))


@router.get("/report/{report_id}/download")
def download_analysis_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    report = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.id == report_id,
            AnalysisReport.user_id == current_user.id,
        )
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Analysis report not found.",
        )

    paper = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.id == report.paper_id,
            ResearchPaper.user_id == current_user.id,
        )
        .first()
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="ResearchLens Quality Assessment Report",
        author="ResearchLens",
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#172b4d"),
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=12,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=19,
            textColor=colors.HexColor("#172b4d"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="BodyTextCustom",
            parent=styles["BodyText"],
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ScoreText",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0f766e"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="SmallText",
            parent=styles["Normal"],
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#64748b"),
        )
    )

    story = []

    story.append(
        Paragraph(
            "ResearchLens",
            ParagraphStyle(
                "Brand",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=12,
                textColor=colors.HexColor("#0f766e"),
            ),
        )
    )

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "Research Paper Quality Assessment",
            styles["ReportTitle"],
        )
    )

    story.append(
        Paragraph(
            pdf_text(paper.original_filename),
            styles["ReportSubtitle"],
        )
    )

    story.append(
        Paragraph(
            f"Report ID: {report.id}",
            styles["SmallText"],
        )
    )

    generated_date = (
        report.created_at.strftime("%d %b %Y, %I:%M %p")
        if report.created_at else "Not available"
    )

    story.append(
        Paragraph(
            f"Generated on: {pdf_text(generated_date)}",
            styles["SmallText"],
        )
    )

    story.append(Spacer(1, 8 * mm))

    overall_score = (
        report.overall_score
        if report.overall_score is not None
        else 0
    )

    overall_data = [
        [
            Paragraph(
                f"<b>{overall_score}/100</b>",
                ParagraphStyle(
                    "OverallScore",
                    parent=styles["Normal"],
                    fontSize=24,
                    leading=30,
                    textColor=colors.HexColor("#0f766e"),
                    alignment=TA_CENTER,
                ),
            ),
            Paragraph(
                "<b>Overall Paper Quality</b><br/><br/>"
                + pdf_text(report.summary),
                styles["BodyTextCustom"],
            ),
        ]
    ]

    overall_table = Table(
        overall_data,
        colWidths=[40 * mm, 130 * mm],
    )

    overall_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#f1f8f7"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.HexColor("#d5e8e5"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    story.append(overall_table)

    story.append(
        Paragraph(
            "Research Paper Summary",
            styles["SectionHeading"],
        )
    )

    story.append(
        Paragraph(
            pdf_text(report.paper_summary),
            styles["BodyTextCustom"],
        )
    )

    story.append(
        Paragraph(
            "Research Keywords",
            styles["SectionHeading"],
        )
    )

    keyword_text = ", ".join(pdf_list(report.keywords))

    story.append(
        Paragraph(
            pdf_text(keyword_text or "No keywords available."),
            styles["BodyTextCustom"],
        )
    )

    story.append(
        Paragraph(
            "Evaluation Scores",
            styles["SectionHeading"],
        )
    )

    score_items = [
        (
            "Structure & Organization",
            report.structure_score,
            report.structure_feedback,
        ),
        (
            "Writing Quality",
            report.writing_score,
            report.writing_feedback,
        ),
        (
            "Methodology",
            report.methodology_score,
            report.methodology_feedback,
        ),
        (
            "Abstract Quality",
            report.abstract_score,
            report.abstract_feedback,
        ),
        (
            "Conclusion Quality",
            report.conclusion_score,
            report.conclusion_feedback,
        ),
        (
            "References & Citations",
            report.references_score,
            report.references_feedback,
        ),
    ]

    score_data = [
        [
            Paragraph("<b>Category</b>", styles["BodyTextCustom"]),
            Paragraph("<b>Score</b>", styles["BodyTextCustom"]),
            Paragraph(
                "<b>AI Evaluation Feedback</b>",
                styles["BodyTextCustom"],
            ),
        ]
    ]

    for label, score, feedback in score_items:
        score_display = (
            f"{score}/100"
            if score is not None
            else "Not evaluated"
        )

        score_data.append(
            [
                Paragraph(pdf_text(label), styles["BodyTextCustom"]),
                Paragraph(
                    pdf_text(score_display),
                    styles["ScoreText"],
                ),
                Paragraph(
                    pdf_text(feedback),
                    styles["BodyTextCustom"],
                ),
            ]
        )

    score_table = Table(
        score_data,
        colWidths=[42 * mm, 25 * mm, 103 * mm],
        repeatRows=1,
    )

    score_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#172b4d"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#f8fafc"),
                    ],
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#e2e8f0"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.append(score_table)

    story.append(
        Paragraph(
            "Research Structure & Formatting Analysis",
            styles["SectionHeading"],
        )
    )

    if report.structure_summary:
        story.append(
            Paragraph(
                "Structure Summary",
                styles["ScoreText"],
            )
        )

        story.append(
            Paragraph(
                pdf_text(report.structure_summary),
                styles["BodyTextCustom"],
            )
        )

    detected_sections = pdf_list(report.detected_sections)

    story.append(
        Paragraph(
            "Detected Sections",
            styles["ScoreText"],
        )
    )

    if detected_sections:
        story.append(
            Paragraph(
                pdf_text(", ".join(detected_sections)),
                styles["BodyTextCustom"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No detected sections available.",
                styles["BodyTextCustom"],
            )
        )

    story.append(
        Paragraph(
            "Section-by-Section Analysis",
            styles["ScoreText"],
        )
    )

    section_analysis = (
        report.section_analysis
        if isinstance(report.section_analysis, list)
        else []
    )

    if section_analysis:
        section_data = [
            [
                Paragraph("<b>Section</b>", styles["BodyTextCustom"]),
                Paragraph("<b>Status</b>", styles["BodyTextCustom"]),
                Paragraph("<b>Observation</b>", styles["BodyTextCustom"]),
            ]
        ]

        for item in section_analysis:
            if not isinstance(item, dict):
                continue

            section_data.append(
                [
                    Paragraph(
                        pdf_text(item.get("section") or "Not specified"),
                        styles["BodyTextCustom"],
                    ),
                    Paragraph(
                        pdf_text(item.get("status") or "Not specified"),
                        styles["BodyTextCustom"],
                    ),
                    Paragraph(
                        pdf_text(item.get("observation") or "No observation available."),
                        styles["BodyTextCustom"],
                    ),
                ]
            )

        if len(section_data) > 1:
            section_table = Table(
                section_data,
                colWidths=[38 * mm, 30 * mm, 102 * mm],
                repeatRows=1,
            )

            section_table.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.HexColor("#172b4d"),
                        ),
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.white,
                        ),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [
                                colors.white,
                                colors.HexColor("#f8fafc"),
                            ],
                        ),
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            0.5,
                            colors.HexColor("#e2e8f0"),
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )

            story.append(section_table)
    else:
        story.append(
            Paragraph(
                "No section-by-section analysis available.",
                styles["BodyTextCustom"],
            )
        )

    story.append(
        Paragraph(
            "Formatting Issues",
            styles["ScoreText"],
        )
    )

    formatting_issues = pdf_list(report.formatting_issues)

    if formatting_issues:
        for issue in formatting_issues:
            story.append(
                Paragraph(
                    f"&bull; {pdf_text(issue)}",
                    styles["BodyTextCustom"],
                )
            )
    else:
        story.append(
            Paragraph(
                "No specific formatting issues were identified.",
                styles["BodyTextCustom"],
            )
        )

    story.append(
        Paragraph(
            "Citation & Reference Analysis",
            styles["SectionHeading"],
        )
    )

    if report.citation_summary:
        story.append(
            Paragraph(
                pdf_text(report.citation_summary),
                styles["BodyTextCustom"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No citation analysis summary available.",
                styles["BodyTextCustom"],
            )
        )

    append_writing_issue_section(
        story,
        "Citation Issues",
        report.citation_issues,
        styles,
    )

    citation_sections = [
        ("Missing References", report.missing_references),
        ("Uncited References", report.uncited_references),
        ("Citation Formatting Issues", report.citation_format_issues),
    ]

    for section_title, section_items in citation_sections:
        story.append(
            Paragraph(
                pdf_text(section_title),
                styles["ScoreText"],
            )
        )

        items = pdf_list(section_items)

        if items:
            for item in items:
                story.append(
                    Paragraph(
                        f"&bull; {pdf_text(item)}",
                        styles["BodyTextCustom"],
                    )
                )
        else:
            story.append(
                Paragraph(
                    "No issues identified.",
                    styles["BodyTextCustom"],
                )
            )

    story.append(
        Paragraph(
            "Note: Citation analysis checks citation consistency and "
            "does not perform plagiarism detection. Please manually verify "
            "the suggested corrections and reference matches.",
            styles["SmallText"],
        )
    )

    plagiarism_check = (
        db.query(PlagiarismCheck)
        .filter(
            PlagiarismCheck.paper_id == paper.id,
            PlagiarismCheck.user_id == current_user.id,
            PlagiarismCheck.status == "completed",
        )
        .order_by(
            PlagiarismCheck.created_at.desc(),
            PlagiarismCheck.id.desc(),
        )
        .first()
    )

    story.append(
        Paragraph(
            "Plagiarism & Similarity Analysis",
            styles["SectionHeading"],
        )
    )

    if plagiarism_check:
        similarity_score = plagiarism_check.similarity_score

        score_display = (
            f"{similarity_score:.2f}%"
            if similarity_score is not None
            else "Not available"
        )

        story.append(
            Paragraph(
                f"<b>Similarity indicator:</b> {pdf_text(score_display)}",
                styles["ScoreText"],
            )
        )

        if plagiarism_check.checked_at:
            checked_date = plagiarism_check.checked_at.strftime(
                "%d %b %Y, %I:%M %p"
            )

            story.append(
                Paragraph(
                    f"<b>Checked on:</b> {pdf_text(checked_date)}",
                    styles["BodyTextCustom"],
                )
            )

        story.append(
            Paragraph(
                pdf_text(
                    plagiarism_check.plagiarism_summary
                    or "No similarity summary available."
                ),
                styles["BodyTextCustom"],
            )
        )

        similarity_sources = (
            plagiarism_check.similarity_sources
            if isinstance(plagiarism_check.similarity_sources, list)
            else []
        )

        story.append(
            Paragraph(
                "Sources Compared",
                styles["ScoreText"],
            )
        )

        if similarity_sources:
            for index, source in enumerate(similarity_sources, start=1):
                if not isinstance(source, dict):
                    continue

                source_title = (
                    source.get("title")
                    or source.get("source_title")
                    or "Untitled source"
                )

                source_score = source.get(
                    "similarity_score",
                    source.get("similarity", 0),
                )

                try:
                    source_score_text = f"{float(source_score):.2f}%"
                except (TypeError, ValueError):
                    source_score_text = "Not available"

                story.append(
                    Paragraph(
                        f"<b>{index}. {pdf_text(source_title)}</b>",
                        styles["BodyTextCustom"],
                    )
                )

                story.append(
                    Paragraph(
                        f"Similarity indicator: {pdf_text(source_score_text)}",
                        styles["BodyTextCustom"],
                    )
                )

                source_doi = source.get("doi")
                if source_doi:
                    story.append(
                        Paragraph(
                            f"DOI: {pdf_text(source_doi)}",
                            styles["SmallText"],
                        )
                    )
        else:
            story.append(
                Paragraph(
                    "No comparison sources were available.",
                    styles["BodyTextCustom"],
                )
            )

        matched_passages = (
            plagiarism_check.matched_passages
            if isinstance(plagiarism_check.matched_passages, list)
            else []
        )

        story.append(
            Paragraph(
                "Potentially Matching Passages",
                styles["ScoreText"],
            )
        )

        if matched_passages:
            for index, passage in enumerate(matched_passages, start=1):
                if isinstance(passage, dict):
                    passage_text = (
                        passage.get("passage")
                        or passage.get("text")
                        or passage.get("original_text")
                        or ""
                    )

                    source_title = (
                        passage.get("source_title")
                        or passage.get("title")
                        or ""
                    )

                    passage_score = passage.get(
                        "similarity_score",
                        passage.get("similarity"),
                    )

                    story.append(
                        Paragraph(
                            f"<b>{index}. Passage:</b> "
                            f"{pdf_text(passage_text or 'Not provided')}",
                            styles["BodyTextCustom"],
                        )
                    )

                    if source_title:
                        story.append(
                            Paragraph(
                                f"<b>Source:</b> {pdf_text(source_title)}",
                                styles["BodyTextCustom"],
                            )
                        )

                    if passage_score is not None:
                        try:
                            passage_score = f"{float(passage_score):.2f}%"
                        except (TypeError, ValueError):
                            passage_score = str(passage_score)

                        story.append(
                            Paragraph(
                                f"<b>Similarity:</b> {pdf_text(passage_score)}",
                                styles["BodyTextCustom"],
                            )
                        )

                elif isinstance(passage, str):
                    story.append(
                        Paragraph(
                            f"{index}. {pdf_text(passage)}",
                            styles["BodyTextCustom"],
                        )
                    )

        else:
            story.append(
                Paragraph(
                    "No potentially matching passages were identified.",
                    styles["BodyTextCustom"],
                )
            )

    else:
        story.append(
            Paragraph(
                "No completed similarity check is available for this paper.",
                styles["BodyTextCustom"],
            )
        )

    story.append(
        Paragraph(
            "Important: This is an experimental OpenAlex scholarly-source "
            "similarity indicator based on accessible abstracts. It is not "
            "a comprehensive plagiarism scan and cannot prove whether a "
            "paper is original or plagiarized. Results should be reviewed "
            "manually.",
            styles["SmallText"],
        )
    )
    
    story.append(
        Paragraph(
            "Grammar, Spelling & Sentence Clarity",
            styles["SectionHeading"],
        )
    )

    append_writing_issue_section(
        story,
        "Grammar Issues",
        report.grammar_issues,
        styles,
    )

    append_writing_issue_section(
        story,
        "Spelling Issues",
        report.spelling_issues,
        styles,
    )

    append_writing_issue_section(
        story,
        "Sentence Clarity Issues",
        report.clarity_issues,
        styles,
    )

    story.append(
        Paragraph(
            "Academic Writing Improvement Tips",
            styles["SectionHeading"],
        )
    )

    writing_tips = pdf_list(report.writing_tips)

    if writing_tips:
        for tip in writing_tips:
            story.append(
                Paragraph(
                    f"&bull; {pdf_text(tip)}",
                    styles["BodyTextCustom"],
                )
            )
    else:
        story.append(
            Paragraph(
                "No writing tips available.",
                styles["BodyTextCustom"],
            )
        )

    report_sections = [
        ("Strengths", report.strengths),
        ("Weaknesses", report.weaknesses),
        ("Missing or Incomplete Sections", report.missing_sections),
        ("Recommendations", report.recommendations),
    ]

    for section_title, section_items in report_sections:
        story.append(
            Paragraph(
                pdf_text(section_title),
                styles["SectionHeading"],
            )
        )

        items = pdf_list(section_items)

        if not items:
            story.append(
                Paragraph(
                    "No information available.",
                    styles["BodyTextCustom"],
                )
            )
            continue

        for item in items:
            story.append(
                Paragraph(
                    f"&bull; {pdf_text(item)}",
                    styles["BodyTextCustom"],
                )
            )

    story.append(Spacer(1, 5 * mm))

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#e2e8f0"),
        )
    )

    story.append(Spacer(1, 3 * mm))

    story.append(
        Paragraph(
            "Report generated by ResearchLens AI Research Paper Quality Analyzer.",
            styles["SmallText"],
        )
    )

    document.build(story)
    buffer.seek(0)

    safe_filename = re.sub(
        r'[^A-Za-z0-9._-]+',
        "_",
        Path(paper.original_filename).stem,
    ).strip("._")

    if not safe_filename:
        safe_filename = "Research_Paper"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}_ResearchLens_Report.pdf"'
            )
        },
    )
