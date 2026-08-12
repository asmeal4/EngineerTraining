"""Business logic for EngineerTraining."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional

from .auth import hash_password
from .config import BASE_DIR, DATA_DIR, SECTION_UPLOADS, TASK_UPLOADS, UPLOADS_DIR, WORK_TYPE_UPLOADS
from .database import db_session, now_iso, role_label

SECTION_PAGES = {
    "training": {
        "title": "التدريب",
        "subtitle": "شروحات وصور تعليمية مرتبة على أقسام",
        "entity": "training_section",
        "entity_label": "قسم تدريب",
        "base_path": "/training",
    },
    "problems": {
        "title": "أكثر المشكلات",
        "subtitle": "المشكلات الشائعة مع الشرح والصورة",
        "entity": "problem_section",
        "entity_label": "قسم مشكلة",
        "base_path": "/problems",
    },
}


def resolve_work_type_image_candidates(image_path: Optional[str]) -> list[Path]:
    """Possible absolute paths for a stored work-type image."""
    if not image_path:
        return []
    raw = str(image_path).strip().replace("\\", "/")
    if not raw:
        return []
    path = Path(raw)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        name = Path(raw).name
        candidates.extend(
            [
                UPLOADS_DIR / raw,
                WORK_TYPE_UPLOADS / name,
                DATA_DIR / raw,
                BASE_DIR / "data" / "uploads" / raw,
                BASE_DIR / raw,
            ]
        )
    # unique preserve order
    seen: set[str] = set()
    result: list[Path] = []
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def delete_work_type_image_file(image_path: Optional[str]) -> bool:
    """Delete image file from disk immediately. Returns True if a file was removed."""
    removed = False
    for path in resolve_work_type_image_candidates(image_path):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError:
            continue
    return removed


def resolve_section_image_candidates(image_path: Optional[str]) -> list[Path]:
    if not image_path:
        return []
    raw = str(image_path).strip().replace("\\", "/")
    if not raw:
        return []
    path = Path(raw)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        name = Path(raw).name
        candidates.extend(
            [
                UPLOADS_DIR / raw,
                SECTION_UPLOADS / name,
                DATA_DIR / raw,
                BASE_DIR / "data" / "uploads" / raw,
                BASE_DIR / raw,
            ]
        )
    seen: set[str] = set()
    result: list[Path] = []
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def delete_section_image_file(image_path: Optional[str]) -> bool:
    removed = False
    for path in resolve_section_image_candidates(image_path):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError:
            continue
    return removed


def resolve_task_image_candidates(image_path: Optional[str]) -> list[Path]:
    if not image_path:
        return []
    raw = str(image_path).strip().replace("\\", "/")
    if not raw:
        return []
    path = Path(raw)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        name = Path(raw).name
        candidates.extend(
            [
                UPLOADS_DIR / raw,
                TASK_UPLOADS / name,
                DATA_DIR / raw,
                BASE_DIR / "data" / "uploads" / raw,
                BASE_DIR / raw,
            ]
        )
    seen: set[str] = set()
    result: list[Path] = []
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def delete_task_image_file(image_path: Optional[str]) -> bool:
    removed = False
    for path in resolve_task_image_candidates(image_path):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError:
            continue
    return removed


def section_entity_for_page(page: str) -> str:
    meta = SECTION_PAGES.get(page) or SECTION_PAGES["training"]
    return meta["entity"]


def section_page_meta(page: str) -> dict:
    meta = SECTION_PAGES.get(page)
    if not meta:
        raise ValueError("invalid_page")
    return meta

ACTION_LABELS = {
    "create": "إضافة",
    "update": "تعديل",
    "delete": "حذف",
    "restore": "استرجاع",
    "purge": "حذف نهائي",
    "deactivate": "إيقاف",
    "activate": "تفعيل",
}

ENTITY_LABELS = {
    "user": "مستخدم",
    "system": "نظام",
    "work_type": "نوع عمل",
    "package": "باقة",
    "training_package": "باقة تدريب",
    "training_section": "قسم تدريب",
    "problem_section": "قسم مشكلة",
    "task": "مهمة",
}

NOT_DELETED = "(deleted_at IS NULL OR deleted_at = '')"
IS_DELETED = "(deleted_at IS NOT NULL AND deleted_at != '')"


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

def log_activity(
    conn,
    *,
    user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_log
        (user_id, action, entity_type, entity_id, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, action, entity_type, entity_id, details, now_iso()),
    )


def list_activity(
    *,
    q: str = "",
    user_id: Optional[int] = None,
    action: str = "",
    entity_type: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 300,
) -> list[dict]:
    clauses = ["1=1"]
    params: list[Any] = []
    if q:
        clauses.append(
            "(a.details LIKE ? OR a.action LIKE ? OR a.entity_type LIKE ? "
            "OR u.name LIKE ? OR u.phone LIKE ?)"
        )
        like = f"%{q.strip()}%"
        params.extend([like, like, like, like, like])
    if user_id:
        clauses.append("a.user_id = ?")
        params.append(user_id)
    if action:
        clauses.append("a.action = ?")
        params.append(action)
    if entity_type:
        clauses.append("a.entity_type = ?")
        params.append(entity_type)
    if date_from:
        clauses.append("a.created_at >= ?")
        params.append(date_from.strip())
    if date_to:
        clauses.append("a.created_at <= ?")
        params.append(date_to.strip() + " 23:59:59")
    where = " AND ".join(clauses)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT a.*, u.name AS user_name
            FROM activity_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE {where}
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["action_label"] = ACTION_LABELS.get(item["action"], item["action"])
        item["entity_label"] = ENTITY_LABELS.get(
            item.get("entity_type") or "", item.get("entity_type") or "—"
        )
        result.append(item)
    return result


def clear_activity_log() -> int:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM activity_log")
        return int(cur.rowcount or 0)


def clear_activity_older_than(days: int = 60) -> int:
    days = max(1, int(days))
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        cur = conn.execute(
            "DELETE FROM activity_log WHERE created_at < ?",
            (cutoff,),
        )
        return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_admin_count(conn, exclude_id: Optional[int] = None) -> int:
    sql = f"""
        SELECT COUNT(*) AS c FROM users
        WHERE role = 'admin' AND is_active = 1 AND {NOT_DELETED}
    """
    params: list[Any] = []
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(sql, params).fetchone()["c"]


def _user_names(conn, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT id, name FROM users WHERE id IN ({placeholders})",
        tuple(user_ids),
    ).fetchall()
    return {r["id"]: r["name"] for r in rows}


def _attach_audit(row: dict) -> dict:
    return row


def get_user_name(user_id: Optional[int]) -> str:
    if not user_id:
        return "—"
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["name"] if row else "—"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard_stats(user: Optional[dict] = None) -> dict:
    is_admin = bool(user and user.get("role") == "admin")
    user_id = int(user["id"]) if user and user.get("id") else None
    with db_session() as conn:
        def count(table: str) -> int:
            return conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {NOT_DELETED}"
            ).fetchone()["c"]

        def section_count(page: str) -> int:
            return conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM content_sections
                WHERE page = ? AND {NOT_DELETED}
                """,
                (page,),
            ).fetchone()["c"]

        trash = 0
        for table in (
            "users",
            "systems",
            "work_types",
            "packages",
            "training_packages",
            "content_sections",
            "tasks",
        ):
            trash += conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {IS_DELETED}"
            ).fetchone()["c"]

        if is_admin or user_id is None:
            task_count = count("tasks")
        else:
            task_count = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM tasks
                WHERE (assigned_user_id IS NULL OR assigned_user_id = ?)
                  AND {NOT_DELETED}
                """,
                (user_id,),
            ).fetchone()["c"]

        training_count = section_count("training")
        problems_count = section_count("problems")
        work_type_count = count("work_types")
        package_count = count("packages")
        user_count = count("users")
        active_users = conn.execute(
            f"SELECT COUNT(*) AS c FROM users WHERE is_active = 1 AND {NOT_DELETED}"
        ).fetchone()["c"]
        system_count = count("systems")

        top_rows = conn.execute(
            f"""
            SELECT p.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name,
                   (
                     SELECT COUNT(*) FROM activity_log a
                     WHERE a.entity_type = 'package' AND a.entity_id = p.id
                       AND a.action IN ('create', 'update', 'restore')
                   ) AS activity_count
            FROM packages p
            LEFT JOIN users cb ON cb.id = p.created_by
            LEFT JOIN users ub ON ub.id = p.updated_by
            WHERE (p.deleted_at IS NULL OR p.deleted_at = '')
            ORDER BY activity_count DESC,
                     COALESCE(p.updated_at, p.created_at) DESC,
                     p.id DESC
            """
        ).fetchall()
        top_packages = []
        for row in top_rows:
            item = dict(row)
            systems, work_types, problems = _package_links(conn, item["id"])
            item["systems"] = systems
            item["work_types"] = work_types
            item["problems"] = problems
            top_packages.append(item)

    return {
        "user_count": user_count,
        "system_count": system_count,
        "task_count": task_count,
        "training_count": training_count,
        "problems_count": problems_count,
        "work_type_count": work_type_count,
        "package_count": package_count,
        "trash_count": trash,
        "active_users": active_users,
        "top_packages": top_packages,
        "dashboard_tasks": list_tasks(user=user),
        "tasks_for_self": not is_admin,
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def list_users(q: str = "", *, active_only: bool = False) -> list[dict]:
    clauses = ["(u.deleted_at IS NULL OR u.deleted_at = '')"]
    params: list[Any] = []
    if active_only:
        clauses.append("u.is_active = 1")
    if q:
        clauses.append("(u.name LIKE ? OR u.phone LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like])
    where = " AND ".join(clauses)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT u.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM users u
            LEFT JOIN users cb ON cb.id = u.created_by
            LEFT JOIN users ub ON ub.id = u.updated_by
            WHERE {where}
            ORDER BY u.name COLLATE NOCASE, u.id
            """,
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["role_label"] = role_label(item.get("role"))
        result.append(item)
    return result


