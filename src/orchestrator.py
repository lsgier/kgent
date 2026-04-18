import logging
from pathlib import Path

from agent import DedupAgent
from audit import AuditLog, SPARQLLog
from config import AUDIT_LOG_PATH, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SPARQL_ENDPOINT, SPARQL_LOG_PATH
from models import Person
from repository import KnowledgeGraphRepository
from validation import SHACLValidator

log = logging.getLogger(__name__)

ONTOLOGY_PATH = Path(__file__).parent / "validation" / "ontology-combined.ttl"


def _pick_canonical(iris: list[str], persons_by_iri: dict[str, Person]) -> str:
    # Rank by: most complete record first, then shortest IRI, then alphabetical.
    def rank(iri: str) -> tuple:
        p = persons_by_iri.get(iri)
        completeness = sum(1 for v in [p.github_username, p.email, p.orcid, p.infoscience_id, p.url] if v) if p else 0
        return (-completeness, len(iri), iri)
    return min(iris, key=rank)


def run() -> None:
    sparql_log = SPARQLLog(Path(SPARQL_LOG_PATH))
    repo = KnowledgeGraphRepository(SPARQL_ENDPOINT, sparql_log=sparql_log)
    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    validator = SHACLValidator(ONTOLOGY_PATH)
    audit = AuditLog(Path(AUDIT_LOG_PATH))

    log.info("Fetching persons...")
    persons = repo.get_persons()
    log.info("Found %d persons", len(persons))
    persons_by_iri = {p.iri: p for p in persons}

    log.info("Running deduplication agent...")
    clusters = agent.find_duplicates(persons)
    log.info("Found %d duplicate clusters", len(clusters))

    for cluster in clusters:
        canonical_iri = _pick_canonical(cluster.entities, persons_by_iri)
        duplicate_iris = [iri for iri in cluster.entities if iri != canonical_iri]

        for dup_iri in duplicate_iris:
            log.info("Validating merge: %s → %s", dup_iri, canonical_iri)
            canonical = persons_by_iri[canonical_iri]
            duplicate = persons_by_iri[dup_iri]
            merged = canonical.merge(duplicate)
            result = validator.validate_person(merged)

            if result.valid:
                repo.merge_persons(canonical_iri, dup_iri)
                audit.log_merge(
                    canonical=canonical,
                    duplicate=duplicate,
                    confidence=cluster.confidence,
                    reason=cluster.reason,
                    validation_passed=True,
                    committed=True,
                )
            else:
                log.warning("SHACL failed for %s → %s: %s", dup_iri, canonical_iri, result)
                audit.log_merge(
                    canonical=canonical,
                    duplicate=duplicate,
                    confidence=cluster.confidence,
                    reason=cluster.reason,
                    validation_passed=False,
                    violations=result.violations,
                    committed=False,
                )
