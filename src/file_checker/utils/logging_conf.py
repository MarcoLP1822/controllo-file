from __future__ import annotations

"""file_checker.utils.logging_conf

Configurazione centralizzata del logging.
Può essere importata da qualunque modulo tramite::

    from file_checker.utils.logging_conf import logger

Il livello di log di default è INFO, ma può essere modificato via variabile
 d'ambiente ``FILE_CHECKER_LOGLEVEL`` (DEBUG, INFO, WARNING, ERROR, CRITICAL).
I log sono scritti sia su console sia su file rotante in ``logs/``.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Parametri configurabili via env
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("FILE_CHECKER_LOGLEVEL", "INFO").upper()
LOG_DIR = Path(os.getenv("FILE_CHECKER_LOGDIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"file_checker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Handler: Rotating file (max 5 MB, 3 backup)
# ---------------------------------------------------------------------------

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))

# ---------------------------------------------------------------------------
# Root logger
# ---------------------------------------------------------------------------

logging.basicConfig(level=LOG_LEVEL, handlers=[file_handler, console_handler])

logger = logging.getLogger("file_checker")
logger.setLevel(LOG_LEVEL)

# ---------------------------------------------------------------------------
# Utility helper (opzionale)
# ---------------------------------------------------------------------------


def set_level(level: str | int) -> None:
    """Permette di cambiare livello a runtime."""

    logging.getLogger().setLevel(level)
    logger.setLevel(level)
