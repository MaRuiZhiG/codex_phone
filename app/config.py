from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser() if value else default


def _stable_token(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    path.write_text(f"{token}\n", encoding="utf-8")
    return token


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    app_name: str
    state_dir: Path
    upload_dir: Path
    log_file: Path
    codex_home: Path
    codex_sessions_dir: Path
    codex_session_index: Path
    desktop_logs_dir: Path
    max_text_length: int
    max_body_bytes: int
    max_attachment_bytes: int
    max_attachments: int
    token: str
    focus_settle_ms: int
    deep_link_settle_ms: int
    click_settle_ms: int
    text_paste_settle_ms: int
    attachment_paste_settle_ms: int
    composer_bottom_offset: int


def load_settings() -> Settings:
    user_home = Path.home()
    state_dir = _env_path("CODEX_PHONE_STATE_DIR", user_home / ".codex-phone")
    upload_dir = _env_path("CODEX_PHONE_UPLOAD_DIR", state_dir / "uploads")
    log_file = _env_path("CODEX_PHONE_LOG_FILE", state_dir / "logs" / "bridge.log")
    codex_home = _env_path("CODEX_HOME", user_home / ".codex")
    desktop_logs_dir = _env_path(
        "CODEX_PHONE_DESKTOP_LOGS_DIR",
        Path(os.getenv("APPDATA", "")) / "codex-ds",
    )
    token_path = state_dir / "token.txt"

    return Settings(
        host=os.getenv("CODEX_PHONE_HOST", "0.0.0.0"),
        port=int(os.getenv("CODEX_PHONE_PORT", "8787")),
        app_name=os.getenv("CODEX_PHONE_APP_NAME", "Codex Phone"),
        state_dir=state_dir,
        upload_dir=upload_dir,
        log_file=log_file,
        codex_home=codex_home,
        codex_sessions_dir=codex_home / "sessions",
        codex_session_index=codex_home / "session_index.jsonl",
        desktop_logs_dir=desktop_logs_dir,
        max_text_length=int(os.getenv("CODEX_PHONE_MAX_TEXT_LENGTH", "12000")),
        max_body_bytes=int(os.getenv("CODEX_PHONE_MAX_BODY_BYTES", str(32 * 1024 * 1024))),
        max_attachment_bytes=int(os.getenv("CODEX_PHONE_MAX_ATTACHMENT_BYTES", str(10 * 1024 * 1024))),
        max_attachments=int(os.getenv("CODEX_PHONE_MAX_ATTACHMENTS", "6")),
        token=_stable_token(token_path),
        focus_settle_ms=int(os.getenv("CODEX_PHONE_FOCUS_SETTLE_MS", "150")),
        deep_link_settle_ms=int(os.getenv("CODEX_PHONE_DEEPLINK_SETTLE_MS", "700")),
        click_settle_ms=int(os.getenv("CODEX_PHONE_CLICK_SETTLE_MS", "80")),
        text_paste_settle_ms=int(os.getenv("CODEX_PHONE_TEXT_PASTE_SETTLE_MS", "160")),
        attachment_paste_settle_ms=int(os.getenv("CODEX_PHONE_ATTACHMENT_PASTE_SETTLE_MS", "240")),
        composer_bottom_offset=int(os.getenv("CODEX_PHONE_COMPOSER_BOTTOM_OFFSET", "92")),
    )
