import os
import sqlite3
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, DATABASE_PATH, UPLOADS_DIR

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DB_MEMBER_NAME = "app.db"
UPLOADS_MEMBER_PREFIX = "uploads/"


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
    """Create a ZIP with the database and uploads folder for download."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_name = f"engineer_training_backup_{ts}.zip"
    fd, name = tempfile.mkstemp(prefix=f"backup_{ts}_", suffix=".zip")
    os.close(fd)
    dest = Path(name)
    db_tmp: Path | None = None
    try:
        db_fd, db_name = tempfile.mkstemp(prefix=f"backup_db_{ts}_", suffix=".db")
        os.close(db_fd)
        db_tmp = Path(db_name)
        _backup_connection(DATABASE_PATH, db_tmp)

        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_tmp, arcname=DB_MEMBER_NAME)
            if UPLOADS_DIR.exists():
                for path in UPLOADS_DIR.rglob("*"):
                    if path.is_file():
                        rel = path.relative_to(UPLOADS_DIR).as_posix()
                        zf.write(path, arcname=f"{UPLOADS_MEMBER_PREFIX}{rel}")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        if db_tmp is not None:
            db_tmp.unlink(missing_ok=True)
    return dest, download_name


def _restore_uploads_from_dir(src_uploads: Path) -> None:
    """Replace current uploads with contents from extracted backup folder."""
    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if src_uploads.exists() and src_uploads.is_dir():
        for item in src_uploads.iterdir():
            target = UPLOADS_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)


def restore_database(upload_path: Path) -> Path:
    """Restore from .zip (db + uploads) or legacy .db file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore = BACKUP_DIR / f"pre_restore_{ts}.db"
    shutil.copy2(DATABASE_PATH, pre_restore)

    suffix = upload_path.suffix.lower()
    if suffix == ".zip" or zipfile.is_zipfile(upload_path):
        if upload_path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("file_too_large")
        extract_dir = Path(tempfile.mkdtemp(prefix=f"restore_{ts}_"))
        try:
            with zipfile.ZipFile(upload_path, "r") as zf:
                # Prevent path traversal
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/"):
                        raise ValueError("invalid_database")
                zf.extractall(extract_dir)

            db_candidates = [
                extract_dir / DB_MEMBER_NAME,
                extract_dir / "engineer_training.db",
                extract_dir / "database.db",
            ]
            db_file = next((p for p in db_candidates if p.is_file()), None)
            if db_file is None:
                # Any single .db at root of extract
                root_dbs = list(extract_dir.glob("*.db"))
                if len(root_dbs) == 1:
                    db_file = root_dbs[0]
            if db_file is None:
                raise ValueError("invalid_database")

            verify_sqlite_file(db_file)
            _backup_connection(db_file, DATABASE_PATH)

            uploads_src = extract_dir / "uploads"
            if uploads_src.is_dir():
                _restore_uploads_from_dir(uploads_src)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
    else:
        verify_sqlite_file(upload_path)
        _backup_connection(upload_path, DATABASE_PATH)

    return pre_restore