def get_user_record(user_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT u.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM users u
            LEFT JOIN users cb ON cb.id = u.created_by
            LEFT JOIN users ub ON ub.id = u.updated_by
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["role_label"] = role_label(item.get("role"))
    return item


def create_user(data: dict, actor_id: Optional[int] = None) -> int:
    password = (data.get("password") or "").strip()
    if not password:
        raise ValueError("password_required")
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    role = data.get("role") or "user"
    if role not in ("admin", "user"):
        role = "user"
    is_active = 1 if data.get("is_active", True) else 0
    if not name or not phone:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO users
            (name, phone, password_hash, role, is_active, created_at,
             created_by, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                hash_password(password),
                role,
                is_active,
                now_iso(),
                actor_id,
                actor_id,
                now_iso(),
            ),
        )
        user_id = int(cur.lastrowid)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="user",
            entity_id=user_id,
            details=f"إضافة مستخدم: {name} ({phone})",
        )
        return user_id


def update_user(
    user_id: int,
    data: dict,
    *,
    actor_id: Optional[int],
    actor_is_admin: bool,
) -> None:
    existing = get_user_record(user_id)
    if not existing or existing.get("deleted_at"):
        raise ValueError("not_found")

    is_self = actor_id == user_id
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    role = data.get("role") or existing["role"]
    if role not in ("admin", "user"):
        role = "user"
    is_active = 1 if data.get("is_active", True) else 0
    password = (data.get("password") or "").strip()

    if not actor_is_admin:
        if not is_self:
            raise PermissionError("cannot_edit_other")
        # Non-admin: keep own role/active; may change own password only
        role = existing["role"]
        is_active = existing["is_active"]
        if password and not is_self:
            raise PermissionError("cannot_change_password")
    else:
        # Admin protections
        if existing["role"] == "admin" and role != "admin":
            with db_session() as conn:
                if _active_admin_count(conn, exclude_id=user_id) < 1:
                    raise ValueError("last_admin_role")
        if existing["role"] == "admin" and existing["is_active"] and not is_active:
            with db_session() as conn:
                if _active_admin_count(conn, exclude_id=user_id) < 1:
                    raise ValueError("last_admin_deactivate")

    if not name or not phone:
        raise ValueError("required")

    with db_session() as conn:
        fields = [
            "name = ?",
            "phone = ?",
            "role = ?",
            "is_active = ?",
            "updated_by = ?",
            "updated_at = ?",
        ]
        values: list[Any] = [name, phone, role, is_active, actor_id, now_iso()]
        if password:
            if not actor_is_admin and not is_self:
                raise PermissionError("cannot_change_password")
            fields.append("password_hash = ?")
            values.append(hash_password(password))
        values.append(user_id)
        conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="user",
            entity_id=user_id,
            details=f"تعديل مستخدم: {name}",
        )


