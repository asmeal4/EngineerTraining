import os
import sqlite3
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DATABASE_PATH

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _backup_connection(src_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(src_path))
    dest = sqlite3.connect(str(dest_path))
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()


def verify_sqlite_file(path: Path) -> None:
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("file_too_large")
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not row:
            raise ValueError("invalid_database")
    finally:
        conn.close()


def create_backup_file() -> tuple[Path, str]:
    """Create a temporary backup for download; caller must delete after send."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_name = f"engineer_training_backup_{ts}.db"
    fd, name = tempfile.mkstemp(prefix=f"backup_{ts}_", suffix=".db")
    os.close(fd)
    dest = Path(name)
    try:
        _backup_connection(DATABASE_PATH, dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest, download_name


def restore_database(upload_path: Path) -> Path:
    verify_sqlite_file(upload_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore = BACKUP_DIR / f"pre_restore_{ts}.db"
    shutil.copy2(DATABASE_PATH, pre_restore)
    _backup_connection(upload_path, DATABASE_PATH)
    return pre_restore
