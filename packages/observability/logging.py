import logging
from typing import Any

from pythonjsonlogger.json import JsonFormatter

REDACTED_KEYS = frozenset({"authorization", "password", "secret", "token", "access_token"})


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in REDACTED_KEYS:
            if hasattr(record, key):
                setattr(record, key, "[REDACTED]")
        if isinstance(record.args, dict):
            record.args = {
                key: "[REDACTED]" if key.lower() in REDACTED_KEYS else value
                for key, value in record.args.items()
            }
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactionFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


def safe_context(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if key.lower() in REDACTED_KEYS else value
        for key, value in values.items()
    }
