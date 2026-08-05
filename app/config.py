import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
WORK_TYPE_UPLOADS = UPLOADS_DIR / "work_types"
WORK_TYPE_UPLOADS.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "app.db"
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "engineer-training-local-secret-change-me",
)
SESSION_COOKIE = "et_session"
DEFAULT_PASSWORD = os.environ.get("DEFAULT_PASSWORD", "admin123")
DEFAULT_ADMIN_PHONE = os.environ.get("DEFAULT_ADMIN_PHONE", "0500000000")
DEFAULT_ADMIN_NAME = os.environ.get("DEFAULT_ADMIN_NAME", "المدير")
HTTPS_ONLY = _env_bool("HTTPS_ONLY", False)

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8001"))
RELOAD = _env_bool("RELOAD", True)
