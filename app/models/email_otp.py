
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func

from app.database import Base


class EmailOTP(Base):
    __tablename__ = "email_otp_verifications"

    id = Column(Integer, primary_key=True, index=True)

    challenge_id = Column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )

    firebase_uid = Column(
        String(128),
        nullable=False,
        index=True,
    )

    email = Column(
        String(255),
        nullable=False,
    )

    otp_hash = Column(
        String(64),
        nullable=False,
    )

    attempts = Column(
        Integer,
        nullable=False,
        default=0,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
    )

    last_sent_at = Column(
        DateTime,
        nullable=False,
    )

    consumed_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_email_otp_uid_created",
            "firebase_uid",
            "created_at",
        ),
    )