def soft_delete_user(
    user_id: int,
    *,
    actor_id: int,
    actor_is_admin: bool,
) -> tuple[bool, str]:
    existing = get_user_record(user_id)
    if not existing or existing.get("deleted_at"):
        return False, "not_found"
    if not actor_is_admin:
        return False, "forbidden"
    if existing["role"] == "admin":
        with db_session() as conn:
            if _active_admin_count(conn, exclude_id=user_id) < 1:
                return False, "last_admin"
    with db_session() as conn:
        conn.execute(
            """
            UPDATE users
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, user_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="user",
            entity_id=user_id,
            details=f"حذف مستخدم: {existing['name']}",
        )
    return True, ""


def restore_user(user_id: int, *, actor_id: int) -> tuple[bool, str]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False, "not_found"
        conn.execute(
            """
            UPDATE users
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, user_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="user",
            entity_id=user_id,
            details=f"استرجاع مستخدم: {row['name']}",
        )
    return True, ""


def purge_user(user_id: int, *, actor_id: int) -> tuple[bool, str]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False, "not_in_trash"
        if row["role"] == "admin":
            # Still protect purging if it would leave zero admins among remaining
            remaining = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM users
                WHERE role = 'admin' AND id != ? AND {NOT_DELETED}
                """,
                (user_id,),
            ).fetchone()["c"]
            if remaining < 1:
                return False, "last_admin"
        name = row["name"]
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="user",
            entity_id=user_id,
            details=f"حذف نهائي لمستخدم: {name}",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------

def list_systems(q: str = "", include_deleted: bool = False) -> list[dict]:
    clauses: list[str] = []
    if not include_deleted:
        clauses.append("(s.deleted_at IS NULL OR s.deleted_at = '')")
    params: list[Any] = []
    if q:
        clauses.append("(s.name LIKE ? OR s.abbreviation LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like])
    where = " AND ".join(clauses) if clauses else "1=1"
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT s.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM systems s
            LEFT JOIN users cb ON cb.id = s.created_by
            LEFT JOIN users ub ON ub.id = s.updated_by
            WHERE {where}
            ORDER BY s.sort_order, s.name
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_system(system_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT s.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM systems s
            LEFT JOIN users cb ON cb.id = s.created_by
            LEFT JOIN users ub ON ub.id = s.updated_by
            WHERE s.id = ?
            """,
            (system_id,),
        ).fetchone()
    return dict(row) if row else None


def create_system(data: dict, actor_id: Optional[int] = None) -> int:
    name = (data.get("name") or "").strip()
    abbr = (data.get("abbreviation") or "").strip()
    sort_order = int(data.get("sort_order") or 0)
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO systems
            (name, abbreviation, sort_order, created_at, updated_at,
             created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, abbr, sort_order, now_iso(), now_iso(), actor_id, actor_id),
        )
        sid = int(cur.lastrowid)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="system",
            entity_id=sid,
            details=f"إضافة نظام: {name}",
        )
        return sid


