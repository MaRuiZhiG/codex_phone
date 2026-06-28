from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path
from typing import Callable

from PIL import Image
import pystray

from app.access_manager import AccessManager
from app.config import Settings


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _icon_path() -> Path:
    root = _app_root()
    candidates = [
        root / "assets" / "app-icon.ico",
        root / "assets" / "app-icon.png",
        Path(sys.executable).resolve().parent / "app-icon.ico",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Codex Phone icon asset was not found.")


def _admin_url(settings: Settings) -> str:
    browser_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    return f"http://{browser_host}:{settings.port}/admin"


def _mobile_url(settings: Settings) -> str:
    access = AccessManager(settings).read_status()
    base_url = access.get("effectiveUrl") or access.get("lanUrl") or ""
    if not base_url:
        return _admin_url(settings)
    return f"{base_url}/?token={settings.token}"


def create_tray_icon(settings: Settings, on_exit: Callable[[], None]) -> pystray.Icon:
    image = Image.open(_icon_path())

    def open_admin(_: pystray.Icon, __: pystray.MenuItem) -> None:
        webbrowser.open(_admin_url(settings))

    def open_mobile(_: pystray.Icon, __: pystray.MenuItem) -> None:
        webbrowser.open(_mobile_url(settings))

    def quit_app(icon: pystray.Icon, _: pystray.MenuItem) -> None:
        on_exit()
        icon.stop()

    return pystray.Icon(
        "Codex Phone",
        image,
        "Codex Phone 正在运行",
        pystray.Menu(
            pystray.MenuItem("打开管理页面", open_admin, default=True),
            pystray.MenuItem("打开手机入口", open_mobile),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出 Codex Phone", quit_app),
        ),
    )


def tray_enabled() -> bool:
    return os.getenv("CODEX_PHONE_NO_TRAY", "").strip().lower() not in {"1", "true", "yes"}
