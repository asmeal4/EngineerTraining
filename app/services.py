"""Business logic for EngineerTraining."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .auth import hash_password
from .config import WORK_TYPE_UPLOADS
from .database import db_session, now_iso, role_label

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

def dashboard_stats() -> dict:
    with db_session() as conn:
        def count(table: str) -> int:
            return conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {NOT_DELETED}"
            ).fetchone()["c"]

        trash = 0
        for table in ("users", "systems", "work_types", "packages"):
            trash += conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {IS_DELETED}"
            ).fetchone()["c"]

        return {
            "user_count": count("users"),
            "system_count": count("systems"),
            "work_type_count": count("work_types"),
            "package_count": count("packages"),
            "trash_count": trash,
            "active_users": conn.execute(
                f"SELECT COUNT(*) AS c FROM users WHERE is_active = 1 AND {NOT_DELETED}"
            ).fetchone()["c"],
        }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def list_users(q: str = "") -> list[dict]:
    clauses = ["(u.deleted_at IS NULL OR u.deleted_at = '')"]
    params: list[Any] = []
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
            ORDER BY u.id
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
    clauses = [NOT_DELETED]
    params: list[Any] = []
    if q:
        clauses.append("(w.name LIKE ? OR w.abbreviation LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like])
    where = " AND ".join(c.replace("deleted_at", "w.deleted_at") if "deleted_at" in c else c for c in clauses)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT w.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM work_types w
            LEFT JOIN users cb ON cb.id = w.created_by
            LEFT JOIN users ub ON ub.id = w.updated_by
            WHERE {where}
            ORDER BY w.name
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


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
    has_explanation = 1 if data.get("has_explanation") else 0
    explanation = (data.get("explanation") or "").strip() or None
    image_path = data.get("image_path")
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO work_types
            (name, abbreviation, has_explanation, explanation, image_path,
             created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                abbr,
                has_explanation,
                explanation if has_explanation else None,
                image_path if has_explanation else None,
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
    has_explanation = 1 if data.get("has_explanation") else 0
    explanation = (data.get("explanation") or "").strip() or None
    if not name or not abbr:
        raise ValueError("required")
    with db_session() as conn:
        existing = conn.execute(
            f"SELECT * FROM work_types WHERE id = ? AND {NOT_DELETED}",
            (work_type_id,),
        ).fetchone()
        if not existing:
            raise ValueError("not_found")
        image_path = data.get("image_path")
        if image_path is None:
            image_path = existing["image_path"]
        if not has_explanation:
            explanation = None
            # keep image unless explicitly cleared — plan says one image when enabled
        fields = """
            name = ?, abbreviation = ?, has_explanation = ?,
            explanation = ?, updated_at = ?, updated_by = ?
        """
        values: list[Any] = [
            name,
            abbr,
            has_explanation,
            explanation if has_explanation else None,
            now_iso(),
            actor_id,
        ]
        if "image_path" in data:
            fields += ", image_path = ?"
            values.append(data["image_path"] if has_explanation else None)
        elif not has_explanation:
            fields += ", image_path = ?"
            values.append(None)
        values.append(work_type_id)
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


def soft_delete_work_type(work_type_id: int, actor_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            f"SELECT * FROM work_types WHERE id = ? AND {NOT_DELETED}",
            (work_type_id,),
        ).fetchone()
        if not row:
            return False
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
    if image_path:
        path = Path(image_path)
        if not path.is_absolute():
            path = WORK_TYPE_UPLOADS.parent.parent / image_path
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    return True


# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------

def _package_links(conn, package_id: int) -> tuple[list[dict], list[dict]]:
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
        ORDER BY w.name
        """,
        (package_id,),
    ).fetchall()
    return [dict(r) for r in systems], [dict(r) for r in work_types]


def list_packages(q: str = "") -> list[dict]:
    clauses = [NOT_DELETED]
    params: list[Any] = []
    if q:
        clauses.append("(p.name LIKE ? OR p.notes LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like])
    where = " AND ".join(
        c.replace("deleted_at", "p.deleted_at") if "deleted_at" in c else c
        for c in clauses
    )
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*,
                   cb.name AS created_by_name,
                   ub.name AS updated_by_name
            FROM packages p
            LEFT JOIN users cb ON cb.id = p.created_by
            LEFT JOIN users ub ON ub.id = p.updated_by
            WHERE {where}
            ORDER BY p.name
            """,
            params,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            systems, work_types = _package_links(conn, item["id"])
            item["systems"] = systems
            item["work_types"] = work_types
            item["system_ids"] = [s["id"] for s in systems]
            item["work_type_ids"] = [w["id"] for w in work_types]
            result.append(item)
    return result


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
        systems, work_types = _package_links(conn, package_id)
        item["systems"] = systems
        item["work_types"] = work_types
        item["system_ids"] = [s["id"] for s in systems]
        item["work_type_ids"] = [w["id"] for w in work_types]
        return item


def _set_package_links(
    conn, package_id: int, system_ids: list[int], work_type_ids: list[int]
) -> None:
    conn.execute(
        "DELETE FROM package_systems WHERE package_id = ?", (package_id,)
    )
    conn.execute(
        "DELETE FROM package_work_types WHERE package_id = ?", (package_id,)
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


def create_package(
    data: dict,
    system_ids: list[int],
    work_type_ids: list[int],
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
        _set_package_links(conn, pid, system_ids, work_type_ids)
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
        _set_package_links(conn, package_id, system_ids, work_type_ids)
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
    }
    fn = handlers.get(entity)
    if not fn:
        return False, "unknown"
    result = fn()
    if isinstance(result, tuple):
        return result
    return bool(result), "" if result else "not_found"
