## Architecture

```mermaid
flowchart TD
    Orchestrator -->|SPARQL SELECT| TS[(RDF Triple Store)]
    Orchestrator -.->|query log| SPARQLLog[(sparql.jsonl)]
    Orchestrator <-.->|read if present, written after a live SPARQL fetch| PersonsCache[(persons_cache.jsonl)]
    TS -->|Person rows| Rules["Rule resolvers\n(deterministic bridges)"]
    Rules -.->|rule-based matches| AuditLog[(audit.jsonl)]
    Rules -->|rule-based matches| RdfExport["RDF export\n(rdf_export.py)"]
    Rules -->|remaining persons| IDF["Name-frequency IDF\n(per-name weight)"]
    Rules -->|remaining persons| Cluster["Cluster\n(embed + FAISS k-NN)"]
    IDF -->|idf-adjusted threshold| Cluster
    Cluster <-->|batched text / vectors| EMB([Embedding API])
    Cluster <-.->|content-addressed cache| EmbeddingCache[(embedding_cache.npz)]
    Cluster -->|candidate clusters| DedupAgent
    DedupAgent <-->|prompt / structured output| LLM([LLM])
    DedupAgent -.->|prompt/response log| LLMLog[(llm.jsonl)]
    DedupAgent -.->|duplicate verdict| AuditLog
    DedupAgent -->|duplicate verdict, grouped| RdfExport
    RdfExport -.->|update log| SPARQLLog
    RdfExport -->|SPARQL INSERT DATA\n(dedup named graph)| TS
```

Legend: solid arrow (`-->`) = pipeline data flow; dotted arrow (`-.->`) = persisted to / read from disk (logs, caches).

Duplicate verdicts (rule-based and LLM) are never auto-merged into the source data. Each verdict is a group of two or more Person IRIs considered duplicates of each other — no member is designated "canonical" at this stage — written as a `dedup:DuplicateAssertion` (confidence, methodology, reasoning, `dedup:member` per entity) into a dedicated named graph (`DEDUP_GRAPH`, default `https://open-pulse.epfl.ch/graph/dedup`) via SPARQL UPDATE. A downstream process queries that graph to decide how to proceed.

## Running as a service

**Prerequisites:** a running SPARQL endpoint reachable from `.env`, Docker running.

### 1. Build

```bash
docker build -t kgent -f tools/image/Dockerfile .
```

### 2. Start

```bash
docker run -d --rm --name kgent --network host --env-file .env kgent
```

`--network host` is required if `.env` points any endpoint at `localhost` (e.g. a local GraphDB instance) — Linux-only, and without it "localhost" inside the container means the container itself, not the host. This also means no `-p` flag is needed; the app is directly reachable at `localhost:8000`. Job-scoped audit/log files and the embedding cache live in the container's own filesystem and are gone once it stops.

Check it started cleanly:
```bash
docker logs kgent            # expect "Uvicorn running on http://0.0.0.0:8000", no ImportError
curl localhost:8000/health   # {"status":"ok"}
```

### 3. Trigger a run

```bash
curl -X POST localhost:8000/runs -H "Content-Type: application/json" -d '{}'
```
Returns `202` and a `job_id`. Optional overrides (all optional, omit for defaults):
```bash
curl -X POST localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"dedup_graph": "https://open-pulse.epfl.ch/graph/dedup", "cluster_k": 20, "cluster_threshold": 0.99}'
```

A real run fetches every person from the configured SPARQL endpoint, embeds them, and makes real sequential LLM calls per cluster — minutes to tens of minutes, and real inference cost (≈655 calls on the last full dataset). A second `POST` while one is running gets `409`.

### 4. Poll status

```bash
curl localhost:8000/runs/<job_id>
```
`status` moves `queued` → `running` → `succeeded`/`failed`; `result` (groups/entities counts, `dedup_graph`) populates on success, `error` on failure.

### 5. Stop

```bash
docker stop kgent   # --rm means it's removed automatically
```
