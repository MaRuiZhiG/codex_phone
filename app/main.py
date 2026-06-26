from __future__ import annotations

import logging
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.access_manager import AccessManager
from app.codex_models import CodexModelRepository
from app.codex_session import SessionRepository
from app.config import Settings, load_settings
from app.logging_setup import configure_logging
from app.schemas import AccessModeRequest, InterruptRequest, ModelSelectionRequest, NewThreadRequest, PublicConfigRequest, RemoteConfigRequest, SelectThreadRequest, SendRequest, ZeroTierConfigRequest
from app.security import authorize
from app.windows_gui import GuiAutomationError, WindowsCodexController

settings = load_settings()
configure_logging(settings.log_file)
log = logging.getLogger(__name__)

repo = SessionRepository(settings)
model_repo = CodexModelRepository(settings)
access_manager = AccessManager(settings)
controller = WindowsCodexController(settings)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if getattr(sys, "frozen", False):
    app_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    app_root = Path(__file__).resolve().parent.parent

static_dir = app_root / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _authorize(request: Request) -> None:
    authorize(request, settings)


def _json_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "code": code, "message": message})


def _is_local_request(request: Request) -> bool:
    client_host = (request.client.host if request.client else "") or ""
    return client_host in {"127.0.0.1", "::1", "localhost"}


def _authorize_local(request: Request) -> None:
    if _is_local_request(request):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"ok": False, "code": "LOCAL_ONLY", "message": "This page is only available on the local PC."},
    )


def _build_mobile_link(base_url: str) -> str:
    if not base_url:
        return ""
    return f"{base_url}/?token={settings.token}"


def _resolve_attachment_path(raw_path: str) -> tuple[Path | None, str]:
    if not raw_path:
        return None, ""

    candidate = Path(raw_path.strip())
    if not candidate.is_absolute():
        return None, ""

    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, ""

    media_type, _ = mimetypes.guess_type(resolved.name)
    if not media_type or not media_type.startswith("image/"):
        return None, ""

    return resolved, media_type


