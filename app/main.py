from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import auth, backup, services
from .config import BASE_DIR, HTTPS_ONLY, SECRET_KEY, SESSION_COOKIE, WORK_TYPE_UPLOADS
from .database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="تدريب المهندسين", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie=SESSION_COOKIE,
    same_site="lax",
    https_only=HTTPS_ONLY,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount(
    "/uploads",
    StaticFiles(directory=str(BASE_DIR / "data" / "uploads")),
    name="uploads",
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return render(
            request,
            "404.html",
            {"path": request.url.path},
            status_code=404,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def flash(
    request: Request,
    message: str,
    category: str = "success",
    detail: Optional[str] = None,
) -> None:
    payload = {"message": message, "category": category}
    if detail:
        payload["detail"] = detail
    request.session["flash"] = payload


def pop_flash(request: Request) -> Optional[dict]:
    return request.session.pop("flash", None)


def render(request: Request, name: str, context: Optional[dict] = None, status_code: int = 200):
    user = auth.get_current_user(request)
    ctx = {
        "request": request,
        "flash": pop_flash(request),
        "user_logged_in": auth.is_logged_in(request) and user is not None,
        "current_user": user,
        "is_admin": auth.is_admin(request),
        "today": date.today().isoformat(),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(name, ctx, status_code=status_code)


def current_user_id(request: Request) -> Optional[int]:
    user = auth.get_current_user(request)
    return int(user["id"]) if user else None


def deny_purge(request: Request, list_url: str):
    if not auth.is_admin(request):
        flash(request, "ليس لديك صلاحية الحذف النهائي", "error")
        return RedirectResponse(list_url, status_code=303)
    return None


def parse_id_list(form, field: str) -> list[int]:
    values = form.getlist(field)
    result = []
    for v in values:
        try:
            result.append(int(v))
        except (TypeError, ValueError):
            continue
    return result


async def save_work_type_image(upload: Optional[UploadFile]) -> Optional[str]:
    if not upload or not upload.filename:
        return None
    ext = Path(upload.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        raise ValueError("invalid_image")
    name = f"{uuid4().hex}{ext}"
    dest = WORK_TYPE_UPLOADS / name
    content = await upload.read()
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("image_too_large")
    dest.write_bytes(content)
    return f"work_types/{name}"


@app.get("/favicon.ico")
def favicon():
    return FileResponse(
        BASE_DIR / "static" / "favicon.svg",
        media_type="image/svg+xml",
    )


# --- Auth ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if auth.is_logged_in(request) and auth.get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", {"next": next or "/"})


@app.post("/login")
def login_submit(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = auth.authenticate(phone, password)
    if user:
        auth.login_user(request, user)
        flash(request, "تم تسجيل الدخول بنجاح")
        target = next if next.startswith("/") else "/"
        return RedirectResponse(target, status_code=303)
    flash(request, "رقم الجوال أو كلمة المرور غير صحيحة", "error")
    return RedirectResponse("/login", status_code=303)


@app.get("/logout")
def logout(request: Request):
    auth.logout_user(request)
    return RedirectResponse("/login", status_code=303)


# --- Dashboard ---

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    return render(request, "dashboard.html", {"stats": services.dashboard_stats()})


# --- Users ---

@app.get("/users", response_class=HTMLResponse)
def users_list(request: Request, q: str = ""):
    if (redir := auth.require_login(request)):
        return redir
    return render(
        request,
        "users.html",
        {"users": services.list_users(q), "q": q},
    )


@app.get("/users/new", response_class=HTMLResponse)
def users_new(request: Request):
    if (redir := auth.require_admin(request)):
        return redir
    return render(request, "user_form.html", {"user": None, "mode": "new"})


@app.post("/users/new")
async def users_create(request: Request):
    if (redir := auth.require_admin(request)):
        return redir
    form = await request.form()
    try:
        services.create_user(
            {
                "name": form.get("name"),
                "phone": form.get("phone"),
                "password": form.get("password"),
                "role": form.get("role") or "user",
                "is_active": form.get("is_active") == "1",
            },
            actor_id=current_user_id(request),
        )
        flash(request, "تم إضافة المستخدم")
        return RedirectResponse("/users", status_code=303)
    except ValueError as e:
        msg = {
            "password_required": "كلمة المرور مطلوبة",
            "required": "الاسم ورقم الجوال مطلوبان",
        }.get(str(e), "تعذر الحفظ")
        flash(request, msg, "error")
        return RedirectResponse("/users/new", status_code=303)
    except Exception:
        flash(request, "تعذر الحفظ — ربما رقم الجوال مستخدم", "error")
        return RedirectResponse("/users/new", status_code=303)


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
def users_edit(request: Request, user_id: int):
    if (redir := auth.require_login(request)):
        return redir
    user = services.get_user_record(user_id)
    if not user or user.get("deleted_at"):
        flash(request, "المستخدم غير موجود", "error")
        return RedirectResponse("/users", status_code=303)
    actor = auth.get_current_user(request)
    if not auth.is_admin(request) and actor and actor["id"] != user_id:
        flash(request, "ليس لديك صلاحية تعديل هذا المستخدم", "error")
        return RedirectResponse("/users", status_code=303)
    return render(request, "user_form.html", {"user": user, "mode": "edit"})


@app.post("/users/{user_id}/edit")
async def users_update(request: Request, user_id: int):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        services.update_user(
            user_id,
            {
                "name": form.get("name"),
                "phone": form.get("phone"),
                "password": form.get("password"),
                "role": form.get("role") or "user",
                "is_active": form.get("is_active") == "1",
            },
            actor_id=current_user_id(request),
            actor_is_admin=auth.is_admin(request),
        )
        flash(request, "تم التعديل")
        return RedirectResponse("/users", status_code=303)
    except PermissionError:
        flash(request, "ليس لديك صلاحية لهذا التعديل", "error")
    except ValueError as e:
        msg = {
            "last_admin_role": "لا يمكن جعل كل المستخدمين عاديين — يجب بقاء مدير واحد على الأقل",
            "last_admin_deactivate": "لا يمكن إيقاف آخر مدير نشط",
            "required": "الاسم ورقم الجوال مطلوبان",
            "not_found": "المستخدم غير موجود",
        }.get(str(e), "تعذر التعديل")
        flash(request, msg, "error")
    except Exception:
        flash(request, "تعذر التعديل — ربما رقم الجوال مستخدم", "error")
    return RedirectResponse(f"/users/{user_id}/edit", status_code=303)


@app.post("/users/{user_id}/delete")
def users_delete(request: Request, user_id: int):
    if (redir := auth.require_login(request)):
        return redir
    ok, err = services.soft_delete_user(
        user_id,
        actor_id=current_user_id(request) or 0,
        actor_is_admin=auth.is_admin(request),
    )
    if ok:
        flash(request, "تم نقل المستخدم إلى سلة المحذوفات")
    else:
        msg = {
            "forbidden": "ليس لديك صلاحية حذف المستخدمين",
            "last_admin": "لا يمكن حذف آخر مدير",
            "not_found": "المستخدم غير موجود",
        }.get(err, "تعذر الحذف")
        flash(request, msg, "error")
    return RedirectResponse("/users", status_code=303)


# --- Systems ---

@app.get("/systems", response_class=HTMLResponse)
def systems_list(request: Request, q: str = ""):
    if (redir := auth.require_login(request)):
        return redir
    return render(
        request,
        "systems.html",
        {"systems": services.list_systems(q), "q": q},
    )


@app.get("/systems/new", response_class=HTMLResponse)
def systems_new(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    return render(request, "system_form.html", {"system": None, "mode": "new"})


@app.post("/systems/new")
async def systems_create(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        services.create_system(
            {
                "name": form.get("name"),
                "abbreviation": form.get("abbreviation"),
                "sort_order": form.get("sort_order") or 0,
            },
            actor_id=current_user_id(request),
        )
        flash(request, "تم إضافة النظام")
        return RedirectResponse("/systems", status_code=303)
    except ValueError:
        flash(request, "الاسم والاختصار مطلوبان", "error")
        return RedirectResponse("/systems/new", status_code=303)


@app.get("/systems/{system_id}/edit", response_class=HTMLResponse)
def systems_edit(request: Request, system_id: int):
    if (redir := auth.require_login(request)):
        return redir
    system = services.get_system(system_id)
    if not system or system.get("deleted_at"):
        flash(request, "النظام غير موجود", "error")
        return RedirectResponse("/systems", status_code=303)
    return render(request, "system_form.html", {"system": system, "mode": "edit"})


@app.post("/systems/{system_id}/edit")
async def systems_update(request: Request, system_id: int):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        services.update_system(
            system_id,
            {
                "name": form.get("name"),
                "abbreviation": form.get("abbreviation"),
                "sort_order": form.get("sort_order") or 0,
            },
            actor_id=current_user_id(request),
        )
        flash(request, "تم التعديل")
        return RedirectResponse("/systems", status_code=303)
    except ValueError:
        flash(request, "الاسم والاختصار مطلوبان", "error")
        return RedirectResponse(f"/systems/{system_id}/edit", status_code=303)


@app.post("/systems/{system_id}/delete")
def systems_delete(request: Request, system_id: int):
    if (redir := auth.require_login(request)):
        return redir
    if services.soft_delete_system(system_id, current_user_id(request) or 0):
        flash(request, "تم النقل إلى سلة المحذوفات")
    else:
        flash(request, "تعذر الحذف", "error")
    return RedirectResponse("/systems", status_code=303)


# --- Work types ---

@app.get("/work-types", response_class=HTMLResponse)
def work_types_list(request: Request, q: str = ""):
    if (redir := auth.require_login(request)):
        return redir
    return render(
        request,
        "work_types.html",
        {"work_types": services.list_work_types(q), "q": q},
    )


@app.get("/work-types/new", response_class=HTMLResponse)
def work_types_new(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    return render(request, "work_type_form.html", {"work_type": None, "mode": "new"})


@app.post("/work-types/new")
async def work_types_create(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        image_path = None
        upload = form.get("image")
        if upload and getattr(upload, "filename", None):
            image_path = await save_work_type_image(upload)
        services.create_work_type(
            {
                "name": form.get("name"),
                "abbreviation": form.get("abbreviation"),
                "has_explanation": form.get("has_explanation") == "1",
                "explanation": form.get("explanation"),
                "image_path": image_path,
            },
            actor_id=current_user_id(request),
        )
        flash(request, "تم إضافة نوع العمل")
        return RedirectResponse("/work-types", status_code=303)
    except ValueError as e:
        msg = {
            "required": "الاسم والاختصار مطلوبان",
            "invalid_image": "صيغة الصورة غير مدعومة",
            "image_too_large": "حجم الصورة كبير جداً",
        }.get(str(e), "تعذر الحفظ")
        flash(request, msg, "error")
        return RedirectResponse("/work-types/new", status_code=303)


@app.get("/work-types/{work_type_id}/edit", response_class=HTMLResponse)
def work_types_edit(request: Request, work_type_id: int):
    if (redir := auth.require_login(request)):
        return redir
    work_type = services.get_work_type(work_type_id)
    if not work_type or work_type.get("deleted_at"):
        flash(request, "نوع العمل غير موجود", "error")
        return RedirectResponse("/work-types", status_code=303)
    return render(
        request,
        "work_type_form.html",
        {"work_type": work_type, "mode": "edit"},
    )


@app.post("/work-types/{work_type_id}/edit")
async def work_types_update(request: Request, work_type_id: int):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        data = {
            "name": form.get("name"),
            "abbreviation": form.get("abbreviation"),
            "has_explanation": form.get("has_explanation") == "1",
            "explanation": form.get("explanation"),
        }
        upload = form.get("image")
        if upload and getattr(upload, "filename", None):
            data["image_path"] = await save_work_type_image(upload)
        if form.get("clear_image") == "1":
            data["image_path"] = None
        services.update_work_type(
            work_type_id, data, actor_id=current_user_id(request)
        )
        flash(request, "تم التعديل")
        return RedirectResponse("/work-types", status_code=303)
    except ValueError as e:
        msg = {
            "required": "الاسم والاختصار مطلوبان",
            "not_found": "غير موجود",
            "invalid_image": "صيغة الصورة غير مدعومة",
            "image_too_large": "حجم الصورة كبير جداً",
        }.get(str(e), "تعذر التعديل")
        flash(request, msg, "error")
        return RedirectResponse(f"/work-types/{work_type_id}/edit", status_code=303)


@app.post("/work-types/{work_type_id}/delete")
def work_types_delete(request: Request, work_type_id: int):
    if (redir := auth.require_login(request)):
        return redir
    if services.soft_delete_work_type(work_type_id, current_user_id(request) or 0):
        flash(request, "تم النقل إلى سلة المحذوفات")
    else:
        flash(request, "تعذر الحذف", "error")
    return RedirectResponse("/work-types", status_code=303)


# --- Packages ---

@app.get("/packages", response_class=HTMLResponse)
def packages_list(request: Request, q: str = ""):
    if (redir := auth.require_login(request)):
        return redir
    return render(
        request,
        "packages.html",
        {"packages": services.list_packages(q), "q": q},
    )


@app.get("/packages/new", response_class=HTMLResponse)
def packages_new(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    return render(
        request,
        "package_form.html",
        {
            "package": None,
            "mode": "new",
            "all_systems": services.list_systems(),
            "all_work_types": services.list_work_types(),
        },
    )


@app.post("/packages/new")
async def packages_create(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        services.create_package(
            {"name": form.get("name"), "notes": form.get("notes")},
            parse_id_list(form, "system_ids"),
            parse_id_list(form, "work_type_ids"),
            actor_id=current_user_id(request),
        )
        flash(request, "تم إضافة الباقة")
        return RedirectResponse("/packages", status_code=303)
    except ValueError:
        flash(request, "اسم الباقة مطلوب", "error")
        return RedirectResponse("/packages/new", status_code=303)


@app.get("/packages/{package_id}/edit", response_class=HTMLResponse)
def packages_edit(request: Request, package_id: int):
    if (redir := auth.require_login(request)):
        return redir
    package = services.get_package(package_id)
    if not package or package.get("deleted_at"):
        flash(request, "الباقة غير موجودة", "error")
        return RedirectResponse("/packages", status_code=303)
    return render(
        request,
        "package_form.html",
        {
            "package": package,
            "mode": "edit",
            "all_systems": services.list_systems(),
            "all_work_types": services.list_work_types(),
        },
    )


@app.post("/packages/{package_id}/edit")
async def packages_update(request: Request, package_id: int):
    if (redir := auth.require_login(request)):
        return redir
    form = await request.form()
    try:
        services.update_package(
            package_id,
            {"name": form.get("name"), "notes": form.get("notes")},
            parse_id_list(form, "system_ids"),
            parse_id_list(form, "work_type_ids"),
            actor_id=current_user_id(request),
        )
        flash(request, "تم التعديل")
        return RedirectResponse("/packages", status_code=303)
    except ValueError:
        flash(request, "اسم الباقة مطلوب", "error")
        return RedirectResponse(f"/packages/{package_id}/edit", status_code=303)


@app.post("/packages/{package_id}/delete")
def packages_delete(request: Request, package_id: int):
    if (redir := auth.require_login(request)):
        return redir
    if services.soft_delete_package(package_id, current_user_id(request) or 0):
        flash(request, "تم النقل إلى سلة المحذوفات")
    else:
        flash(request, "تعذر الحذف", "error")
    return RedirectResponse("/packages", status_code=303)


# --- Trash ---

@app.get("/trash", response_class=HTMLResponse)
def trash_list(request: Request, q: str = ""):
    if (redir := auth.require_login(request)):
        return redir
    return render(request, "trash.html", {"items": services.list_trash(q), "q": q})


@app.post("/trash/{entity}/{item_id}/restore")
def trash_restore(request: Request, entity: str, item_id: int):
    if (redir := auth.require_login(request)):
        return redir
    ok, err = services.restore_trash_item(
        entity, item_id, current_user_id(request) or 0
    )
    if ok:
        flash(request, "تم الاسترجاع")
    else:
        flash(request, "تعذر الاسترجاع", "error")
    return RedirectResponse("/trash", status_code=303)


@app.post("/trash/{entity}/{item_id}/purge")
def trash_purge(request: Request, entity: str, item_id: int):
    if (redir := auth.require_login(request)):
        return redir
    if (denied := deny_purge(request, "/trash")):
        return denied
    ok, err = services.purge_trash_item(
        entity, item_id, current_user_id(request) or 0
    )
    if ok:
        flash(request, "تم الحذف النهائي")
    else:
        msg = {
            "last_admin": "لا يمكن حذف آخر مدير نهائياً",
            "not_in_trash": "العنصر ليس في السلة",
        }.get(err, "تعذر الحذف النهائي")
        flash(request, msg, "error")
    return RedirectResponse("/trash", status_code=303)


# --- Activity ---

ACTIVITY_BUILD = "activity-clear-v4"


@app.get("/activity", response_class=HTMLResponse)
def activity_list(
    request: Request,
    q: str = "",
    user_id: str = "",
    action: str = "",
    entity_type: str = "",
    date_from: str = "",
    date_to: str = "",
    confirm_clear: str = "",
):
    if (redir := auth.require_login(request)):
        return redir
    uid = int(user_id) if user_id.isdigit() else None
    return render(
        request,
        "activity.html",
        {
            "items": services.list_activity(
                q=q,
                user_id=uid,
                action=action,
                entity_type=entity_type,
                date_from=date_from,
                date_to=date_to,
            ),
            "q": q,
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "date_from": date_from,
            "date_to": date_to,
            "users": services.list_users(),
            "actions": services.ACTION_LABELS,
            "entities": services.ENTITY_LABELS,
            "confirm_clear": confirm_clear,
        },
    )


@app.post("/activity")
async def activity_actions(request: Request):
    """Clear actions post to /activity so they work after reload on same path."""
    if (redir := auth.require_admin(request)):
        return redir
    form = await request.form()
    intent = (form.get("intent") or "").strip()
    if intent == "clear_all":
        deleted = services.clear_activity_log()
        flash(request, f"تم مسح سجل النشاط بالكامل ({deleted} سجل)")
    elif intent == "clear_older":
        raw = (form.get("days") or "60").strip()
        try:
            days = max(1, int(raw))
        except (TypeError, ValueError):
            days = 60
        deleted = services.clear_activity_older_than(days)
        flash(request, f"تم حذف السجلات الأقدم من {days} يوم ({deleted} سجل)")
    else:
        flash(request, "عملية غير معروفة", "error")
    return RedirectResponse("/activity", status_code=303)


@app.get("/health")
def health():
    return JSONResponse(
        {
            "ok": True,
            "app": "EngineerTraining",
            "activity_clear": True,
            "build": ACTIVITY_BUILD,
        }
    )


# --- Backup ---

@app.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request):
    if (redir := auth.require_login(request)):
        return redir
    return render(request, "backup.html")


@app.get("/backup/download/db")
def backup_download_db(request: Request, background_tasks: BackgroundTasks):
    if (redir := auth.require_login(request)):
        return redir
    path, filename = backup.create_database_backup()
    background_tasks.add_task(lambda p=path: p.unlink(missing_ok=True))
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/backup/download/images")
def backup_download_images(request: Request, background_tasks: BackgroundTasks):
    if (redir := auth.require_login(request)):
        return redir
    path, filename = backup.create_images_backup()
    background_tasks.add_task(lambda p=path: p.unlink(missing_ok=True))
    return FileResponse(
        path,
        filename=filename,
        media_type="application/zip",
    )


@app.post("/backup/restore/db")
async def backup_restore_db(request: Request, backup_file: UploadFile = File(...)):
    if (redir := auth.require_admin(request)):
        return redir
    import tempfile
    import os
    import logging

    original_name = (backup_file.filename or "").lower()
    suffix = ".zip" if original_name.endswith(".zip") else ".db"
    fd, temp_name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        content = await backup_file.read()
        if not content:
            flash(request, "الملف فارغ أو لم يُرفع بشكل صحيح", "error")
            return RedirectResponse("/backup", status_code=303)
        temp_path.write_bytes(content)
        backup.restore_database_only(temp_path)
        flash(request, "تم استرجاع قاعدة البيانات بنجاح")
    except ValueError as e:
        msg = {
            "file_too_large": "الملف كبير جداً (الحد 100 ميجابايت)",
            "invalid_database": "ملف قاعدة بيانات غير صالح",
        }.get(str(e), "تعذر استرجاع قاعدة البيانات")
        flash(request, msg, "error")
    except Exception as e:
        logging.getLogger(__name__).exception("database restore failed")
        flash(request, f"تعذر استرجاع قاعدة البيانات: {type(e).__name__}", "error")
    finally:
        temp_path.unlink(missing_ok=True)
    return RedirectResponse("/backup", status_code=303)


@app.post("/backup/restore/images")
async def backup_restore_images(request: Request, backup_file: UploadFile = File(...)):
    if (redir := auth.require_admin(request)):
        return redir
    import tempfile
    import os
    import logging

    fd, temp_name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        content = await backup_file.read()
        if not content:
            flash(request, "الملف فارغ أو لم يُرفع بشكل صحيح", "error")
            return RedirectResponse("/backup", status_code=303)
        temp_path.write_bytes(content)
        backup.restore_images_only(temp_path)
        flash(request, "تم استرجاع الصور بنجاح")
    except ValueError as e:
        msg = {
            "file_too_large": "الملف كبير جداً (الحد 100 ميجابايت)",
            "invalid_images": "ملف صور غير صالح",
            "uploads_restore_failed": "تعذر استرجاع الصور",
        }.get(str(e), "تعذر استرجاع الصور")
        flash(request, msg, "error")
    except Exception as e:
        logging.getLogger(__name__).exception("images restore failed")
        flash(request, f"تعذر استرجاع الصور: {type(e).__name__}", "error")
    finally:
        temp_path.unlink(missing_ok=True)
    return RedirectResponse("/backup", status_code=303)
