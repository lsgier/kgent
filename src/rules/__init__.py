from typing import Callable

from models import Person
from rules.github_username_bridge import resolve_github_username_bridge
from rules.infoscience_uuid import resolve_infoscience_uuid
from rules.types import RuleMatch

RESOLVERS: list[Callable[[list[Person]], list[RuleMatch]]] = [
    resolve_github_username_bridge,
    resolve_infoscience_uuid,
]


def resolve_rule_based(persons: list[Person]) -> list[RuleMatch]:
    """Run every registered rule resolver over the full person pool."""
    matches: list[RuleMatch] = []
    for resolver in RESOLVERS:
        matches.extend(resolver(persons))
    return matches