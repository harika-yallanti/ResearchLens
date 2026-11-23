from pathlib import Path
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.analysis_report import AnalysisReport
from app.models.plagiarism_check import PlagiarismCheck
from app.services.session_service import get_current_admin

BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=BASE_DIR / "templates"
)
UPLOAD_DIR = BASE_DIR.parent / "uploads"

router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
)


@router.get("/dashboard")
def admin_dashboard(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        current_admin = get_current_admin(request, response)

    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse(
                url="/login",
                status_code=303,
            )

        if (
            exc.status_code == 403
            and exc.detail == "Administrator access required."
        ):
            return RedirectResponse(
                url="/dashboard",
                status_code=303,
            )

        raise
    total_users = db.query(User).count()

    total_admins = (
        db.query(User)
        .filter(User.is_admin.is_(True))
        .count()
    )

    total_papers = db.query(ResearchPaper).count()
    total_reports = db.query(AnalysisReport).count()
    total_plagiarism_checks = db.query(PlagiarismCheck).count()

    completed_checks = (
        db.query(PlagiarismCheck)
        .filter(PlagiarismCheck.status == "completed")
        .count()
    )

    failed_checks = (
        db.query(PlagiarismCheck)
        .filter(PlagiarismCheck.status == "failed")
        .count()
    )

    recent_users = (
        db.query(User)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(5)
        .all()
    )

    recent_papers = (
        db.query(ResearchPaper, User)
        .join(User, ResearchPaper.user_id == User.id)
        .order_by(
            ResearchPaper.uploaded_at.desc(),
            ResearchPaper.id.desc(),
        )
        .limit(5)
        .all()
    )

    recent_reports = (
        db.query(AnalysisReport, ResearchPaper, User)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .join(
            User,
            AnalysisReport.user_id == User.id,
        )
        .order_by(
            AnalysisReport.created_at.desc(),
            AnalysisReport.id.desc(),
        )
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "app_name": "ResearchLens Admin",
            "current_admin": current_admin,
            "total_users": total_users,
            "total_admins": total_admins,
            "total_researchers": total_users - total_admins,
            "total_papers": total_papers,
            "total_reports": total_reports,
            "total_plagiarism_checks": total_plagiarism_checks,
            "completed_checks": completed_checks,
            "failed_checks": failed_checks,
            "recent_users": recent_users,
            "recent_papers": recent_papers,
            "recent_reports": recent_reports,
        },
    )