def _save_attachments(request: SendRequest) -> list[Path]:
    if len(request.attachments) > settings.max_attachments:
        raise HTTPException(status_code=413, detail={"ok": False, "code": "TOO_MANY_ATTACHMENTS", "message": "Too many attachments."})

    saved: list[Path] = []
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    for index, attachment in enumerate(request.attachments):
        if not attachment.type.lower().startswith("image/"):
            raise HTTPException(status_code=400, detail={"ok": False, "code": "BAD_ATTACHMENT", "message": "Only images are supported."})
        data = controller.decode_attachment_data_url(attachment.data_url)
        if len(data) > settings.max_attachment_bytes:
            raise HTTPException(status_code=413, detail={"ok": False, "code": "ATTACHMENT_TOO_LARGE", "message": "Attachment is too large."})
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in attachment.name)[:80] or f"image-{index}.png"
        path = settings.upload_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{index}-{safe_name}"
        path.write_bytes(data)
        saved.append(path)

    return saved


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return _json_error(exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/admin")
async def admin_page(request: Request) -> FileResponse:
    _authorize_local(request)
    return FileResponse(
        static_dir / "admin.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
async def health(request: Request, _: None = Depends(_authorize)) -> dict:
    return {"ok": True, "service": "codex-phone", "now": _now_iso(), "logFile": str(settings.log_file)}


@app.get("/config")
async def config(request: Request, _: None = Depends(_authorize)) -> dict:
    return {
        "ok": True,
        "service": "codex-phone",
        "appName": settings.app_name,
        "token": settings.token,
        "sessionsDir": str(settings.codex_sessions_dir),
        "desktopLogsDir": str(settings.desktop_logs_dir),
    }


@app.get("/access/status")
async def access_status(request: Request, _: None = Depends(_authorize)) -> dict:
    return access_manager.read_status()


@app.get("/admin/bootstrap")
async def admin_bootstrap(request: Request) -> dict:
    _authorize_local(request)
    access = access_manager.read_status()
    return {
        "ok": True,
        "service": "codex-phone",
        "appName": settings.app_name,
        "token": settings.token,
        "port": settings.port,
        "host": settings.host,
        "stateDir": str(settings.state_dir),
        "logFile": str(settings.log_file),
        "access": {
            **access,
            "lanLink": _build_mobile_link(access.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(access.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(access.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(access.get("effectiveUrl", "")),
        },
    }


@app.post("/admin/access/mode")
async def admin_access_mode_update(request: Request, payload: AccessModeRequest) -> dict:
    _authorize_local(request)
    try:
        result = access_manager.set_mode(payload.mode)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_ACCESS_MODE", str(exc))
    return {
        "ok": True,
        "message": "Access mode updated.",
        "access": {
            **result,
            "lanLink": _build_mobile_link(result.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(result.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(result.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(result.get("effectiveUrl", "")),
        },
    }


@app.post("/admin/access/public/config")
async def admin_access_public_config(request: Request, payload: PublicConfigRequest) -> dict:
    _authorize_local(request)
    try:
        result = access_manager.configure_public(payload.public_url, payload.enabled, payload.provider)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_PUBLIC_CONFIG", str(exc))
    return {
        "ok": True,
        "message": "Public access config updated.",
        "access": {
            **result,
            "lanLink": _build_mobile_link(result.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(result.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(result.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(result.get("effectiveUrl", "")),
        },
    }


@app.post("/admin/access/zerotier/config")
async def admin_access_zerotier_config(request: Request, payload: ZeroTierConfigRequest) -> dict:
    _authorize_local(request)
    try:
        result = access_manager.configure_zerotier(payload.zerotier_ip, payload.zerotier_port, payload.enabled)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_ZEROTIER_CONFIG", str(exc))
    return {
        "ok": True,
        "message": "ZeroTier access config updated.",
        "access": {
            **result,
            "lanLink": _build_mobile_link(result.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(result.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(result.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(result.get("effectiveUrl", "")),
        },
    }


@app.post("/admin/access/check")
async def admin_access_check(request: Request) -> dict:
    _authorize_local(request)
    result = access_manager.read_status()
    return {
        "ok": True,
        "message": "Access status refreshed.",
        "access": {
            **result,
            "lanLink": _build_mobile_link(result.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(result.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(result.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(result.get("effectiveUrl", "")),
        },
    }


@app.post("/admin/access/zerotier/check")
async def admin_access_zerotier_check(request: Request) -> dict:
    _authorize_local(request)
    result = access_manager.check_zerotier()
    return {
        "ok": True,
        "message": "ZeroTier access checked.",
        "access": {
            **result,
            "lanLink": _build_mobile_link(result.get("lanUrl", "")),
            "zerotierLink": _build_mobile_link(result.get("zerotierUrl", "")),
            "publicLink": _build_mobile_link(result.get("publicUrl", "")),
            "effectiveLink": _build_mobile_link(result.get("effectiveUrl", "")),
        },
    }


@app.post("/access/mode")
async def access_mode_update(request: Request, payload: AccessModeRequest, _: None = Depends(_authorize)) -> dict:
    try:
        result = access_manager.set_mode(payload.mode)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_ACCESS_MODE", str(exc))
    return {
        **result,
        "message": "Access mode updated.",
    }


@app.post("/access/public/config")
async def access_public_config(request: Request, payload: PublicConfigRequest, _: None = Depends(_authorize)) -> dict:
    try:
        result = access_manager.configure_public(payload.public_url, payload.enabled, payload.provider)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_PUBLIC_CONFIG", str(exc))
    return {
        **result,
        "message": "Public access config updated.",
    }


@app.post("/access/remote/config")
async def access_remote_config_legacy(request: Request, payload: RemoteConfigRequest, _: None = Depends(_authorize)) -> dict:
    try:
        remote_url = payload.remote_url or payload.public_url
        result = access_manager.configure_public(remote_url, payload.enabled, payload.provider)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_REMOTE_CONFIG", str(exc))
    return {
        **result,
        "message": "Remote access config updated.",
    }


@app.post("/access/public/check")
async def access_public_check(request: Request, _: None = Depends(_authorize)) -> dict:
    return access_manager.check_public()


@app.post("/access/remote/check")
async def access_remote_check_legacy(request: Request, _: None = Depends(_authorize)) -> dict:
    return access_manager.check_public()


@app.post("/access/zerotier/config")
async def access_zerotier_config(request: Request, payload: ZeroTierConfigRequest, _: None = Depends(_authorize)) -> dict:
    try:
        result = access_manager.configure_zerotier(payload.zerotier_ip, payload.zerotier_port, payload.enabled)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_ZEROTIER_CONFIG", str(exc))
    return {
        **result,
        "message": "ZeroTier access config updated.",
    }


@app.post("/access/zerotier/check")
async def access_zerotier_check(request: Request, _: None = Depends(_authorize)) -> dict:
    return access_manager.check_zerotier()


@app.get("/codex/threads")
async def codex_threads(request: Request, limit: int = 80, _: None = Depends(_authorize)) -> dict:
    return {"ok": True, "threads": repo.list_threads(max(1, min(limit, 120)))}


@app.get("/codex/history")
async def codex_history(request: Request, thread: str, limit: int = 80, _: None = Depends(_authorize)) -> dict:
    if not repo.is_thread_id(thread):
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_THREAD_ID", "Invalid thread id.")
    return repo.parse_history(thread, max(1, min(limit, 120)))


@app.get("/codex/attachment")
async def codex_attachment(request: Request, path: str, _: None = Depends(_authorize)):
    resolved, media_type = _resolve_attachment_path(path)
    if not resolved:
        return _json_error(status.HTTP_404_NOT_FOUND, "ATTACHMENT_NOT_FOUND", "Attachment image is unavailable.")
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get("/codex/status")
async def codex_status(
    request: Request,
    thread: str = "",
    session: str = "",
    since: str = "",
    _: None = Depends(_authorize),
) -> dict:
    return repo.parse_status(thread_id=thread, session_file=session, since=since)


@app.get("/codex/models")
async def codex_models(request: Request, _: None = Depends(_authorize)) -> dict:
    return model_repo.read_model_info()


@app.post("/codex/models")
async def codex_models_update(request: Request, payload: ModelSelectionRequest, _: None = Depends(_authorize)) -> dict:
    try:
        result = model_repo.write_model_selection(payload.model, payload.effort)
    except ValueError as exc:
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_MODEL_SELECTION", str(exc))
    except OSError as exc:
        log.exception("Failed to update Codex model selection.")
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "MODEL_UPDATE_FAILED", str(exc))
    return {
        **result,
        "message": "Codex model config updated.",
    }


@app.post("/codex/select")
async def codex_select(request: Request, payload: SelectThreadRequest, _: None = Depends(_authorize)) -> dict:
    if not repo.is_thread_id(payload.thread_id):
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_THREAD_ID", "Invalid thread id.")
    try:
        controller.focus_codex(payload.thread_id)
    except GuiAutomationError as exc:
        log.exception("Failed to select thread %s", payload.thread_id)
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "CODEX_FOCUS_FAILED", str(exc))
    return {"ok": True, "threadId": payload.thread_id, "message": "Codex thread activated."}


@app.post("/codex/new-thread")
async def codex_new_thread(request: Request, payload: NewThreadRequest, _: None = Depends(_authorize)) -> dict:
    try:
        controller.open_new_thread(payload.project_path)
    except GuiAutomationError as exc:
        log.exception("Failed to create new thread.")
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "CODEX_NEW_THREAD_FAILED", str(exc))
    return {"ok": True, "pending": True, "projectPath": payload.project_path, "message": "Opened a new Codex thread."}


@app.post("/codex/interrupt")
async def codex_interrupt(request: Request, payload: InterruptRequest, _: None = Depends(_authorize)) -> dict:
    if payload.thread_id and not repo.is_thread_id(payload.thread_id):
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_THREAD_ID", "Invalid thread id.")
    try:
        controller.interrupt(payload.thread_id)
    except GuiAutomationError as exc:
        log.exception("Failed to interrupt thread %s", payload.thread_id)
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "CODEX_INTERRUPT_FAILED", str(exc))
    return {"ok": True, "threadId": payload.thread_id, "interruptedAt": _now_iso(), "message": "Interrupt signal sent to Codex Desktop."}


@app.post("/send")
async def send(request: Request, payload: SendRequest, _: None = Depends(_authorize)) -> dict:
    text = payload.text or ""
    if len(text) > settings.max_text_length:
        return _json_error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "TEXT_TOO_LONG", "Text is too long.")
    if not text.strip() and not payload.attachments:
        return _json_error(status.HTTP_400_BAD_REQUEST, "EMPTY_MESSAGE", "Message is empty.")
    if payload.thread_id and not repo.is_thread_id(payload.thread_id):
        return _json_error(status.HTTP_400_BAD_REQUEST, "BAD_THREAD_ID", "Invalid thread id.")

    attachments = _save_attachments(payload)
    watch_file = repo.find_file_by_thread_id(payload.thread_id) if payload.thread_id else repo.find_latest_file()
    previous_watch_thread = repo.thread_id_from_file(watch_file) if watch_file else ""
    previous_watch_mtime = watch_file.stat().st_mtime if watch_file else 0.0
    watch = {
        "threadId": payload.thread_id,
        "sessionFile": watch_file.name if watch_file else "",
        "since": _now_iso(),
    }

    try:
        controller.send_message(text=text, attachments=attachments, thread_id=payload.thread_id)
        log.info("Sent phone message to Codex thread=%s text_len=%s attachments=%s", payload.thread_id, len(text), len(attachments))
    except GuiAutomationError as exc:
        log.exception("Send failed")
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "SEND_FAILED", str(exc))
    except Exception as exc:  # pragma: no cover - diagnostic path for local Windows automation
        log.exception("Send failed with unexpected error")
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "SEND_FAILED", f"{type(exc).__name__}: {exc}")

    if not watch["threadId"]:
        latest = repo.wait_for_latest_file(previous_thread_id=previous_watch_thread, previous_mtime=previous_watch_mtime)
        if latest:
            watch["threadId"] = repo.thread_id_from_file(latest)
            watch["sessionFile"] = latest.name

    return {
        "ok": True,
        "message": "Message pasted into Codex Desktop.",
        "target": "codex",
        "sentAt": _now_iso(),
        "watch": watch,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
