import re

from models import Person
from rules.types import RuleMatch

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _bare_uuid(infoscience_id: str) -> str | None:
    m = _UUID_RE.search(infoscience_id)
    return m.group(0).lower() if m else None


def resolve_infoscience_uuid(persons: list[Person]) -> list[RuleMatch]:
    """Group persons sharing the same Infoscience UUID, regardless of which of the two
    known URL forms (…/server/api/core/items/<uuid> vs …/entities/person/<uuid>) it's stored as."""
    by_uuid: dict[str, list[Person]] = {}
    for p in persons:
        if not p.infoscience_id:
            continue
        uuid = _bare_uuid(p.infoscience_id)
        if uuid:
            by_uuid.setdefault(uuid, []).append(p)

    matches = []
    for uuid, group in by_uuid.items():
        iris = sorted({p.iri for p in group})
        if len(iris) < 2:
            continue
        reason = f"[infoscience_uuid] Shared Infoscience UUID {uuid} across {len(iris)} records."
        usernames = {p.github_username for p in group if p.github_username}
        if len(usernames) > 1:
            reason += (f" Caution: conflicting GitHub accounts attached "
                       f"({', '.join(sorted(usernames))}) — verify before trusting.")
        matches.append(RuleMatch(entities=iris, reason=reason))
    return matches