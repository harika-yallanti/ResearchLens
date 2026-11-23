
import os
import hmac
import hashlib
import secrets

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from firebase_admin import auth as firebase_auth
from dotenv import load_dotenv

from app.database import get_db
from app.models.user import User
from app.models.email_otp import EmailOTP
from app.services.firebase_service import verify_firebase_token
from app.services.email_service import send_email


load_dotenv()

router = APIRouter(prefix="/auth", tags=["Authentication"])

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
SESSION_DAYS = 5


class FirebaseTokenRequest(BaseModel):
    id_token: str


class OTPVerificationRequest(BaseModel):
    id_token: str
    challenge_id: str
    otp: str = Field(pattern=r"^\d{6}$")


class OTPResendRequest(BaseModel):
    id_token: str
    challenge_id: str


def get_otp_hash(otp: str) -> str:
    secret = os.getenv("OTP_HASH_SECRET")

    if not secret:
        raise RuntimeError("OTP_HASH_SECRET is missing from .env")

    return hmac.new(
        secret.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_login_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def get_verified_firebase_user(id_token: str):
    decoded_token = verify_firebase_token(id_token)

    if not decoded_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Firebase ID token",
        )

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")

    if not firebase_uid or not email:
        raise HTTPException(
            status_code=400,
            detail="Firebase account is missing required user information",
        )

    return decoded_token


def send_login_otp(email: str, otp: str):
    subject = "Your ResearchLens Login Verification Code"

    body = (
        "Hello,\n\n"
        "Your ResearchLens login verification code is:\n\n"
        f"{otp}\n\n"
        "This code expires in 5 minutes.\n"
        "Do not share this code with anyone.\n\n"
        "If you did not attempt to log in, you can ignore this email.\n\n"
        "Regards,\n"
        "ResearchLens Team"
    )

    try:
        send_email(
            to_email=email,
            subject=subject,
            body=body,
        )

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to send the verification email. Please try again later.",
        )


def invalidate_active_challenges(db: Session, firebase_uid: str):
    now = datetime.utcnow()

    db.query(EmailOTP).filter(
        EmailOTP.firebase_uid == firebase_uid,
        EmailOTP.consumed_at.is_(None),
    ).update(
        {"consumed_at": now},
        synchronize_session=False,
    )


def set_session_cookie(response: Response, id_token: str):
    try:
        session_cookie = firebase_auth.create_session_cookie(
            id_token,
            expires_in=timedelta(days=SESSION_DAYS),
        )

        response.set_cookie(
            key="session",
            value=session_cookie,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=SESSION_DAYS * 24 * 60 * 60,
            path="/",
        )

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unable to create your login session.",
        )


@router.post("/verify")
def verify_user(
    payload: FirebaseTokenRequest,
    db: Session = Depends(get_db),
):
    decoded_token = get_verified_firebase_user(payload.id_token)

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")
    display_name = decoded_token.get("name")

    user = (
        db.query(User)
        .filter(User.firebase_uid == firebase_uid)
        .first()
    )

    if user:
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Your account has been deactivated. Please contact the administrator.",
            )

        user.email = email
        user.display_name = display_name

    else:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
            is_active=True,
        )

        db.add(user)

    db.commit()
    db.refresh(user)

    now = datetime.utcnow()

    existing_challenge = (
        db.query(EmailOTP)
        .filter(
            EmailOTP.firebase_uid == firebase_uid,
            EmailOTP.consumed_at.is_(None),
            EmailOTP.expires_at > now,
            EmailOTP.attempts < OTP_MAX_ATTEMPTS,
        )
        .order_by(EmailOTP.created_at.desc())
        .first()
    )

    if existing_challenge:
        elapsed = (
            now - existing_challenge.last_sent_at
        ).total_seconds()

        if elapsed < OTP_RESEND_SECONDS:
            return {
                "status": "otp_required",
                "message": "A verification code has already been sent to your email.",
                "challenge_id": existing_challenge.challenge_id,
                "user": {
                    "id": user.id,
                    "firebase_uid": user.firebase_uid,
                    "email": user.email,
                    "display_name": user.display_name,
                    "is_admin": bool(user.is_admin),
                    "is_active": bool(user.is_active),
                },
            }

    invalidate_active_challenges(db, firebase_uid)

    otp = create_login_otp()
    challenge_id = secrets.token_urlsafe(32)

    otp_hash = get_otp_hash(otp)

    send_login_otp(email, otp)

    challenge = EmailOTP(
        challenge_id=challenge_id,
        firebase_uid=firebase_uid,
        email=email,
        otp_hash=otp_hash,
        attempts=0,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        last_sent_at=now,
    )

    db.add(challenge)
    db.commit()

    return {
        "status": "otp_required",
        "message": "A verification code has been sent to your email.",
        "challenge_id": challenge_id,
        "user": {
            "id": user.id,
            "firebase_uid": user.firebase_uid,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": bool(user.is_admin),
            "is_active": bool(user.is_active),
        },
    }


