import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, entry: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


class SPARQLLog:
    def __init__(self, path: Path):
        self._path = path

    def log(self, operation: str, statement: str) -> None:
        _append(self._path, {
            "timestamp": _now(),
            "operation": operation,
            "statement": statement.strip(),
        })


class LLMLog:
    def __init__(self, path: Path):
        self._path = path

    def log(self, prompt: str, response: dict) -> None:
        _append(self._path, {
            "timestamp": _now(),
            "prompt": prompt,
            "response": response,
        })


class AuditLog:
    def __init__(self, path: Path):
        self._path = path

    def log_group(
        self,
        entities: list[str],
        confidence: float,
        reason: str,
        method: str = "llm",
    ) -> None:
        entry: dict = {
            "timestamp": _now(),
            "operation": "duplicate_group",
            "method": method,
            "confidence": confidence,
            "reason": reason,
            "entities": entities,
        }
        _append(self._path, entry)
        log.info("[audit] duplicate group (%s): %s (confidence %.2f)", method, entities, confidence)
