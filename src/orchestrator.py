import logging
from pathlib import Path

from agent import DedupAgent
from audit import AuditLog, LLMLog, SPARQLLog
from cluster import cluster_persons
from config import (
    AGENT_MAX_CLUSTER_SIZE, AUDIT_LOG_PATH, CLUSTER_K, CLUSTER_NAME_SIMILARITY_PENALTY, CLUSTER_THRESHOLD, EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY, EMBEDDING_MODEL, LLM_API_KEY, LLM_BASE_URL, LLM_LOG_PATH, LLM_MODEL,
    SPARQL_ENDPOINT, SPARQL_LOG_PATH, SPARQL_USER, SPARQL_PASSWORD,
)
from models import Person
from repository import KnowledgeGraphRepository

log = logging.getLogger(__name__)


def _log_cluster_stats(clusters: list[list[Person]], total_persons: int) -> None:
    sizes = sorted((len(c) for c in clusters), reverse=True)
    clustered = sum(sizes)
    if not sizes:
        log.info("Found 0 candidate clusters (all %d persons are singletons)", total_persons)
        return
    hist: dict[int, int] = {}
    for s in sizes:
        hist[s] = hist.get(s, 0) + 1
    hist_str = ", ".join(f"{size}:{count}" for size, count in sorted(hist.items()))
    log.info(
        "Found %d candidate clusters | %d/%d persons clustered (%d singletons) | "
        "size min=%d max=%d mean=%.1f | size histogram (size:count) %s",
        len(sizes), clustered, total_persons, total_persons - clustered,
        sizes[-1], sizes[0], clustered / len(sizes), hist_str,
    )


def _pick_canonical(iris: list[str], persons_by_iri: dict[str, Person]) -> str:
    def rank(iri: str) -> tuple:
        p = persons_by_iri.get(iri)
        completeness = sum(1 for v in [p.github_username, p.email, p.orcid, p.infoscience_id, p.url] if v) if p else 0
        return (-completeness, len(iri), iri)
    return min(iris, key=rank)


def run() -> None:
    sparql_log = SPARQLLog(Path(SPARQL_LOG_PATH))
    repo = KnowledgeGraphRepository(SPARQL_ENDPOINT, sparql_log=sparql_log,
                                    user=SPARQL_USER, password=SPARQL_PASSWORD)
    llm_log = LLMLog(Path(LLM_LOG_PATH))
    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY, llm_log=llm_log)
    audit = AuditLog(Path(AUDIT_LOG_PATH))

    log.info("Fetching persons...")
    all_persons = repo.get_persons()
    log.info("Found %d persons", len(all_persons))
    persons_by_iri = {p.iri: p for p in all_persons}

    log.info("Clustering persons...")
    person_clusters = cluster_persons(
        all_persons, api_url=LLM_BASE_URL + "/embeddings", api_key=LLM_API_KEY, model=EMBEDDING_MODEL,
        k=CLUSTER_K, threshold=CLUSTER_THRESHOLD, name_similarity_penalty=CLUSTER_NAME_SIMILARITY_PENALTY,
        batch_size=EMBED_BATCH_SIZE, concurrency=EMBED_CONCURRENCY,
    )
    _log_cluster_stats(person_clusters, total_persons=len(all_persons))

    log.info("Running deduplication agent...")
    clusters = []
    skipped_oversized = 0
    failed = 0
    for person_cluster in person_clusters:
        if len(person_cluster) > AGENT_MAX_CLUSTER_SIZE:
            skipped_oversized += 1
            log.info("skipped-oversized: cluster of %d persons > cap %d (e.g. %s) — name-collision blob",
                     len(person_cluster), AGENT_MAX_CLUSTER_SIZE,
                     ", ".join(p.name for p in person_cluster[:3]))
            continue
        try:
            clusters.extend(agent.find_duplicates(person_cluster))
        except Exception as e:  # keep the run alive; a repo-heavy cluster can overflow the context window
            failed += 1
            log.warning("agent-failed: cluster of %d persons (e.g. %s) — %s: %s",
                        len(person_cluster), person_cluster[0].name, type(e).__name__, e)
    log.info("Agent done: %d verdicts, %d clusters skipped-oversized, %d agent-failed",
             len(clusters), skipped_oversized, failed)

    found = 0
    for cluster in clusters:
        if not cluster.is_duplicate:
            log.info("Skipping non-duplicate (certainty %.2f): %s", cluster.certainty, cluster.reason)
            continue
        canonical_iri = _pick_canonical(cluster.entities, persons_by_iri)
        duplicate_iris = [iri for iri in cluster.entities if iri != canonical_iri]

        for dup_iri in duplicate_iris:
            canonical = persons_by_iri[canonical_iri]
            duplicate = persons_by_iri[dup_iri]
            audit.log_duplicate(
                canonical=canonical,
                duplicate=duplicate,
                confidence=cluster.certainty,
                reason=cluster.reason,
            )
            found += 1

    log.info("Found %d duplicates, presented for review in %s (not merged)", found, AUDIT_LOG_PATH)
