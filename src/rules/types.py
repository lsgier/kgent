from dataclasses import dataclass


@dataclass
class RuleMatch:
    """Two or more Person IRIs deterministically identified as the same real-world person."""
    entities: list[str]
    reason: str