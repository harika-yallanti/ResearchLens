from fastapi import HTTPException, Request, Response
from firebase_admin import auth as firebase_auth

from app.database import SessionLocal
from app.models.user import User


def clear_session_cookie(response: Response):
    response.delete_cookie(
        key="session",
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )


def get_current_user(
    request: Request,
    response: Response,
):
    session_cookie = request.cookies.get("session")

    if not session_cookie:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please sign in.",
        )

    try:
        decoded_token = firebase_auth.verify_session_cookie(
            session_cookie,
            check_revoked=True,
        )

        firebase_uid = decoded_token.get("uid")

        if not firebase_uid:
            clear_session_cookie(response)

            raise HTTPException(
                status_code=401,
                detail="Invalid session. Please sign in again.",
            )

    except Exception:
        clear_session_cookie(response)

        raise HTTPException(
            status_code=401,
            detail="Your session has expired or is invalid. Please sign in again.",
        )

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.firebase_uid == firebase_uid)
            .first()
        )

        if not user:
            clear_session_cookie(response)

            raise HTTPException(
                status_code=401,
                detail="User account not found. Please sign in again.",
            )

        if not user.is_active:
            clear_session_cookie(response)

            raise HTTPException(
                status_code=403,
                detail="Your account has been deactivated. Please contact the administrator.",
            )

        return user

    finally:
        db.close()


def get_current_admin(
    request: Request,
    response: Response,
):
    user = get_current_user(request, response)

    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )

    return user
