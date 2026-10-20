"""Application logging setup with rotating files."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path | None = None) -> Path:
    """Configure a rotating UTF-8 log under the app's logs directory."""
    destination = log_dir or Path.cwd() / "logs"
    destination.mkdir(parents=True, exist_ok=True)
    logfile = destination / "dupe-sweep.log"
    root = logging.getLogger("dupe_sweep")
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        handler = RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=4, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    return logfile
