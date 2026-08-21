import logging
from pathlib import Path

from agent import DedupAgent
from audit import AuditLog, LLMLog, SPARQLLog
from cache import load_persons, save_persons
from cluster import cluster_persons
from config import (
    AGENT_MAX_CLUSTER_SIZE, AUDIT_LOG_PATH, CLUSTER_K, CLUSTER_NAME_SIMILARITY_PENALTY, CLUSTER_THRESHOLD,
    DEDUP_GRAPH, EMBED_BATCH_SIZE, EMBED_CONCURRENCY, EMBED_FIELDS, EMBEDDING_CACHE_PATH, EMBEDDING_MODEL,
    LLM_API_KEY, LLM_BASE_URL, LLM_LOG_PATH, LLM_MODEL, PERSONS_CACHE_PATH, SPARQL_ENDPOINT, SPARQL_LOG_PATH,
    SPARQL_UPDATE_ENDPOINT, SPARQL_USER, SPARQL_PASSWORD, USE_PERSONS_CACHE,
)
from models import Person
from rdf_export import DuplicateGroup, write_groups
from repository import KnowledgeGraphRepository
from rules import resolve_rule_based

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


def run(
    *,
    sparql_endpoint: str = SPARQL_ENDPOINT,
    sparql_update_endpoint: str = SPARQL_UPDATE_ENDPOINT,
    dedup_graph: str = DEDUP_GRAPH,
    cluster_k: int = CLUSTER_K,
    cluster_threshold: float = CLUSTER_THRESHOLD,
    cluster_name_similarity_penalty: float = CLUSTER_NAME_SIMILARITY_PENALTY,
    audit_log_path: str = AUDIT_LOG_PATH,
    sparql_log_path: str = SPARQL_LOG_PATH,
    llm_log_path: str = LLM_LOG_PATH,
    persons_cache_path: str = PERSONS_CACHE_PATH,
) -> dict:
    for p in (audit_log_path, sparql_log_path, llm_log_path, persons_cache_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    sparql_log = SPARQLLog(Path(sparql_log_path))
    repo = KnowledgeGraphRepository(sparql_endpoint, update_endpoint=sparql_update_endpoint, sparql_log=sparql_log,
                                    user=SPARQL_USER, password=SPARQL_PASSWORD)
    llm_log = LLMLog(Path(llm_log_path))
    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY, llm_log=llm_log)
    audit = AuditLog(Path(audit_log_path))

    all_persons = []
    if USE_PERSONS_CACHE:
        all_persons = load_persons(Path(persons_cache_path))
        if all_persons:
            log.info("Loaded %d persons from cache (%s)", len(all_persons), persons_cache_path)
        else:
            log.info("Cache empty or missing (%s), falling back to SPARQL", persons_cache_path)
    if not all_persons:
        log.info("Fetching persons...")
        all_persons = repo.get_persons()
        log.info("Found %d persons", len(all_persons))
        save_persons(all_persons, Path(persons_cache_path))
        log.info("Cached %d persons to %s", len(all_persons), persons_cache_path)
    persons_by_iri = {p.iri: p for p in all_persons}

    groups: list[DuplicateGroup] = []

    log.info("Resolving deterministic duplicates...")
    rule_matches = resolve_rule_based(all_persons)
    resolved_iris: set[str] = set()
    for match in rule_matches:
        audit.log_group(entities=match.entities, confidence=1.0, reason=match.reason, method="rule-based")
        groups.append(DuplicateGroup(entities=match.entities, confidence=1.0, reason=match.reason, method="rule-based"))
        resolved_iris.update(match.entities)
    log.info("Rule-based resolution: %d groups, %d persons removed from clustering pool",
             len(rule_matches), len(resolved_iris))

    remaining_persons = [p for p in all_persons if p.iri not in resolved_iris]

    log.info("Clustering persons...")
    person_clusters = cluster_persons(
        remaining_persons, api_url=LLM_BASE_URL + "/embeddings", api_key=LLM_API_KEY, model=EMBEDDING_MODEL,
        k=cluster_k, threshold=cluster_threshold, name_similarity_penalty=cluster_name_similarity_penalty,
        batch_size=EMBED_BATCH_SIZE, concurrency=EMBED_CONCURRENCY, fields=EMBED_FIELDS,
        cache_path=Path(EMBEDDING_CACHE_PATH),
    )
    _log_cluster_stats(person_clusters, total_persons=len(remaining_persons))

    log.info("Running deduplication agent...")
    clusters = []
    skipped_oversized = 0
    failed = 0
    total_clusters = len(person_clusters)
    next_log_pct = 10
    for i, person_cluster in enumerate(person_clusters, 1):
        if len(person_cluster) > AGENT_MAX_CLUSTER_SIZE:
            skipped_oversized += 1
            log.info("skipped-oversized: cluster of %d persons > cap %d (e.g. %s) — name-collision blob",
                     len(person_cluster), AGENT_MAX_CLUSTER_SIZE,
                     ", ".join(p.name for p in person_cluster[:3]))
        else:
            try:
                clusters.extend(agent.find_duplicates(person_cluster))
            except Exception as e:  # keep the run alive; a repo-heavy cluster can overflow the context window
                failed += 1
                log.warning("agent-failed: cluster of %d persons (e.g. %s) — %s: %s",
                            len(person_cluster), person_cluster[0].name, type(e).__name__, e)
        pct = i * 100 // total_clusters
        if pct >= next_log_pct:
            log.info("Agent progress: %d/%d clusters (%d%%)", i, total_clusters, pct)
            next_log_pct += 10
    log.info("Agent done: %d verdicts, %d clusters skipped-oversized, %d agent-failed",
             len(clusters), skipped_oversized, failed)

    llm_found = 0
    for cluster in clusters:
        if not cluster.is_duplicate:
            log.info("Skipping non-duplicate: %s", cluster.reason)
            continue
        # The agent is contractually supposed to echo back exactly the input IRIs, but
        # occasionally hallucinates a malformed one (e.g. a doubled "https" prefix) --
        # untrusted LLM output, so validate at this boundary rather than crash the run.
        valid_entities = [iri for iri in cluster.entities if iri in persons_by_iri]
        if len(valid_entities) < len(cluster.entities):
            log.warning("agent returned unknown entity IRI(s) not in the input cluster, ignoring: %s",
                        set(cluster.entities) - set(valid_entities))
        if len(valid_entities) < 2:
            continue
        audit.log_group(entities=valid_entities, confidence=cluster.certainty, reason=cluster.reason, method="llm")
        groups.append(DuplicateGroup(entities=valid_entities, confidence=cluster.certainty,
                                      reason=cluster.reason, method="llm"))
        llm_found += 1

    log.info("Found %d duplicate groups (%d rule-based, %d LLM) covering %d entities, presented for review in "
             "%s (not merged)",
             len(groups), len(rule_matches), llm_found, sum(len(g.entities) for g in groups), audit_log_path)

    method_order = {"rule-based": 0, "llm": 1}
    groups.sort(key=lambda g: (method_order.get(g.method, 99), -g.confidence))
    print(f"\n{len(groups)} duplicate groups, sorted by method then confidence (highest first):")
    for g in groups:
        print(f"  {g.confidence:.2f}  [{g.method:10s}]  {', '.join(g.entities)}")

    write_groups(groups, repo, dedup_graph)

    return {
        "groups_found": len(groups),
        "rule_based_groups": len(rule_matches),
        "llm_groups": llm_found,
        "entities_covered": sum(len(g.entities) for g in groups),
        "dedup_graph": dedup_graph,
    }
