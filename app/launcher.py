from __future__ import annotations

import json
import os
import threading
import time
import traceback
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn

from app.config import load_settings
from app.logging_setup import configure_logging
from app.tray import create_tray_icon, tray_enabled


def _open_admin_page(host: str, port: int) -> None:
    time.sleep(1.2)
    _open_admin_url(host, port)


def _open_admin_url(host: str, port: int) -> None:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    webbrowser.open(f"http://{browser_host}:{port}/admin")


def _existing_service_is_codex_phone(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/admin/bootstrap", timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("ok") is True and data.get("service") == "codex-phone"
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_file)
    from app.main import app as fastapi_app

    if _existing_service_is_codex_phone(settings.port):
        _open_admin_url(settings.host, settings.port)
        return

    if os.getenv("CODEX_PHONE_NO_BROWSER", "").strip() not in {"1", "true", "yes"}:
        threading.Thread(target=_open_admin_page, args=(settings.host, settings.port), daemon=True).start()

    config = uvicorn.Config(
        fastapi_app,
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)

    if not tray_enabled():
        server.run()
        return

    server_thread = threading.Thread(target=server.run, name="codex-phone-server", daemon=True)
    server_thread.start()

    tray_icon = create_tray_icon(settings, lambda: setattr(server, "should_exit", True))

    def _stop_tray_when_server_exits() -> None:
        server_thread.join()
        tray_icon.stop()

    threading.Thread(target=_stop_tray_when_server_exits, name="codex-phone-tray-watch", daemon=True).start()
    tray_icon.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        settings = load_settings()
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        with (settings.log_file.parent / "launcher-crash.log").open("a", encoding="utf-8") as handle:
            handle.write("\n=== Codex Phone launcher crash ===\n")
            handle.write(traceback.format_exc())
        raise
