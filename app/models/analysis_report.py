
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Text,
    DateTime,
    JSON,
)
from sqlalchemy.sql import func

from app.database import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    paper_id = Column(
        Integer,
        ForeignKey("research_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    summary = Column(Text, nullable=True)
    paper_summary = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)

    methodology = Column(Text, nullable=True)
    findings = Column(Text, nullable=True)
    limitations = Column(Text, nullable=True)
    future_work = Column(Text, nullable=True)

    overall_score = Column(Integer, nullable=True)
    structure_score = Column(Integer, nullable=True)
    writing_score = Column(Integer, nullable=True)
    methodology_score = Column(Integer, nullable=True)
    abstract_score = Column(Integer, nullable=True)
    conclusion_score = Column(Integer, nullable=True)
    references_score = Column(Integer, nullable=True)

    structure_feedback = Column(Text, nullable=True)

    structure_summary = Column(Text, nullable=True)
    detected_sections = Column(JSON, nullable=True)
    section_analysis = Column(JSON, nullable=True)
    formatting_issues = Column(JSON, nullable=True)

    writing_feedback = Column(Text, nullable=True)
    methodology_feedback = Column(Text, nullable=True)
    abstract_feedback = Column(Text, nullable=True)
    conclusion_feedback = Column(Text, nullable=True)
    references_feedback = Column(Text, nullable=True)

    strengths = Column(JSON, nullable=True)
    weaknesses = Column(JSON, nullable=True)
    missing_sections = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)

    grammar_issues = Column(JSON, nullable=True)
    spelling_issues = Column(JSON, nullable=True)
    clarity_issues = Column(JSON, nullable=True)
    writing_tips = Column(JSON, nullable=True)

    # Citation and reference analysis
    citation_summary = Column(Text, nullable=True)
    citation_issues = Column(JSON, nullable=True)
    missing_references = Column(JSON, nullable=True)
    uncited_references = Column(JSON, nullable=True)
    citation_format_issues = Column(JSON, nullable=True)

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