def update_system(
    system_id: int, data: dict, actor_id: Optional[int] = None
) -> None:
    name = (data.get("name") or "").strip()
    abbr = (data.get("abbreviation") or "").strip()
    sort_order = int(data.get("sort_order") or 0)
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        conn.execute(
            """
            UPDATE systems
            SET name = ?, abbreviation = ?, sort_order = ?,
                updated_at = ?, updated_by = ?
            WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')
            """,
            (name, abbr, sort_order, now_iso(), actor_id, system_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="system",
            entity_id=system_id,
            details=f"تعديل نظام: {name}",
        )


def soft_delete_system(system_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM systems WHERE id = ? AND {NOT_DELETED}",
            (system_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE systems
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, system_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="system",
            entity_id=system_id,
            details=f"حذف نظام: {row['name']}",
        )
    return True


def restore_system(system_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM systems WHERE id = ?", (system_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            """
            UPDATE systems
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, system_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="system",
            entity_id=system_id,
            details=f"استرجاع نظام: {row['name']}",
        )
    return True


def purge_system(system_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM systems WHERE id = ?", (system_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            "DELETE FROM package_systems WHERE system_id = ?", (system_id,)
        )
        conn.execute("DELETE FROM systems WHERE id = ?", (system_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="system",
            entity_id=system_id,
            details=f"حذف نهائي لنظام: {row['name']}",
        )
    return True


# ---------------------------------------------------------------------------
# Work types
# ---------------------------------------------------------------------------

def list_work_types(q: str = "") -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT w.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM work_types w
            LEFT JOIN users cb ON cb.id = w.created_by
            LEFT JOIN users ub ON ub.id = w.updated_by
            WHERE {NOT_DELETED.replace("deleted_at", "w.deleted_at")}
            ORDER BY w.sort_order ASC, w.id ASC
            """
        ).fetchall()
    items = [dict(r) for r in rows]
    needle = (q or "").strip().lower()
    if needle:
        items = [
            item
            for item in items
            if needle in (item.get("name") or "").lower()
            or needle in (item.get("abbreviation") or "").lower()
            or needle in (item.get("explanation") or "").lower()
        ]
    return items


def get_work_type(work_type_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT w.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM work_types w
            LEFT JOIN users cb ON cb.id = w.created_by
            LEFT JOIN users ub ON ub.id = w.updated_by
            WHERE w.id = ?
            """,
            (work_type_id,),
        ).fetchone()
    return dict(row) if row else None


def create_work_type(data: dict, actor_id: Optional[int] = None) -> int:
    name = (data.get("name") or "").strip()
    abbr = (data.get("abbreviation") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    image_path = data.get("image_path")
    sort_order = int(data.get("sort_order") or 0)
    has_explanation = 1 if (explanation or image_path) else 0
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO work_types
            (name, abbreviation, has_explanation, explanation, image_path,
             sort_order, created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                abbr,
                has_explanation,
                explanation if has_explanation else None,
                image_path if has_explanation else None,
                sort_order,
                now_iso(),
                now_iso(),
                actor_id,
                actor_id,
            ),
        )
        wid = int(cur.lastrowid)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="work_type",
            entity_id=wid,
            details=f"إضافة نوع عمل: {name}",
        )
        return wid


def update_work_type(
    work_type_id: int, data: dict, actor_id: Optional[int] = None
) -> None:
    name = (data.get("name") or "").strip()
    abbr = (data.get("abbreviation") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    sort_order = int(data.get("sort_order") or 0)
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        existing = conn.execute(
            f"SELECT * FROM work_types WHERE id = ? AND {NOT_DELETED}",
            (work_type_id,),
        ).fetchone()
        if not existing:
            raise ValueError("not_found")
        old_image = existing["image_path"]
        # Only change image when form explicitly sent image_path (clear or replace)
        if "image_path" in data:
            new_image = data["image_path"]
        else:
            new_image = old_image
        has_explanation = 1 if (explanation or new_image) else 0
        final_image = new_image if has_explanation else None
        fields = """
            name = ?, abbreviation = ?, has_explanation = ?,
            explanation = ?, image_path = ?, sort_order = ?,
            updated_at = ?, updated_by = ?
        """
        values: list[Any] = [
            name,
            abbr,
            has_explanation,
            explanation if has_explanation else None,
            final_image,
            sort_order,
            now_iso(),
            actor_id,
            work_type_id,
        ]
        conn.execute(
            f"UPDATE work_types SET {fields} WHERE id = ?",
            values,
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="work_type",
            entity_id=work_type_id,
            details=f"تعديل نوع عمل: {name}",
        )
    # Delete file only when image was cleared or replaced from the image UI
    if old_image and old_image != final_image:
        delete_work_type_image_file(old_image)


def soft_delete_work_type(work_type_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM work_types WHERE id = ? AND {NOT_DELETED}",
            (work_type_id,),
        ).fetchone()
        if not row:
            return False
        # Soft delete keeps image on disk so restore can bring it back
        conn.execute(
            """
            UPDATE work_types
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, work_type_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="work_type",
            entity_id=work_type_id,
            details=f"حذف نوع عمل: {row['name']}",
        )
    return True


def restore_work_type(work_type_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM work_types WHERE id = ?", (work_type_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            """
            UPDATE work_types
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, work_type_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="work_type",
            entity_id=work_type_id,
            details=f"استرجاع نوع عمل: {row['name']}",
        )
    return True


def purge_work_type(work_type_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM work_types WHERE id = ?", (work_type_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        image_path = row["image_path"]
        conn.execute(
            "DELETE FROM package_work_types WHERE work_type_id = ?",
            (work_type_id,),
        )
        conn.execute("DELETE FROM work_types WHERE id = ?", (work_type_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="work_type",
            entity_id=work_type_id,
            details=f"حذف نهائي لنوع عمل: {row['name']}",
        )
    # Delete any remaining file (also covers records soft-deleted before this fix)
    delete_work_type_image_file(image_path)
    return True


# ---------------------------------------------------------------------------
# Content sections (training / problems)
# ---------------------------------------------------------------------------

def list_sections(page: str, q: str = "") -> list[dict]:
    section_page_meta(page)
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT s.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM content_sections s
            LEFT JOIN users cb ON cb.id = s.created_by
            LEFT JOIN users ub ON ub.id = s.updated_by
            WHERE s.page = ?
              AND (s.deleted_at IS NULL OR s.deleted_at = '')
            ORDER BY s.sort_order ASC, s.id ASC
            """,
            (page,),
        ).fetchall()
    items = [dict(r) for r in rows]
    needle = (q or "").strip().lower()
    if needle:
        items = [
            item
            for item in items
            if needle in (item.get("title") or "").lower()
            or needle in (item.get("explanation") or "").lower()
        ]
    return items


def get_section(section_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT s.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM content_sections s
            LEFT JOIN users cb ON cb.id = s.created_by
            LEFT JOIN users ub ON ub.id = s.updated_by
            WHERE s.id = ?
            """,
            (section_id,),
        ).fetchone()
    return dict(row) if row else None


def create_section(page: str, data: dict, actor_id: Optional[int] = None) -> int:
    meta = section_page_meta(page)
    title = (data.get("title") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    image_path = data.get("image_path")
    sort_order = int(data.get("sort_order") or 0)
    if not title:
        raise ValueError("required")
    entity = meta["entity"]
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO content_sections
            (page, title, explanation, image_path, sort_order,
             created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page,
                title,
                explanation,
                image_path,
                sort_order,
                now_iso(),
                now_iso(),
                actor_id,
                actor_id,
            ),
        )
        sid = int(cur.lastrowid)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type=entity,
            entity_id=sid,
            details=f"إضافة {meta['entity_label']}: {title}",
        )
        return sid


def update_section(
    section_id: int, data: dict, actor_id: Optional[int] = None
) -> None:
    title = (data.get("title") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    sort_order = int(data.get("sort_order") or 0)
    if not title:
        raise ValueError("required")
    with db_session() as conn:
        existing = conn.execute(
            f"SELECT * FROM content_sections WHERE id = ? AND {NOT_DELETED}",
            (section_id,),
        ).fetchone()
        if not existing:
            raise ValueError("not_found")
        old_image = existing["image_path"]
        if "image_path" in data:
            new_image = data["image_path"]
        else:
            new_image = old_image
        page = existing["page"]
        meta = section_page_meta(page)
        conn.execute(
            """
            UPDATE content_sections
            SET title = ?, explanation = ?, image_path = ?, sort_order = ?,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (
                title,
                explanation,
                new_image,
                sort_order,
                now_iso(),
                actor_id,
                section_id,
            ),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type=meta["entity"],
            entity_id=section_id,
            details=f"تعديل {meta['entity_label']}: {title}",
        )
    if old_image and old_image != new_image:
        delete_section_image_file(old_image)


def soft_delete_section(section_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM content_sections WHERE id = ? AND {NOT_DELETED}",
            (section_id,),
        ).fetchone()
        if not row:
            return False
        meta = section_page_meta(row["page"])
        conn.execute(
            """
            UPDATE content_sections
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, section_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type=meta["entity"],
            entity_id=section_id,
            details=f"حذف {meta['entity_label']}: {row['title']}",
        )
    return True


def restore_section(section_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM content_sections WHERE id = ?", (section_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        meta = section_page_meta(row["page"])
        conn.execute(
            """
            UPDATE content_sections
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, section_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type=meta["entity"],
            entity_id=section_id,
            details=f"استرجاع {meta['entity_label']}: {row['title']}",
        )
    return True


def purge_section(section_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM content_sections WHERE id = ?", (section_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        image_path = row["image_path"]
        meta = section_page_meta(row["page"])
        conn.execute(
            "DELETE FROM package_problems WHERE section_id = ?", (section_id,)
        )
        conn.execute(
            "DELETE FROM training_package_sections WHERE section_id = ?",
            (section_id,),
        )
        conn.execute("DELETE FROM content_sections WHERE id = ?", (section_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type=meta["entity"],
            entity_id=section_id,
            details=f"حذف نهائي ل{meta['entity_label']}: {row['title']}",
        )
    delete_section_image_file(image_path)
    return True



# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _parse_assigned_user_id(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def list_tasks(q: str = "", user: Optional[dict] = None) -> list[dict]:
    """List tasks. If user is a non-admin, filter to assigned tasks only (for dashboard)."""
    clauses = ["(t.deleted_at IS NULL OR t.deleted_at = '')"]
    params: list[Any] = []
    if user and user.get("role") != "admin" and user.get("id") is not None:
        clauses.append("(t.assigned_user_id IS NULL OR t.assigned_user_id = ?)")
        params.append(int(user["id"]))
    where = " AND ".join(clauses)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT t.*,
                   au.name AS assigned_user_name,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM tasks t
            LEFT JOIN users au ON au.id = t.assigned_user_id
            LEFT JOIN users cb ON cb.id = t.created_by
            LEFT JOIN users ub ON ub.id = t.updated_by
            WHERE {where}
            ORDER BY t.sort_order ASC, t.id ASC
            """,
            params,
        ).fetchall()
    items = [dict(r) for r in rows]
    needle = (q or "").strip().lower()
    if needle:
        items = [
            item
            for item in items
            if needle in (item.get("title") or "").lower()
            or needle in (item.get("explanation") or "").lower()
            or needle in (item.get("assigned_user_name") or "").lower()
        ]
    return items


def get_task(task_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT t.*,
                   au.name AS assigned_user_name,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM tasks t
            LEFT JOIN users au ON au.id = t.assigned_user_id
            LEFT JOIN users cb ON cb.id = t.created_by
            LEFT JOIN users ub ON ub.id = t.updated_by
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def create_task(data: dict, actor_id: Optional[int] = None) -> int:
    title = (data.get("title") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    image_path = data.get("image_path")
    sort_order = int(data.get("sort_order") or 0)
    assigned_user_id = _parse_assigned_user_id(data.get("assigned_user_id"))
    if not title:
        raise ValueError("required")
    with db_session() as conn:
        if assigned_user_id is not None:
            user = conn.execute(
                f"SELECT id FROM users WHERE id = ? AND is_active = 1 AND {NOT_DELETED}",
                (assigned_user_id,),
            ).fetchone()
            if not user:
                raise ValueError("invalid_assignee")
        cur = conn.execute(
            """
            INSERT INTO tasks
            (title, explanation, image_path, sort_order, assigned_user_id,
             created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                explanation,
                image_path,
                sort_order,
                assigned_user_id,
                now_iso(),
                now_iso(),
                actor_id,
                actor_id,
            ),
        )
        tid = int(cur.lastrowid)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="task",
            entity_id=tid,
            details=f"إضافة مهمة: {title}",
        )
        return tid


def update_task(task_id: int, data: dict, actor_id: Optional[int] = None) -> None:
    title = (data.get("title") or "").strip()
    explanation = (data.get("explanation") or "").strip() or None
    sort_order = int(data.get("sort_order") or 0)
    assigned_user_id = _parse_assigned_user_id(data.get("assigned_user_id"))
    if not title:
        raise ValueError("required")
    with db_session() as conn:
        existing = conn.execute(
            f"SELECT * FROM tasks WHERE id = ? AND {NOT_DELETED}",
            (task_id,),
        ).fetchone()
        if not existing:
            raise ValueError("not_found")
        if assigned_user_id is not None:
            user = conn.execute(
                f"SELECT id FROM users WHERE id = ? AND {NOT_DELETED}",
                (assigned_user_id,),
            ).fetchone()
            if not user:
                raise ValueError("invalid_assignee")
        old_image = existing["image_path"]
        if "image_path" in data:
            new_image = data["image_path"]
        else:
            new_image = old_image
        conn.execute(
            """
            UPDATE tasks
            SET title = ?, explanation = ?, image_path = ?, sort_order = ?,
                assigned_user_id = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (
                title,
                explanation,
                new_image,
                sort_order,
                assigned_user_id,
                now_iso(),
                actor_id,
                task_id,
            ),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="task",
            entity_id=task_id,
            details=f"تعديل مهمة: {title}",
        )
    if old_image and old_image != new_image:
        delete_task_image_file(old_image)


def soft_delete_task(task_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM tasks WHERE id = ? AND {NOT_DELETED}",
            (task_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE tasks
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, task_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="task",
            entity_id=task_id,
            details=f"حذف مهمة: {row['title']}",
        )
    return True


def restore_task(task_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            """
            UPDATE tasks
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, task_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="task",
            entity_id=task_id,
            details=f"استرجاع مهمة: {row['title']}",
        )
    return True


def purge_task(task_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        image_path = row["image_path"]
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="task",
            entity_id=task_id,
            details=f"حذف نهائي لمهمة: {row['title']}",
        )
    delete_task_image_file(image_path)
    return True


# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------

def _package_links(
    conn, package_id: int
) -> tuple[list[dict], list[dict], list[dict]]:
    systems = conn.execute(
        """
        SELECT s.id, s.name, s.abbreviation
        FROM package_systems ps
        JOIN systems s ON s.id = ps.system_id
        WHERE ps.package_id = ?
        ORDER BY s.sort_order, s.name
        """,
        (package_id,),
    ).fetchall()
    work_types = conn.execute(
        """
        SELECT w.id, w.name, w.abbreviation,
               w.has_explanation, w.explanation, w.image_path
        FROM package_work_types pw
        JOIN work_types w ON w.id = pw.work_type_id
        WHERE pw.package_id = ?
        ORDER BY w.sort_order, w.id
        """,
        (package_id,),
    ).fetchall()
    problems = conn.execute(
        """
        SELECT c.id, c.title, c.explanation, c.image_path
        FROM package_problems pp
        JOIN content_sections c ON c.id = pp.section_id
        WHERE pp.package_id = ?
          AND c.page = 'problems'
          AND (c.deleted_at IS NULL OR c.deleted_at = '')
        ORDER BY c.sort_order, c.id
        """,
        (package_id,),
    ).fetchall()
    return (
        [dict(r) for r in systems],
        [dict(r) for r in work_types],
        [dict(r) for r in problems],
    )


def list_packages(q: str = "") -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM packages p
            LEFT JOIN users cb ON cb.id = p.created_by
            LEFT JOIN users ub ON ub.id = p.updated_by
            WHERE {NOT_DELETED.replace("deleted_at", "p.deleted_at")}
            ORDER BY p.name
            """,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            systems, work_types, problems = _package_links(conn, item["id"])
            item["systems"] = systems
            item["work_types"] = work_types
            item["problems"] = problems
            item["system_ids"] = [s["id"] for s in systems]
            item["work_type_ids"] = [w["id"] for w in work_types]
            item["problem_ids"] = [p["id"] for p in problems]
            result.append(item)

    needle = (q or "").strip().lower()
    if not needle:
        return result

    def contains(text: Any) -> bool:
        return needle in (text or "").lower()

    matched: list[dict] = []
    for item in result:
        systems = item.get("systems") or []
        work_types = item.get("work_types") or []
        problems = item.get("problems") or []

        pkg_hit = contains(item.get("name")) or contains(item.get("notes"))
        any_hit = pkg_hit

        for s in systems:
            s_hit = contains(s.get("name")) or contains(s.get("abbreviation"))
            s["search_hit"] = s_hit
            if s_hit:
                any_hit = True

        for w in work_types:
            w_hit = (
                contains(w.get("name"))
                or contains(w.get("abbreviation"))
                or contains(w.get("explanation"))
            )
            w["search_hit"] = w_hit
            w["auto_open"] = w_hit
            if w_hit:
                any_hit = True

        for pr in problems:
            pr_hit = contains(pr.get("title")) or contains(pr.get("explanation"))
            pr["search_hit"] = pr_hit
            pr["auto_open"] = pr_hit
            if pr_hit:
                any_hit = True

        if not any_hit:
            continue
        item["search_hit"] = True
        item["open_work_id"] = next(
            (w["id"] for w in work_types if w.get("auto_open")),
            None,
        )
        item["open_problem_id"] = next(
            (pr["id"] for pr in problems if pr.get("auto_open")),
            None,
        )
        matched.append(item)

    return matched


def get_package(package_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT p.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM packages p
            LEFT JOIN users cb ON cb.id = p.created_by
            LEFT JOIN users ub ON ub.id = p.updated_by
            WHERE p.id = ?
            """,
            (package_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        systems, work_types, problems = _package_links(conn, package_id)
        item["systems"] = systems
        item["work_types"] = work_types
        item["problems"] = problems
        item["system_ids"] = [s["id"] for s in systems]
        item["work_type_ids"] = [w["id"] for w in work_types]
        item["problem_ids"] = [p["id"] for p in problems]
        return item


def _set_package_links(
    conn,
    package_id: int,
    system_ids: list[int],
    work_type_ids: list[int],
    problem_ids: list[int],
) -> None:
    conn.execute(
        "DELETE FROM package_systems WHERE package_id = ?", (package_id,)
    )
    conn.execute(
        "DELETE FROM package_work_types WHERE package_id = ?", (package_id,)
    )
    conn.execute(
        "DELETE FROM package_problems WHERE package_id = ?", (package_id,)
    )
    for sid in system_ids:
        conn.execute(
            "INSERT INTO package_systems (package_id, system_id) VALUES (?, ?)",
            (package_id, sid),
        )
    for wid in work_type_ids:
        conn.execute(
            "INSERT INTO package_work_types (package_id, work_type_id) "
            "VALUES (?, ?)",
            (package_id, wid),
        )
    for pid in problem_ids:
        conn.execute(
            "INSERT INTO package_problems (package_id, section_id) "
            "VALUES (?, ?)",
            (package_id, pid),
        )


def create_package(
    data: dict,
    system_ids: list[int],
    work_type_ids: list[int],
    problem_ids: list[int],
    actor_id: Optional[int] = None,
) -> int:
    name = (data.get("name") or "").strip()
    notes = (data.get("notes") or "").strip() or None
    if not name:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO packages
            (name, notes, created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, notes, now_iso(), now_iso(), actor_id, actor_id),
        )
        pid = int(cur.lastrowid)
        _set_package_links(conn, pid, system_ids, work_type_ids, problem_ids)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="package",
            entity_id=pid,
            details=f"إضافة باقة: {name}",
        )
        return pid


def update_package(
    package_id: int,
    data: dict,
    system_ids: list[int],
    work_type_ids: list[int],
    problem_ids: list[int],
    actor_id: Optional[int] = None,
) -> None:
    name = (data.get("name") or "").strip()
    notes = (data.get("notes") or "").strip() or None
    if not name:
        raise ValueError("required")
    with db_session() as conn:
        conn.execute(
            """
            UPDATE packages
            SET name = ?, notes = ?, updated_at = ?, updated_by = ?
            WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')
            """,
            (name, notes, now_iso(), actor_id, package_id),
        )
        _set_package_links(
            conn, package_id, system_ids, work_type_ids, problem_ids
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="package",
            entity_id=package_id,
            details=f"تعديل باقة: {name}",
        )


def soft_delete_package(package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM packages WHERE id = ? AND {NOT_DELETED}",
            (package_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE packages
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, package_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="package",
            entity_id=package_id,
            details=f"حذف باقة: {row['name']}",
        )
    return True


def restore_package(package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM packages WHERE id = ?", (package_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            """
            UPDATE packages
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, package_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="package",
            entity_id=package_id,
            details=f"استرجاع باقة: {row['name']}",
        )
    return True


def purge_package(package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM packages WHERE id = ?", (package_id,)
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            "DELETE FROM package_systems WHERE package_id = ?", (package_id,)
        )
        conn.execute(
            "DELETE FROM package_work_types WHERE package_id = ?",
            (package_id,),
        )
        conn.execute(
            "DELETE FROM package_problems WHERE package_id = ?",
            (package_id,),
        )
        conn.execute("DELETE FROM packages WHERE id = ?", (package_id,))
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="package",
            entity_id=package_id,
            details=f"حذف نهائي لباقة: {row['name']}",
        )
    return True


# ---------------------------------------------------------------------------
# Training packages
# ---------------------------------------------------------------------------

def _training_package_links(
    conn, training_package_id: int
) -> tuple[list[dict], list[dict]]:
    work_types = conn.execute(
        """
        SELECT w.id, w.name, w.abbreviation,
               w.has_explanation, w.explanation, w.image_path
        FROM training_package_work_types tpw
        JOIN work_types w ON w.id = tpw.work_type_id
        WHERE tpw.training_package_id = ?
        ORDER BY w.sort_order, w.id
        """,
        (training_package_id,),
    ).fetchall()
    trainings = conn.execute(
        """
        SELECT c.id, c.title, c.explanation, c.image_path
        FROM training_package_sections tps
        JOIN content_sections c ON c.id = tps.section_id
        WHERE tps.training_package_id = ?
          AND c.page = 'training'
          AND (c.deleted_at IS NULL OR c.deleted_at = '')
        ORDER BY c.sort_order, c.id
        """,
        (training_package_id,),
    ).fetchall()
    return (
        [dict(r) for r in work_types],
        [dict(r) for r in trainings],
    )


def list_training_packages(q: str = "") -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT tp.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM training_packages tp
            LEFT JOIN users cb ON cb.id = tp.created_by
            LEFT JOIN users ub ON ub.id = tp.updated_by
            WHERE {NOT_DELETED.replace("deleted_at", "tp.deleted_at")}
            ORDER BY tp.name
            """,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            work_types, trainings = _training_package_links(conn, item["id"])
            item["work_types"] = work_types
            item["trainings"] = trainings
            item["work_type_ids"] = [w["id"] for w in work_types]
            item["training_ids"] = [t["id"] for t in trainings]
            result.append(item)

    needle = (q or "").strip().lower()
    if not needle:
        return result

    def contains(text: Any) -> bool:
        return needle in (text or "").lower()

    matched: list[dict] = []
    for item in result:
        work_types = item.get("work_types") or []
        trainings = item.get("trainings") or []

        pkg_hit = contains(item.get("name")) or contains(item.get("notes"))
        any_hit = pkg_hit

        for w in work_types:
            w_hit = (
                contains(w.get("name"))
                or contains(w.get("abbreviation"))
                or contains(w.get("explanation"))
            )
            w["search_hit"] = w_hit
            w["auto_open"] = w_hit
            if w_hit:
                any_hit = True

        for tr in trainings:
            tr_hit = contains(tr.get("title")) or contains(tr.get("explanation"))
            tr["search_hit"] = tr_hit
            tr["auto_open"] = tr_hit
            if tr_hit:
                any_hit = True

        if not any_hit:
            continue
        item["search_hit"] = True
        item["open_work_id"] = next(
            (w["id"] for w in work_types if w.get("auto_open")),
            None,
        )
        item["open_training_id"] = next(
            (tr["id"] for tr in trainings if tr.get("auto_open")),
            None,
        )
        matched.append(item)

    return matched


def get_training_package(training_package_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT tp.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM training_packages tp
            LEFT JOIN users cb ON cb.id = tp.created_by
            LEFT JOIN users ub ON ub.id = tp.updated_by
            WHERE tp.id = ?
            """,
            (training_package_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        work_types, trainings = _training_package_links(conn, training_package_id)
        item["work_types"] = work_types
        item["trainings"] = trainings
        item["work_type_ids"] = [w["id"] for w in work_types]
        item["training_ids"] = [t["id"] for t in trainings]
        return item


def _set_training_package_links(
    conn,
    training_package_id: int,
    work_type_ids: list[int],
    training_ids: list[int],
) -> None:
    conn.execute(
        "DELETE FROM training_package_work_types WHERE training_package_id = ?",
        (training_package_id,),
    )
    conn.execute(
        "DELETE FROM training_package_sections WHERE training_package_id = ?",
        (training_package_id,),
    )
    for wid in work_type_ids:
        conn.execute(
            "INSERT INTO training_package_work_types "
            "(training_package_id, work_type_id) VALUES (?, ?)",
            (training_package_id, wid),
        )
    for tid in training_ids:
        conn.execute(
            "INSERT INTO training_package_sections "
            "(training_package_id, section_id) VALUES (?, ?)",
            (training_package_id, tid),
        )


def create_training_package(
    data: dict,
    work_type_ids: list[int],
    training_ids: list[int],
    actor_id: Optional[int] = None,
) -> int:
    name = (data.get("name") or "").strip()
    notes = (data.get("notes") or "").strip() or None
    if not name:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO training_packages
            (name, notes, created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, notes, now_iso(), now_iso(), actor_id, actor_id),
        )
        pid = int(cur.lastrowid)
        _set_training_package_links(conn, pid, work_type_ids, training_ids)
        log_activity(
            conn,
            user_id=actor_id,
            action="create",
            entity_type="training_package",
            entity_id=pid,
            details=f"إضافة باقة تدريب: {name}",
        )
        return pid


def update_training_package(
    training_package_id: int,
    data: dict,
    work_type_ids: list[int],
    training_ids: list[int],
    actor_id: Optional[int] = None,
) -> None:
    name = (data.get("name") or "").strip()
    notes = (data.get("notes") or "").strip() or None
    if not name:
        raise ValueError("required")
    with db_session() as conn:
        conn.execute(
            """
            UPDATE training_packages
            SET name = ?, notes = ?, updated_at = ?, updated_by = ?
            WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')
            """,
            (name, notes, now_iso(), actor_id, training_package_id),
        )
        _set_training_package_links(
            conn, training_package_id, work_type_ids, training_ids
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="update",
            entity_type="training_package",
            entity_id=training_package_id,
            details=f"تعديل باقة تدريب: {name}",
        )


def soft_delete_training_package(training_package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM training_packages WHERE id = ? AND {NOT_DELETED}",
            (training_package_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE training_packages
            SET deleted_at = ?, deleted_by = ?, updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, now_iso(), actor_id, training_package_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="delete",
            entity_type="training_package",
            entity_id=training_package_id,
            details=f"حذف باقة تدريب: {row['name']}",
        )
    return True


def restore_training_package(training_package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM training_packages WHERE id = ?",
            (training_package_id,),
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            """
            UPDATE training_packages
            SET deleted_at = NULL, deleted_by = NULL,
                updated_at = ?, updated_by = ?
            WHERE id = ?
            """,
            (now_iso(), actor_id, training_package_id),
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="restore",
            entity_type="training_package",
            entity_id=training_package_id,
            details=f"استرجاع باقة تدريب: {row['name']}",
        )
    return True


def purge_training_package(training_package_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM training_packages WHERE id = ?",
            (training_package_id,),
        ).fetchone()
        if not row or not row["deleted_at"]:
            return False
        conn.execute(
            "DELETE FROM training_package_work_types WHERE training_package_id = ?",
            (training_package_id,),
        )
        conn.execute(
            "DELETE FROM training_package_sections WHERE training_package_id = ?",
            (training_package_id,),
        )
        conn.execute(
            "DELETE FROM training_packages WHERE id = ?", (training_package_id,)
        )
        log_activity(
            conn,
            user_id=actor_id,
            action="purge",
            entity_type="training_package",
            entity_id=training_package_id,
            details=f"حذف نهائي لباقة تدريب: {row['name']}",
        )
    return True


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

def list_trash(q: str = "") -> list[dict]:
    items: list[dict] = []
    like = f"%{q.strip()}%" if q else None
    with db_session() as conn:
        queries = [
            (
                "user",
                "مستخدم",
                f"""
                SELECT id, name AS title, phone AS subtitle, deleted_at, deleted_by
                FROM users WHERE {IS_DELETED}
                """,
            ),
            (
                "system",
                "نظام",
                f"""
                SELECT id, name AS title, abbreviation AS subtitle,
                       deleted_at, deleted_by
                FROM systems WHERE {IS_DELETED}
                """,
            ),
            (
                "work_type",
                "نوع عمل",
                f"""
                SELECT id, name AS title, abbreviation AS subtitle,
                       deleted_at, deleted_by
                FROM work_types WHERE {IS_DELETED}
                """,
            ),
            (
                "package",
                "باقة",
                f"""
                SELECT id, name AS title, notes AS subtitle,
                       deleted_at, deleted_by
                FROM packages WHERE {IS_DELETED}
                """,
            ),
            (
                "training_package",
                "باقة تدريب",
                f"""
                SELECT id, name AS title, notes AS subtitle,
                       deleted_at, deleted_by
                FROM training_packages WHERE {IS_DELETED}
                """,
            ),
            (
                "training_section",
                "قسم تدريب",
                f"""
                SELECT id, title, explanation AS subtitle,
                       deleted_at, deleted_by
                FROM content_sections
                WHERE page = 'training' AND {IS_DELETED}
                """,
            ),
            (
                "problem_section",
                "قسم مشكلة",
                f"""
                SELECT id, title, explanation AS subtitle,
                       deleted_at, deleted_by
                FROM content_sections
                WHERE page = 'problems' AND {IS_DELETED}
                """,
            ),
            (
                "task",
                "مهمة",
                f"""
                SELECT id, title, explanation AS subtitle,
                       deleted_at, deleted_by
                FROM tasks WHERE {IS_DELETED}
                """,
            ),
        ]
        for entity, label, sql in queries:
            for row in conn.execute(sql).fetchall():
                item = dict(row)
                item["entity"] = entity
                item["entity_label"] = label
                if like and like.strip("%"):
                    text = f"{item.get('title') or ''} {item.get('subtitle') or ''}"
                    if like.strip("%").lower() not in text.lower():
                        continue
                items.append(item)
        deleter_ids = {i["deleted_by"] for i in items if i.get("deleted_by")}
        names = _user_names(conn, deleter_ids)
        for item in items:
            item["deleted_by_name"] = names.get(item.get("deleted_by"), "—")
    items.sort(key=lambda r: (r.get("deleted_at") or "", r.get("id") or 0), reverse=True)
    return items


def restore_trash_item(
    entity: str, item_id: int, actor_id: int
) -> tuple[bool, str]:
    handlers = {
        "user": lambda: restore_user(item_id, actor_id=actor_id),
        "system": lambda: (restore_system(item_id, actor_id), ""),
        "work_type": lambda: (restore_work_type(item_id, actor_id), ""),
        "package": lambda: (restore_package(item_id, actor_id), ""),
        "training_package": lambda: (
            restore_training_package(item_id, actor_id),
            "",
        ),
        "training_section": lambda: (restore_section(item_id, actor_id), ""),
        "problem_section": lambda: (restore_section(item_id, actor_id), ""),
        "task": lambda: (restore_task(item_id, actor_id), ""),
    }
    fn = handlers.get(entity)
    if not fn:
        return False, "unknown"
    result = fn()
    if isinstance(result, tuple):
        return result
    return bool(result), "" if result else "not_found"


def purge_trash_item(
    entity: str, item_id: int, actor_id: int
) -> tuple[bool, str]:
    handlers = {
        "user": lambda: purge_user(item_id, actor_id=actor_id),
        "system": lambda: (purge_system(item_id, actor_id), ""),
        "work_type": lambda: (purge_work_type(item_id, actor_id), ""),
        "package": lambda: (purge_package(item_id, actor_id), ""),
        "training_package": lambda: (
            purge_training_package(item_id, actor_id),
            "",
        ),
        "training_section": lambda: (purge_section(item_id, actor_id), ""),
        "problem_section": lambda: (purge_section(item_id, actor_id), ""),
        "task": lambda: (purge_task(item_id, actor_id), ""),
    }
    fn = handlers.get(entity)
    if not fn:
        return False, "unknown"
    result = fn()
    if isinstance(result, tuple):
        return result
    return bool(result), "" if result else "not_found"