@router.get("/users")
def manage_users(
    request: Request,
    search: str = Query(default=""),
    role: str = Query(default="all"),
    status: str = Query(default="all"),
    sort_by: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    page_size = 10

    query = db.query(User)

    search = search.strip()

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.display_name.ilike(search_term),
                User.email.ilike(search_term),
            )
        )

    if role == "admin":
        query = query.filter(User.is_admin.is_(True))
    elif role == "researcher":
        query = query.filter(User.is_admin.is_(False))
    else:
        role = "all"

    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    else:
        status = "all"

    total_users = db.query(User).count()
    total_filtered = query.count()

    if sort_by == "oldest":
        query = query.order_by(User.created_at.asc(), User.id.asc())
    elif sort_by == "name_asc":
        query = query.order_by(User.display_name.asc(), User.id.asc())
    elif sort_by == "name_desc":
        query = query.order_by(User.display_name.desc(), User.id.desc())
    else:
        sort_by = "newest"
        query = query.order_by(User.created_at.desc(), User.id.desc())

    total_pages = max(1, ceil(total_filtered / page_size))

    if page > total_pages:
        page = total_pages

    users = (
        query
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    start_item = (
        (page - 1) * page_size + 1
        if total_filtered > 0
        else 0
    )

    end_item = min(page * page_size, total_filtered)

    page_numbers = range(
        max(1, page - 2),
        min(total_pages, page + 2) + 1,
    )

    def page_url(page_number):
        return str(
            request.url.include_query_params(page=page_number)
        )

    page_links = [
        {
            "number": number,
            "url": page_url(number),
        }
        for number in page_numbers
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={
            "current_admin": current_admin,
            "users": users,
            "total_users": total_users,
            "total_filtered": total_filtered,
            "search": search,
            "role": role,
            "status": status,
            "sort_by": sort_by,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_item": start_item,
            "end_item": end_item,
            "page_links": page_links,
            "previous_url": page_url(page - 1) if page > 1 else None,
            "next_url": page_url(page + 1) if page < total_pages else None,
        },
    )


@router.get("/papers")
def manage_papers(
    request: Request,
    search: str = Query(default=""),
    status: str = Query(default="all"),
    file_type: str = Query(default="all"),
    sort_by: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    page_size = 10

    query = (
        db.query(ResearchPaper, User)
        .join(User, ResearchPaper.user_id == User.id)
    )

    search = search.strip()

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ResearchPaper.paper_title.ilike(search_term),
                ResearchPaper.original_filename.ilike(search_term),
                User.email.ilike(search_term),
            )
        )

    status_options = [
        value[0]
        for value in (
            db.query(ResearchPaper.processing_status)
            .filter(ResearchPaper.processing_status.isnot(None))
            .distinct()
            .order_by(ResearchPaper.processing_status)
            .all()
        )
    ]

    file_type_options = [
        value[0]
        for value in (
            db.query(ResearchPaper.file_type)
            .filter(ResearchPaper.file_type.isnot(None))
            .distinct()
            .order_by(ResearchPaper.file_type)
            .all()
        )
    ]

    if status != "all" and status in status_options:
        query = query.filter(
            ResearchPaper.processing_status == status
        )
    else:
        status = "all"

    if file_type != "all" and file_type in file_type_options:
        query = query.filter(
            ResearchPaper.file_type == file_type
        )
    else:
        file_type = "all"

    total_papers = db.query(ResearchPaper).count()
    total_filtered = query.count()

    if sort_by == "oldest":
        query = query.order_by(
            ResearchPaper.uploaded_at.asc(),
            ResearchPaper.id.asc(),
        )
    elif sort_by == "title_asc":
        query = query.order_by(
            ResearchPaper.paper_title.asc(),
            ResearchPaper.id.asc(),
        )
    elif sort_by == "title_desc":
        query = query.order_by(
            ResearchPaper.paper_title.desc(),
            ResearchPaper.id.desc(),
        )
    else:
        sort_by = "newest"
        query = query.order_by(
            ResearchPaper.uploaded_at.desc(),
            ResearchPaper.id.desc(),
        )

    total_pages = max(1, ceil(total_filtered / page_size))

    if page > total_pages:
        page = total_pages

    papers = (
        query
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    start_item = (
        (page - 1) * page_size + 1
        if total_filtered > 0
        else 0
    )

    end_item = min(page * page_size, total_filtered)

    page_numbers = range(
        max(1, page - 2),
        min(total_pages, page + 2) + 1,
    )

    def page_url(page_number):
        return str(
            request.url.include_query_params(page=page_number)
        )

    page_links = [
        {
            "number": number,
            "url": page_url(number),
        }
        for number in page_numbers
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/papers.html",
        context={
            "current_admin": current_admin,
            "papers": papers,
            "total_papers": total_papers,
            "total_filtered": total_filtered,
            "search": search,
            "status": status,
            "file_type": file_type,
            "sort_by": sort_by,
            "status_options": status_options,
            "file_type_options": file_type_options,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_item": start_item,
            "end_item": end_item,
            "page_links": page_links,
            "previous_url": page_url(page - 1) if page > 1 else None,
            "next_url": page_url(page + 1) if page < total_pages else None,
        },
    )


@router.get("/analyses")
def manage_analyses(
    request: Request,
    search: str = Query(default=""),
    score_filter: str = Query(default="all"),
    sort_by: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    page_size = 10

    query = (
        db.query(AnalysisReport, ResearchPaper, User)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .join(
            User,
            AnalysisReport.user_id == User.id,
        )
    )

    search = search.strip()

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ResearchPaper.paper_title.ilike(search_term),
                ResearchPaper.original_filename.ilike(search_term),
                User.email.ilike(search_term),
            )
        )

    if score_filter == "excellent":
        query = query.filter(AnalysisReport.overall_score >= 80)
    elif score_filter == "good":
        query = query.filter(
            AnalysisReport.overall_score >= 60,
            AnalysisReport.overall_score < 80,
        )
    elif score_filter == "needs_improvement":
        query = query.filter(AnalysisReport.overall_score < 60)
    elif score_filter == "unavailable":
        query = query.filter(AnalysisReport.overall_score.is_(None))
    else:
        score_filter = "all"

    total_analyses = db.query(AnalysisReport).count()
    total_filtered = query.count()

    if sort_by == "oldest":
        query = query.order_by(
            AnalysisReport.created_at.asc(),
            AnalysisReport.id.asc(),
        )
    elif sort_by == "highest_score":
        query = query.order_by(
            AnalysisReport.overall_score.desc(),
            AnalysisReport.id.desc(),
        )
    else:
        sort_by = "newest"
        query = query.order_by(
            AnalysisReport.created_at.desc(),
            AnalysisReport.id.desc(),
        )

    total_pages = max(1, ceil(total_filtered / page_size))

    if page > total_pages:
        page = total_pages

    analyses = (
        query
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    start_item = (
        (page - 1) * page_size + 1
        if total_filtered > 0
        else 0
    )

    end_item = min(page * page_size, total_filtered)

    page_numbers = range(
        max(1, page - 2),
        min(total_pages, page + 2) + 1,
    )

    def page_url(page_number):
        return str(
            request.url.include_query_params(page=page_number)
        )

    page_links = [
        {
            "number": number,
            "url": page_url(number),
        }
        for number in page_numbers
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/analyses.html",
        context={
            "current_admin": current_admin,
            "analyses": analyses,
            "total_analyses": total_analyses,
            "total_filtered": total_filtered,
            "search": search,
            "score_filter": score_filter,
            "sort_by": sort_by,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "start_item": start_item,
            "end_item": end_item,
            "page_links": page_links,
            "previous_url": page_url(page - 1) if page > 1 else None,
            "next_url": page_url(page + 1) if page < total_pages else None,
        },
    )

@router.get("/analyses/{report_id}")
def analysis_details(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    result = (
        db.query(AnalysisReport, ResearchPaper, User)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .join(
            User,
            AnalysisReport.user_id == User.id,
        )
        .filter(AnalysisReport.id == report_id)
        .first()
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Analysis report not found",
        )

    report, paper, researcher = result

    return templates.TemplateResponse(
        request=request,
        name="admin/analysis_detail.html",
        context={
            "current_admin": current_admin,
            "report": report,
            "paper": paper,
            "researcher": researcher,
        },
    )

@router.get("/users/{user_id}")
def user_details(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/user_detail.html",
        context={
            "current_admin": current_admin,
            "user": user,
        },
    )

@router.get("/papers/{paper_id}")
def paper_details(
    paper_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    paper_data = (
        db.query(ResearchPaper, User)
        .join(User, ResearchPaper.user_id == User.id)
        .filter(ResearchPaper.id == paper_id)
        .first()
    )

    if not paper_data:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    paper, uploader = paper_data
    file_exists = False

    try:
        stored_path = Path(paper.file_path).resolve()
        upload_directory = UPLOAD_DIR.resolve()

        file_exists = (
            stored_path.is_relative_to(upload_directory)
            and stored_path.is_file()
        )
    except (OSError, ValueError, TypeError):
        file_exists = False

    return templates.TemplateResponse(
        request=request,
        name="admin/paper_detail.html",
        context={
            "current_admin": current_admin,
            "paper": paper,
            "uploader": uploader,
            "file_exists": file_exists,
        },
    )


@router.get("/papers/{paper_id}/download")
def download_research_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    paper = (
        db.query(ResearchPaper)
        .filter(ResearchPaper.id == paper_id)
        .first()
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Research paper not found.",
        )

    try:
        stored_path = Path(paper.file_path).resolve()
        upload_directory = UPLOAD_DIR.resolve()

        if (
            not stored_path.is_relative_to(upload_directory)
            or not stored_path.is_file()
        ):
            raise HTTPException(
                status_code=404,
                detail="The uploaded file is not available.",
            )

    except (OSError, ValueError, TypeError):
        raise HTTPException(
            status_code=404,
            detail="The uploaded file is not available.",
        )

    media_type = (
        "application/pdf"
        if paper.file_type.lower() == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return FileResponse(
        path=stored_path,
        filename=paper.original_filename,
        media_type=media_type,
    )

@router.post("/users/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.id == current_admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own administrator account.",
        )

    if user.is_admin and user.is_active:
        active_admins = (
            db.query(User)
            .filter(
                User.is_admin.is_(True),
                User.is_active.is_(True),
            )
            .count()
        )

        if active_admins <= 1:
            raise HTTPException(
                status_code=400,
                detail="You cannot deactivate the last active administrator.",
            )

    user.is_active = not user.is_active

    db.commit()

    return RedirectResponse(
        url="/admin/users",
        status_code=303,
    )