@router.post("/otp/verify")
def verify_otp(
    payload: OTPVerificationRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    decoded_token = get_verified_firebase_user(payload.id_token)

    firebase_uid = decoded_token.get("uid")

    challenge = (
        db.query(EmailOTP)
        .filter(
            EmailOTP.challenge_id == payload.challenge_id,
            EmailOTP.firebase_uid == firebase_uid,
        )
        .with_for_update()
        .first()
    )

    if not challenge:
        raise HTTPException(
            status_code=404,
            detail="Verification request not found. Please sign in again.",
        )

    if challenge.consumed_at is not None:
        raise HTTPException(
            status_code=400,
            detail="This verification code has already been used.",
        )

    now = datetime.utcnow()

    if now > challenge.expires_at:
        challenge.consumed_at = now
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Verification code expired. Please sign in again.",
        )

    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        challenge.consumed_at = now
        db.commit()

        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Please sign in again.",
        )

    if not hmac.compare_digest(
        challenge.otp_hash,
        get_otp_hash(payload.otp),
    ):
        challenge.attempts += 1

        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            challenge.consumed_at = now

        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Incorrect verification code.",
        )

    user = (
        db.query(User)
        .filter(User.firebase_uid == firebase_uid)
        .first()
    )

    if not user or not user.is_active:
        challenge.consumed_at = now
        db.commit()

        raise HTTPException(
            status_code=403,
            detail="Your account is unavailable. Please contact the administrator.",
        )

    challenge.consumed_at = now
    db.commit()

    set_session_cookie(
        response=response,
        id_token=payload.id_token,
    )

    return {
        "status": "success",
        "message": "Email verification successful. Login completed.",
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": bool(user.is_admin),
        },
    }


@router.post("/otp/resend")
def resend_otp(
    payload: OTPResendRequest,
    db: Session = Depends(get_db),
):
    decoded_token = get_verified_firebase_user(payload.id_token)

    firebase_uid = decoded_token.get("uid")

    challenge = (
        db.query(EmailOTP)
        .filter(
            EmailOTP.challenge_id == payload.challenge_id,
            EmailOTP.firebase_uid == firebase_uid,
            EmailOTP.consumed_at.is_(None),
        )
        .with_for_update()
        .first()
    )

    if not challenge:
        raise HTTPException(
            status_code=404,
            detail="Verification request not found. Please sign in again.",
        )

    now = datetime.utcnow()

    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Please sign in again.",
        )

    if now > challenge.expires_at:
        raise HTTPException(
            status_code=400,
            detail="Verification code expired. Please sign in again.",
        )

    elapsed = (
        now - challenge.last_sent_at
    ).total_seconds()

    if elapsed < OTP_RESEND_SECONDS:
        remaining = OTP_RESEND_SECONDS - int(elapsed)

        raise HTTPException(
            status_code=429,
            detail=f"Please wait {remaining} seconds before requesting another code.",
        )

    user = (
        db.query(User)
        .filter(User.firebase_uid == firebase_uid)
        .first()
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is unavailable.",
        )

    otp = create_login_otp()
    otp_hash = get_otp_hash(otp)

    send_login_otp(
        email=challenge.email,
        otp=otp,
    )

    challenge.otp_hash = otp_hash
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    challenge.last_sent_at = now

    db.commit()

    return {
        "status": "success",
        "message": "A new verification code has been sent to your email.",
    }


@router.post("/session")
def disabled_session_endpoint():
    raise HTTPException(
        status_code=410,
        detail="Direct session creation is disabled. Complete email OTP verification to log in.",
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="session",
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return {
        "status": "success",
        "message": "Logged out successfully",
    }
