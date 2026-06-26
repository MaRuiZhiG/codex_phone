from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    if sys.stderr:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
