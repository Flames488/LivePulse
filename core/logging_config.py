import logging
import logging.handlers
import sys
import json
import traceback
from datetime import datetime, timezone




class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for machine-readable output."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            log_entry["traceback"] = traceback.format_exc().strip()

        if hasattr(record, "extra"):
            log_entry["extra"] = record.extra

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter with color support for terminals."""

    COLORS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[41m",   # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname:<8}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: int | str = logging.INFO,
    json_output: bool = False,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure and return the root logger.

    Args:
        level:        Minimum log level (e.g. logging.DEBUG or "DEBUG").
        json_output:  Emit structured JSON logs to stdout when True,
                      human-readable colored logs when False.
        log_file:     Optional path to a rotating log file (always plain-text).
        max_bytes:    Max size of each log file before rotation.
        backup_count: Number of rotated log files to retain.

    Returns:
        The configured root logger.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any handlers added by previous calls
    root_logger.handlers.clear()

    # ── stdout handler ────────────────────────────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)

    if json_output:
        stdout_handler.setFormatter(JSONFormatter())
    else:
        human_formatter = HumanFormatter(
            fmt="%(asctime)s  %(levelname)s  %(name)s:%(lineno)d  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stdout_handler.setFormatter(human_formatter)

    root_logger.addHandler(stdout_handler)

    # ── optional rotating file handler (always plain-text) ───────────────────
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger (call setup_logging first)."""
    return logging.getLogger(name)


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger = setup_logging(level="DEBUG", json_output=False, log_file="app.log")

    logger.debug("Debug message")
    logger.info("Service started")
    logger.warning("Low memory")
    logger.error("Connection refused")

    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("Unhandled exception caught")