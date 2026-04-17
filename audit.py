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


class AuditLog:
    def __init__(self, path: Path):
        self._path = path

    def log_merge(
        self,
        canonical,
        duplicate,
        confidence: float,
        reason: str,
        validation_passed: bool,
        violations: list[str] | None = None,
        committed: bool = False,
    ) -> None:
        entry: dict = {
            "timestamp": _now(),
            "operation": "merge",
            "status": "committed" if committed else "skipped",
            "confidence": confidence,
            "reason": reason,
            "validation": "passed" if validation_passed else "failed",
            "canonical": canonical.model_dump(),
            "duplicate": duplicate.model_dump(),
        }
        if violations:
            entry["violations"] = violations

        _append(self._path, entry)

        log.info(
            "[audit] %s: %s → %s (%s)",
            entry["status"],
            duplicate.iri,
            canonical.iri,
            entry["validation"],
        )
