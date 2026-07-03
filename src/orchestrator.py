import logging
from pathlib import Path

from agent import DedupAgent
from audit import AuditLog, SPARQLLog
from cluster import cluster_persons
from config import AUDIT_LOG_PATH, EMBEDDING_MODEL, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SPARQL_ENDPOINT, SPARQL_LOG_PATH
from models import Person
from repository import KnowledgeGraphRepository

log = logging.getLogger(__name__)


def _pick_canonical(iris: list[str], persons_by_iri: dict[str, Person]) -> str:
    def rank(iri: str) -> tuple:
        p = persons_by_iri.get(iri)
        completeness = sum(1 for v in [p.github_username, p.email, p.orcid, p.infoscience_id, p.url] if v) if p else 0
        return (-completeness, len(iri), iri)
    return min(iris, key=rank)


def run() -> None:
    sparql_log = SPARQLLog(Path(SPARQL_LOG_PATH))
    repo = KnowledgeGraphRepository(SPARQL_ENDPOINT, sparql_log=sparql_log)
    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    audit = AuditLog(Path(AUDIT_LOG_PATH))

    log.info("Fetching persons...")
    all_persons = repo.get_persons()
    log.info("Found %d persons", len(all_persons))
    persons_by_iri = {p.iri: p for p in all_persons}

    log.info("Clustering persons...")
    person_clusters = cluster_persons(all_persons, api_url=LLM_BASE_URL + "/embeddings", api_key=LLM_API_KEY, model=EMBEDDING_MODEL)
    log.info("Found %d candidate clusters", len(person_clusters))

    log.info("Running deduplication agent...")
    clusters = []
    for person_cluster in person_clusters:
        clusters.extend(agent.find_duplicates(person_cluster))
    log.info("Found %d duplicate clusters", len(clusters))

    for cluster in clusters:
        if not cluster.is_duplicate:
            log.info("Skipping non-duplicate (certainty %.2f): %s", cluster.certainty, cluster.reason)
            continue
        canonical_iri = _pick_canonical(cluster.entities, persons_by_iri)
        duplicate_iris = [iri for iri in cluster.entities if iri != canonical_iri]

        for dup_iri in duplicate_iris:
            canonical = persons_by_iri[canonical_iri]
            duplicate = persons_by_iri[dup_iri]
            repo.merge_persons(canonical_iri, dup_iri)
            audit.log_merge(
                canonical=canonical,
                duplicate=duplicate,
                confidence=cluster.certainty,
                reason=cluster.reason,
            )
