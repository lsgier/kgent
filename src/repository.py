import logging
from typing import Any

from pydantic import ValidationError
from SPARQLWrapper import SPARQLWrapper, JSON

from audit import SPARQLLog
from models import Person

log = logging.getLogger(__name__)

PREFIXES = """
    PREFIX schema: <http://schema.org/>
    PREFIX pulse:  <https://open-pulse.epfl.ch/ontology#>
    PREFIX org:    <http://www.w3.org/ns/org#>
"""

# Namespace -> prefix, used to shorten predicate URIs into readable bag keys.
NAMESPACES = {
    "http://schema.org/": "schema:",
    "https://open-pulse.epfl.ch/ontology#": "pulse:",
    "http://www.w3.org/ns/org#": "org:",
    "https://openpulse.science/git-metadata-extractor#": "gme:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
}

# Prefixed predicate -> single-valued Person field.
_SCALAR_FIELDS = {
    "pulse:githubUsername": "github_username",
    "schema:email": "email",
    "pulse:orcidIdentifier": "orcid",
    "pulse:infosciencePersonIdentifier": "infoscience_id",
    "schema:url": "url",
    "gme:bio": "bio",
    "gme:location": "location",
    "gme:company": "company",
}

# Prefixed predicate -> multi-valued (IRI list) Person field.
_LIST_FIELDS = {
    "pulse:hasContribution": "has_contribution",
    "org:hasMembership": "has_membership",
    "pulse:owns": "owns",
}

PAGE_SIZE = 5000


def _shorten(uri: str) -> str:
    for base, prefix in NAMESPACES.items():
        if uri.startswith(base):
            return prefix + uri[len(base):]
    return uri


class KnowledgeGraphRepository:
    def __init__(self, endpoint: str, sparql_log: SPARQLLog | None = None,
                 user: str | None = None, password: str | None = None):
        self._sparql = SPARQLWrapper(endpoint)
        self._sparql.setReturnFormat(JSON)
        if user and password:
            self._sparql.setCredentials(user, password)
        self._sparql_log = sparql_log

    # Run a SPARQL query, logging it first if a SPARQLLog is configured.
    def _query(self, sparql: str) -> list[dict[str, Any]]:
        if self._sparql_log:
            self._sparql_log.log("query", sparql)
        self._sparql.setQuery(sparql)
        result = self._sparql.query().convert()
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected SPARQL response type: {type(result)}")
        return result["results"]["bindings"]

    def get_persons(self) -> list[Person]:
        persons: list[Person] = []
        page = 0
        while True:
            # Pull every triple for a page of persons; the inner subquery paginates on
            # persons (not triples) so a person's properties never span two pages.
            rows = self._query(f"""
                {PREFIXES}
                SELECT ?iri ?p ?o WHERE {{
                    {{
                        SELECT ?iri WHERE {{ ?iri a schema:Person }}
                        ORDER BY ?iri LIMIT {PAGE_SIZE} OFFSET {page * PAGE_SIZE}
                    }}
                    ?iri ?p ?o .
                }}
                ORDER BY ?iri
            """)
            if not rows:
                break
            for iri, props in self._group_by_subject(rows).items():
                person = self._build_person(iri, props)
                if person:
                    persons.append(person)
            page += 1
        return persons

    # Collapse (subject, predicate, object) rows into {iri: {prefixed_predicate: [values]}}.
    @staticmethod
    def _group_by_subject(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
        grouped: dict[str, dict[str, list[str]]] = {}
        for r in rows:
            iri = r["iri"]["value"]
            pred = _shorten(r["p"]["value"])
            obj = r["o"]["value"]
            values = grouped.setdefault(iri, {}).setdefault(pred, [])
            if obj not in values:
                values.append(obj)
        return grouped

    # Map a full property bag onto a Person; skip (with a warning) if it fails validation.
    @staticmethod
    def _build_person(iri: str, props: dict[str, list[str]]) -> Person | None:
        names = props.get("schema:name")
        if not names:
            return None
        fields: dict[str, Any] = {"iri": iri, "name": " / ".join(names), "properties": props}
        for pred, field in _SCALAR_FIELDS.items():
            if pred in props:
                fields[field] = props[pred][0]
        for pred, field in _LIST_FIELDS.items():
            if pred in props:
                fields[field] = props[pred]
        try:
            return Person(**fields)
        except ValidationError as e:
            log.warning("Skipping person %s: %s", iri, e)
            return None