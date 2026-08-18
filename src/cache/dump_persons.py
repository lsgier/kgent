"""
Fetch all persons from the SPARQL endpoint and cache them locally as JSONL.
"""

import logging
import sys
from pathlib import Path

# This script lives in a subpackage but imports flat top-level modules (config,
# repository) the way every other entry point does -- put src/ back on sys.path
# since running this file directly only puts its own directory (cache/) there.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cache.persons_cache import save_persons
from config import PERSONS_CACHE_PATH, SPARQL_ENDPOINT, SPARQL_PASSWORD, SPARQL_USER
from repository import KnowledgeGraphRepository

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    repo = KnowledgeGraphRepository(SPARQL_ENDPOINT, user=SPARQL_USER, password=SPARQL_PASSWORD)
    log.info("Fetching persons from %s...", SPARQL_ENDPOINT)
    persons = repo.get_persons()
    log.info("Fetched %d persons", len(persons))
    save_persons(persons, Path(PERSONS_CACHE_PATH))
    log.info("Cached to %s", PERSONS_CACHE_PATH)


if __name__ == "__main__":
    main()