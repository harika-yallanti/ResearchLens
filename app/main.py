
from pathlib import Path

from fastapi import (
    FastAPI,
    Request,
    Response,
    HTTPException,
    Depends,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from app.database import Base, engine, get_db

from app.models.research_paper import ResearchPaper
from app.models.user import User
from app.models.analysis_report import AnalysisReport
from app.models.plagiarism_check import PlagiarismCheck
from app.models.email_otp import EmailOTP

from app.services.session_service import get_current_user

from app.routers.auth import router as auth_router
from app.routers.papers import router as papers_router
from app.routers.admin import router as admin_router


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

app = FastAPI(
    title="AI Research Paper Quality Analyzer",
    description=(
        "An AI-powered application for evaluating "
        "academic research papers."
    ),
    version="1.0.0",
)

Base.metadata.create_all(bind=engine)

app.include_router(auth_router)
app.include_router(papers_router)
app.include_router(admin_router)

app.mount(
    "/static",
    StaticFiles(directory=APP_DIR / "static"),
    name="static",
)

templates = Jinja2Templates(
    directory=APP_DIR / "templates"
)


@app.get("/")
def home():
    return RedirectResponse(
        url="/login",
        status_code=303,
    )


@app.get("/login")
def login_page(
    request: Request,
    response: Response,
):
    try:
        current_user = get_current_user(request, response)

        destination = (
            "/admin/dashboard"
            if current_user.is_admin
            else "/dashboard"
        )

        return RedirectResponse(
            url=destination,
            status_code=303,
        )

    except HTTPException:
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "request": request,
            },
        )


@app.get("/dashboard")
def dashboard_page(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        current_user = get_current_user(request, response)

    except HTTPException:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    if current_user.is_admin:
        return RedirectResponse(
            url="/admin/dashboard",
            status_code=303,
        )

    print("DASHBOARD USER ID:", current_user.id)
    print("DASHBOARD USER EMAIL:", current_user.email)
    print("DASHBOARD USER NAME:", current_user.display_name)

    total_papers = (
        db.query(ResearchPaper)
        .filter(
            ResearchPaper.user_id == current_user.id
        )
        .count()
    )

    total_reports = (
        db.query(AnalysisReport)
        .filter(
            AnalysisReport.user_id == current_user.id
        )
        .count()
    )

    analyzed_papers = (
        db.query(AnalysisReport.paper_id)
        .filter(
            AnalysisReport.user_id == current_user.id
        )
        .distinct()
        .count()
    )

    report_rows = (
        db.query(AnalysisReport, ResearchPaper)
        .join(
            ResearchPaper,
            AnalysisReport.paper_id == ResearchPaper.id,
        )
        .filter(
            AnalysisReport.user_id == current_user.id,
            ResearchPaper.user_id == current_user.id,
        )
        .order_by(
            AnalysisReport.created_at.desc(),
            AnalysisReport.id.desc(),
        )
        .all()
    )

    recent_reports = []
    seen_paper_ids = set()

    for report, paper in report_rows:
        if paper.id in seen_paper_ids:
            continue

        seen_paper_ids.add(paper.id)

        recent_reports.append(
            {
                "report": report,
                "paper": paper,
            }
        )

        if len(recent_reports) == 5:
            break

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "app_name": "ResearchLens",
            "current_user": current_user,
            "total_papers": total_papers,
            "analyzed_papers": analyzed_papers,
            "total_reports": total_reports,
            "recent_reports": recent_reports,
        },
    )


@app.get("/health")
def health_check():
    return {
        "status": "running",
        "message": "Application is working",
    }


@app.get("/db-check")
def database_check():
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    return {
        "status": "success",
        "message": "MySQL database connection successful",
    }
