
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Text,
    DateTime,
    JSON,
)
from sqlalchemy.sql import func

from app.database import Base


class PlagiarismCheck(Base):
    __tablename__ = "plagiarism_checks"

    id = Column(Integer, primary_key=True, index=True)

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

    status = Column(
        String(30),
        nullable=False,
        default="pending",
    )

    similarity_score = Column(Float, nullable=True)

    plagiarism_summary = Column(Text, nullable=True)

    similarity_sources = Column(JSON, nullable=True)

    matched_passages = Column(JSON, nullable=True)

    error_message = Column(Text, nullable=True)

    checked_at = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
