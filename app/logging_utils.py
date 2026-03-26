from contextvars import ContextVar, Token
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOGGING_CONFIGURED = False
_LOG_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})
_CURRENT_LOG_FILE: Path | None = None
DEFAULT_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "app.log"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


def _is_console_handler(handler: logging.Handler) -> bool:
    return isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)


def _is_matching_file_handler(handler: logging.Handler, log_file: Path) -> bool:
    if not isinstance(handler, RotatingFileHandler):
        return False
    base_filename = getattr(handler, "baseFilename", None)
    if not base_filename:
        return False
    return Path(base_filename).resolve() == log_file.resolve()


def configure_logging(
    level: int = logging.INFO,
    log_file: str | Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    force: bool = False,
) -> Path:
    global _LOGGING_CONFIGURED, _CURRENT_LOG_FILE
    if _LOGGING_CONFIGURED and not force:
        return _CURRENT_LOG_FILE if _CURRENT_LOG_FILE is not None else DEFAULT_LOG_FILE.resolve()

    resolved_log_file = Path(log_file) if log_file else DEFAULT_LOG_FILE
    resolved_log_file = resolved_log_file.resolve()
    resolved_log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    if force:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    has_console = any(_is_console_handler(handler) for handler in root_logger.handlers)
    has_file = any(_is_matching_file_handler(handler, resolved_log_file) for handler in root_logger.handlers)

    if not has_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if not has_file:
        file_handler = RotatingFileHandler(
            filename=resolved_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _LOGGING_CONFIGURED = True
    _CURRENT_LOG_FILE = resolved_log_file
    return resolved_log_file


def _normalize_field_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(key): _normalize_field_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_field_value(item) for item in value]
    return str(value)


def _serialize_fields(fields: dict[str, Any]) -> str:
    normalized = {str(key): _normalize_field_value(value) for key, value in fields.items()}
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def bind_log_context(**fields: Any) -> Token:
    current_context = dict(_LOG_CONTEXT.get())
    for key, value in fields.items():
        if value is None:
            continue
        current_context[str(key)] = value
    return _LOG_CONTEXT.set(current_context)


def reset_log_context(token: Token) -> None:
    _LOG_CONTEXT.reset(token)


def get_log_context() -> dict[str, Any]:
    return dict(_LOG_CONTEXT.get())


def _merge_context_fields(fields: dict[str, Any]) -> dict[str, Any]:
    merged = get_log_context()
    merged.update(fields)
    return merged


def log_info(logger: logging.Logger, event: str, **fields: Any) -> None:
    merged_fields = _merge_context_fields(fields)
    if merged_fields:
        logger.info("%s | %s", event, _serialize_fields(merged_fields))
        return
    logger.info("%s", event)


def log_warning(logger: logging.Logger, event: str, **fields: Any) -> None:
    merged_fields = _merge_context_fields(fields)
    if merged_fields:
        logger.warning("%s | %s", event, _serialize_fields(merged_fields))
        return
    logger.warning("%s", event)


def log_error(logger: logging.Logger, event: str, **fields: Any) -> None:
    merged_fields = _merge_context_fields(fields)
    if merged_fields:
        logger.error("%s | %s", event, _serialize_fields(merged_fields))
        return
    logger.error("%s", event)


def log_exception(logger: logging.Logger, event: str, **fields: Any) -> None:
    merged_fields = _merge_context_fields(fields)
    if merged_fields:
        logger.exception("%s | %s", event, _serialize_fields(merged_fields))
        return
    logger.exception("%s", event)
