import logging
from pathlib import Path

_LOGGER_NAME = "oko"


def get_logs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "logs"


def ensure_logs_dir() -> Path:
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logs_dir = ensure_logs_dir()
    log_file = logs_dir / "oko.log"

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return setup_logging()
