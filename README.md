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
