import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from .config import (
    DATABASE_PATH,
    DEFAULT_ADMIN_NAME,
    DEFAULT_ADMIN_PHONE,
    DEFAULT_PASSWORD,
)

USER_ROLES = ("admin", "user")

ROLE_LABELS = {
    "admin": "مدير",
    "user": "مستخدم",
}


def role_label(role: Optional[str]) -> str:
    return ROLE_LABELS.get(role or "user", role or "مستخدم")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_soft_delete_columns(conn: sqlite3.Connection, tables: list[str]) -> None:
    for table in tables:
        if not _column_exists(conn, table, "deleted_at"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")
        if not _column_exists(conn, table, "deleted_by"):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN deleted_by INTEGER "
                f"REFERENCES users(id)"
            )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_deleted_at "
            f"ON {table}(deleted_at)"
        )


def seed_admin(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count:
        return
    from .auth import hash_password

    conn.execute(
        """
        INSERT INTO users
        (name, phone, password_hash, role, is_active, created_at)
        VALUES (?, ?, ?, 'admin', 1, ?)
        """,
        (
            DEFAULT_ADMIN_NAME,
            DEFAULT_ADMIN_PHONE,
            hash_password(DEFAULT_PASSWORD),
            now_iso(),
        ),
    )


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER,
                updated_by INTEGER,
                deleted_at TEXT,
                deleted_by INTEGER
            );

            CREATE TABLE IF NOT EXISTS systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS work_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT NOT NULL,
                has_explanation INTEGER NOT NULL DEFAULT 0,
                explanation TEXT,
                image_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS package_systems (
                package_id INTEGER NOT NULL,
                system_id INTEGER NOT NULL,
                PRIMARY KEY (package_id, system_id),
                FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
                FOREIGN KEY (system_id) REFERENCES systems(id)
            );

            CREATE TABLE IF NOT EXISTS package_work_types (
                package_id INTEGER NOT NULL,
                work_type_id INTEGER NOT NULL,
                PRIMARY KEY (package_id, work_type_id),
                FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
                FOREIGN KEY (work_type_id) REFERENCES work_types(id)
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS content_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page TEXT NOT NULL,
                title TEXT NOT NULL,
                explanation TEXT,
                image_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS package_problems (
                package_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                PRIMARY KEY (package_id, section_id),
                FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
                FOREIGN KEY (section_id) REFERENCES content_sections(id)
            );

            CREATE TABLE IF NOT EXISTS training_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS training_package_work_types (
                training_package_id INTEGER NOT NULL,
                work_type_id INTEGER NOT NULL,
                PRIMARY KEY (training_package_id, work_type_id),
                FOREIGN KEY (training_package_id) REFERENCES training_packages(id) ON DELETE CASCADE,
                FOREIGN KEY (work_type_id) REFERENCES work_types(id)
            );

            CREATE TABLE IF NOT EXISTS training_package_sections (
                training_package_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                PRIMARY KEY (training_package_id, section_id),
                FOREIGN KEY (training_package_id) REFERENCES training_packages(id) ON DELETE CASCADE,
                FOREIGN KEY (section_id) REFERENCES content_sections(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                explanation TEXT,
                image_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                assigned_user_id INTEGER REFERENCES users(id),
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
            CREATE INDEX IF NOT EXISTS idx_systems_sort ON systems(sort_order);
            CREATE INDEX IF NOT EXISTS idx_sections_page_sort
                ON content_sections(page, sort_order);
            CREATE INDEX IF NOT EXISTS idx_tasks_sort ON tasks(sort_order);
            CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_user_id);
            CREATE INDEX IF NOT EXISTS idx_activity_created_at
                ON activity_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_activity_entity
                ON activity_log(entity_type, entity_id);
            """
        )
        _ensure_soft_delete_columns(
            conn,
            [
                "users",
                "systems",
                "work_types",
                "packages",
                "training_packages",
                "content_sections",
                "tasks",
            ],
        )
        if not _column_exists(conn, "work_types", "sort_order"):
            conn.execute(
                "ALTER TABLE work_types ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )
            rows = conn.execute(
                """
                SELECT id FROM work_types
                WHERE deleted_at IS NULL OR deleted_at = ''
                ORDER BY name ASC, id ASC
                """
            ).fetchall()
            for i, row in enumerate(rows, start=1):
                conn.execute(
                    "UPDATE work_types SET sort_order = ? WHERE id = ?",
                    (i, row["id"]),
                )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_work_types_sort ON work_types(sort_order)"
        )
        # Drop legacy install-type tables if present (replaced by work types)
        conn.execute("DROP TABLE IF EXISTS package_install_types")
        conn.execute("DROP TABLE IF EXISTS install_types")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS package_work_types (
                package_id INTEGER NOT NULL,
                work_type_id INTEGER NOT NULL,
                PRIMARY KEY (package_id, work_type_id),
                FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
                FOREIGN KEY (work_type_id) REFERENCES work_types(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS package_problems (
                package_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                PRIMARY KEY (package_id, section_id),
                FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
                FOREIGN KEY (section_id) REFERENCES content_sections(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                created_by INTEGER REFERENCES users(id),
                updated_by INTEGER REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_package_work_types (
                training_package_id INTEGER NOT NULL,
                work_type_id INTEGER NOT NULL,
                PRIMARY KEY (training_package_id, work_type_id),
                FOREIGN KEY (training_package_id) REFERENCES training_packages(id) ON DELETE CASCADE,
                FOREIGN KEY (work_type_id) REFERENCES work_types(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_package_sections (
                training_package_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                PRIMARY KEY (training_package_id, section_id),
                FOREIGN KEY (training_package_id) REFERENCES training_packages(id) ON DELETE CASCADE,
                FOREIGN KEY (section_id) REFERENCES content_sections(id)
            )
            """
        )
        seed_admin(conn)
