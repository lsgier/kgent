from pathlib import Path

from models import Person


def save_persons(persons: list[Person], path: Path) -> None:
    with path.open("w") as f:
        for p in persons:
            f.write(p.model_dump_json() + "\n")


def load_persons(path: Path) -> list[Person]:
    if not path.exists():
        return []
    with path.open() as f:
        return [Person.model_validate_json(line) for line in f if line.strip()]