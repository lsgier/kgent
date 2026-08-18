import logging
from pathlib import Path

from agent import DedupAgent
from audit import AuditLog, LLMLog, SPARQLLog
from cache import load_persons, save_persons
from cluster import cluster_persons
from config import (
    AGENT_MAX_CLUSTER_SIZE, AUDIT_LOG_PATH, CLUSTER_K, CLUSTER_NAME_SIMILARITY_PENALTY, CLUSTER_THRESHOLD,
    EMBED_BATCH_SIZE, EMBED_CONCURRENCY, EMBED_FIELDS, EMBEDDING_CACHE_PATH, EMBEDDING_MODEL, LLM_API_KEY,
    LLM_BASE_URL, LLM_LOG_PATH, LLM_MODEL, PERSONS_CACHE_PATH, SPARQL_ENDPOINT, SPARQL_LOG_PATH, SPARQL_USER,
    SPARQL_PASSWORD, USE_PERSONS_CACHE,
)
from models import Person
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

    all_persons = []
    if USE_PERSONS_CACHE:
        all_persons = load_persons(Path(PERSONS_CACHE_PATH))
        if all_persons:
            log.info("Loaded %d persons from cache (%s)", len(all_persons), PERSONS_CACHE_PATH)
        else:
            log.info("Cache empty or missing (%s), falling back to SPARQL", PERSONS_CACHE_PATH)
    if not all_persons:
        log.info("Fetching persons...")
        all_persons = repo.get_persons()
        log.info("Found %d persons", len(all_persons))
        save_persons(all_persons, Path(PERSONS_CACHE_PATH))
        log.info("Cached %d persons to %s", len(all_persons), PERSONS_CACHE_PATH)
    persons_by_iri = {p.iri: p for p in all_persons}

    found_duplicates: list[dict] = []

    log.info("Resolving deterministic duplicates...")
    rule_matches = resolve_rule_based(all_persons)
    resolved_iris: set[str] = set()
    rule_found = 0
    for match in rule_matches:
        canonical_iri = _pick_canonical(match.entities, persons_by_iri)
        for dup_iri in match.entities:
            if dup_iri == canonical_iri:
                continue
            audit.log_duplicate(
                canonical=persons_by_iri[canonical_iri],
                duplicate=persons_by_iri[dup_iri],
                confidence=1.0,
                reason=match.reason,
                method="rule-based",
            )
            found_duplicates.append({
                "confidence": 1.0, "canonical": canonical_iri, "duplicate": dup_iri, "method": "rule-based",
            })
            rule_found += 1
        resolved_iris.update(match.entities)
    log.info("Rule-based resolution: %d matches, %d duplicates found, %d persons removed from clustering pool",
             len(rule_matches), rule_found, len(resolved_iris))

    remaining_persons = [p for p in all_persons if p.iri not in resolved_iris]

    log.info("Clustering persons...")
    person_clusters = cluster_persons(
        remaining_persons, api_url=LLM_BASE_URL + "/embeddings", api_key=LLM_API_KEY, model=EMBEDDING_MODEL,
        k=CLUSTER_K, threshold=CLUSTER_THRESHOLD, name_similarity_penalty=CLUSTER_NAME_SIMILARITY_PENALTY,
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
        canonical_iri = _pick_canonical(valid_entities, persons_by_iri)
        duplicate_iris = [iri for iri in valid_entities if iri != canonical_iri]

        for dup_iri in duplicate_iris:
            canonical = persons_by_iri[canonical_iri]
            duplicate = persons_by_iri[dup_iri]
            audit.log_duplicate(
                canonical=canonical,
                duplicate=duplicate,
                confidence=cluster.certainty,
                reason=cluster.reason,
                method="llm",
            )
            found_duplicates.append({
                "confidence": cluster.certainty, "canonical": canonical_iri, "duplicate": dup_iri, "method": "llm",
            })
            llm_found += 1

    log.info("Found %d duplicates (%d rule-based, %d LLM), presented for review in %s (not merged)",
             rule_found + llm_found, rule_found, llm_found, AUDIT_LOG_PATH)

    found_duplicates.sort(key=lambda d: d["confidence"], reverse=True)
    print(f"\n{len(found_duplicates)} duplicate candidates, sorted by confidence (highest first):")
    for d in found_duplicates:
        print(f"  {d['confidence']:.2f}  [{d['method']:10s}]  {d['duplicate']}  ~  {d['canonical']}")
