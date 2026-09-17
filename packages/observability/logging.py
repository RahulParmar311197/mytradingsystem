"""Structured logs with recursive redaction at the final output boundary."""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretBytes, SecretStr

correlation_context: ContextVar[str] = ContextVar("correlation_id", default="")
_SENSITIVE = re.compile(
    r"authorization|cookie|password|passwd|secret|token|api.?key|credential|"
    r"email|phone|pan_number|external_reference|database_url|redis_url",
    re.I,
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(access_token|refresh_token|token|password|secret|api[_-]?key)"
    r"([\s\"']*[:=][\s\"']*)([^\s,;\"'&}]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL = re.compile(r"(\w+(?:\+\w+)?://)[^\s/@]+:[^\s/@]+@")
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _URL_CREDENTIAL.sub(r"\1[REDACTED]@", value)
    return _ASSIGNMENT.sub(r"\1\2[REDACTED]", value)


def _redact(value: Any) -> Any:
    if isinstance(value, (SecretStr, SecretBytes)):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def safe_context(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if _SENSITIVE.search(key) else _redact(v) for key, v in values.items()
    }


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = safe_context(record.args)
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for key in set(record.__dict__) - _STANDARD:
            setattr(record, key, safe_context({key: getattr(record, key)})[key])
        return True


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "correlation_id": correlation_context.get(),
        }
        fields.update(
            safe_context({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        )
        # Exception bodies can contain broker payloads or database credentials.
        if record.exc_info and record.exc_info[0]:
            fields["exception_type"] = record.exc_info[0].__name__
        return json.dumps(fields, default=str, allow_nan=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    handler.addFilter(RedactionFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers.clear()
        log.propagate = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
