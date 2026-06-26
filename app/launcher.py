from __future__ import annotations

import os
import threading
import time
import traceback
import webbrowser

import uvicorn

from app.config import load_settings
from app.logging_setup import configure_logging


def _open_admin_page(host: str, port: int) -> None:
    time.sleep(1.2)
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    webbrowser.open(f"http://{browser_host}:{port}/admin")


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_file)
    from app.main import app as fastapi_app

    if os.getenv("CODEX_PHONE_NO_BROWSER", "").strip() not in {"1", "true", "yes"}:
        threading.Thread(target=_open_admin_page, args=(settings.host, settings.port), daemon=True).start()

    uvicorn.run(
        fastapi_app,
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
        log_config=None,
    )


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
