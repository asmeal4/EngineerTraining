import logging
import os
import sqlite3
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DATA_DIR, DATABASE_PATH, UPLOADS_DIR

logger = logging.getLogger(__name__)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DB_MEMBER_NAME = "app.db"
UPLOADS_MEMBER_PREFIX = "uploads/"


def _backup_connection(src_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(src_path), timeout=60)
    dest = sqlite3.connect(str(dest_path), timeout=60)
    try:
        src.backup(dest)
        dest.commit()
    finally:
        dest.close()
        src.close()


def verify_sqlite_file(path: Path) -> None:
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("file_too_large")
    if path.stat().st_size < 100:
        raise ValueError("invalid_database")
    conn = sqlite3.connect(str(path), timeout=30)
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
    db_tmp: Optional[Path] = None
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


def _clear_dir_contents(directory: Path) -> None:
    """Remove children of directory without deleting the directory itself."""
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)
        return
    for item in list(directory.iterdir()):
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _restore_uploads_from_dir(src_uploads: Path) -> None:
    """Replace upload files, keeping the uploads root folder (StaticFiles mount)."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _clear_dir_contents(UPLOADS_DIR)
    if not src_uploads.exists() or not src_uploads.is_dir():
        return
    for item in src_uploads.iterdir():
        target = UPLOADS_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _find_db_in_extract(extract_dir: Path) -> Optional[Path]:
    candidates = [
        extract_dir / DB_MEMBER_NAME,
        extract_dir / "engineer_training.db",
        extract_dir / "database.db",
    ]
    for path in candidates:
        if path.is_file():
            return path
    root_dbs = [p for p in extract_dir.glob("*.db") if p.is_file()]
    if len(root_dbs) == 1:
        return root_dbs[0]
    # Nested single .db (some zip tools wrap in a folder)
    nested = [p for p in extract_dir.rglob("*.db") if p.is_file()]
    if len(nested) == 1:
        return nested[0]
    return None


def _is_zip_backup(path: Path) -> bool:
    if path.suffix.lower() == ".zip":
        return True
    try:
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def restore_database(upload_path: Path) -> Path:
    """Restore from .zip (db + uploads) or legacy .db file."""
    if upload_path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("file_too_large")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore = BACKUP_DIR / f"pre_restore_{ts}.db"
    shutil.copy2(DATABASE_PATH, pre_restore)

    if _is_zip_backup(upload_path):
        extract_dir = Path(tempfile.mkdtemp(prefix=f"restore_{ts}_"))
        try:
            try:
                with zipfile.ZipFile(upload_path, "r") as zf:
                    for info in zf.infolist():
                        name = info.filename.replace("\\", "/")
                        if name.startswith("/") or ".." in name.split("/"):
                            raise ValueError("invalid_database")
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile as exc:
                raise ValueError("invalid_database") from exc

            db_file = _find_db_in_extract(extract_dir)
            if db_file is None:
                raise ValueError("invalid_database")

            verify_sqlite_file(db_file)
            _backup_connection(db_file, DATABASE_PATH)

            uploads_src = extract_dir / "uploads"
            if not uploads_src.is_dir():
                # Support zips that nest everything under one top folder
                nested = list(extract_dir.glob("*/uploads"))
                if len(nested) == 1 and nested[0].is_dir():
                    uploads_src = nested[0]
            if uploads_src.is_dir():
                try:
                    _restore_uploads_from_dir(uploads_src)
                except OSError as exc:
                    # DB already restored; keep going but surface as partial
                    logger.exception("uploads restore failed: %s", exc)
                    raise ValueError("uploads_restore_failed") from exc
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
    else:
        verify_sqlite_file(upload_path)
        _backup_connection(upload_path, DATABASE_PATH)

    return pre_restore
