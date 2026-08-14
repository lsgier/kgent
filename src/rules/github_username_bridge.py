import re

from models import Person
from rules.types import RuleMatch

_GITHUB_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/?$")


def _github_username(person: Person) -> str | None:
    if person.github_username:
        return person.github_username
    if person.url:
        m = _GITHUB_URL_RE.match(person.url)
        if m:
            return m.group(1)
    return None


def resolve_github_username_bridge(persons: list[Person]) -> list[RuleMatch]:
    """Group persons sharing a GitHub username, whether it's their own field or embedded
    in another node's profile URL (e.g. an ORCID node linking to the same GitHub profile)."""
    by_username: dict[str, list[Person]] = {}
    for p in persons:
        username = _github_username(p)
        if username:
            by_username.setdefault(username.lower(), []).append(p)

    matches = []
    for username, group in by_username.items():
        iris = sorted({p.iri for p in group})
        if len(iris) < 2:
            continue
        matches.append(RuleMatch(
            entities=iris,
            reason=f"[github_username_bridge] Shared GitHub username '{username}' "
                    f"(direct field or profile URL) across {len(iris)} records.",
        ))
    return matches