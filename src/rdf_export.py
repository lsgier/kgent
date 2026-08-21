import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from rdflib import Graph, Literal, Namespace, URIRef, XSD
from rdflib.namespace import PROV, RDF

from repository import KnowledgeGraphRepository

log = logging.getLogger(__name__)

DEDUP = Namespace("https://open-pulse.epfl.ch/ontology/dedup#")


@dataclass
class DuplicateGroup:
    """Two or more Person IRIs asserted to be the same real-world person; no member is
    designated canonical here — that decision belongs to the downstream consumer."""
    entities: list[str]
    confidence: float
    reason: str
    method: str


def _build_graph(groups: list[DuplicateGroup], graph_iri: str) -> Graph:
    g = Graph()
    g.bind("dedup", DEDUP)
    g.bind("prov", PROV)
    now = Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)
    for group in groups:
        assertion = URIRef(f"{graph_iri}/assertion/{uuid.uuid4()}")
        g.add((assertion, RDF.type, DEDUP.DuplicateAssertion))
        g.add((assertion, PROV.generatedAtTime, now))
        g.add((assertion, DEDUP.confidence, Literal(group.confidence, datatype=XSD.decimal)))
        g.add((assertion, DEDUP.methodology, Literal(group.method)))
        g.add((assertion, DEDUP.reasoning, Literal(group.reason)))
        for entity in group.entities:
            g.add((assertion, DEDUP.member, URIRef(entity)))
    return g


# Serialise groups as N-Triples and wrap them in an INSERT DATA block. N-Triples are a
# syntactic subset of the SPARQL Update triple grammar, and rdflib handles literal
# escaping, so this avoids hand-building query strings from untrusted reason text.
def build_insert(groups: list[DuplicateGroup], graph_iri: str) -> str:
    if not groups:
        return ""
    triples = _build_graph(groups, graph_iri).serialize(format="nt").strip()
    return f"INSERT DATA {{ GRAPH <{graph_iri}> {{\n{triples}\n}} }}"


def write_groups(groups: list[DuplicateGroup], repo: KnowledgeGraphRepository, graph_iri: str) -> None:
    sparql = build_insert(groups, graph_iri)
    if not sparql:
        log.info("No duplicate groups to write to %s", graph_iri)
        return
    repo.update(sparql)
    log.info("Wrote %d duplicate assertions to graph %s", len(groups), graph_iri)
