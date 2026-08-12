from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
import bcrypt

from .database import db_session, role_label


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def authenticate(phone: str, password: str) -> Optional[dict]:
    phone = (phone or "").strip()
    if not phone or not password:
        return None
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM users
            WHERE phone = ? AND is_active = 1
              AND (deleted_at IS NULL OR deleted_at = '')
            """,
            (phone,),
        ).fetchone()
    if not row:
        return None
    user = dict(row)
    if not verify_password(password, user["password_hash"]):
        return None
    user["role_label"] = role_label(user.get("role"))
    return user


def get_user(user_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["role_label"] = role_label(data.get("role"))
    return data


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user_id"))


def get_current_user(request: Request) -> Optional[dict]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = get_user(int(user_id))
    if not user:
        return None
    if user.get("deleted_at") or not user.get("is_active"):
        return None
    return user


def is_admin(request: Request) -> bool:
    return request.session.get("role") == "admin"


def require_login(request: Request) -> Optional[RedirectResponse]:
    if not is_logged_in(request):
        from urllib.parse import quote

        next_url = quote(str(request.url.path))
        return RedirectResponse(f"/login?next={next_url}", status_code=303)
    user = get_current_user(request)
    if not user:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    return None


def require_admin(request: Request) -> Optional[RedirectResponse]:
    if (redir := require_login(request)):
        return redir
    if not is_admin(request):
        return RedirectResponse("/", status_code=303)
    return None


def login_user(request: Request, user: dict) -> None:
    request.session["user_id"] = user["id"]
    request.session["role"] = user["role"]
    request.session["user_name"] = user["name"]


def logout_user(request: Request) -> None:
    request.session.clear()


def get_visible_screens(user: Optional[dict]) -> set[str]:
    from . import services

    return services.parse_visible_screens(user)


def can_access_screen(user: Optional[dict], screen_key: str) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return screen_key in get_visible_screens(user)


def require_screen(
    request: Request, screen_key: str
) -> Optional[RedirectResponse]:
    if (redir := require_login(request)):
        return redir
    user = get_current_user(request)
    if not can_access_screen(user, screen_key):
        return RedirectResponse("/", status_code=303)
    return None
