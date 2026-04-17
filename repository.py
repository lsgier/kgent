from typing import Any

from SPARQLWrapper import SPARQLWrapper, JSON

from models import Person

PREFIXES = """
    PREFIX schema: <http://schema.org/>
    PREFIX pulse:  <https://open-pulse.epfl.ch/ontology#>
    PREFIX org:    <http://www.w3.org/ns/org#>
"""


class KnowledgeGraphRepository:
    def __init__(self, endpoint: str):
        self._sparql = SPARQLWrapper(endpoint)
        self._sparql.setReturnFormat(JSON)

    @staticmethod
    def _val(binding: dict[str, Any], key: str) -> str | None:
        entry = binding.get(key)
        return entry["value"] if entry else None

    @staticmethod
    def _req(binding: dict[str, Any], key: str) -> str:
        entry = binding.get(key)
        if not entry:
            raise ValueError(f"Required SPARQL binding '{key}' is missing")
        return entry["value"]

    @staticmethod
    def _split_iris(val: str | None) -> list[str]:
        return [v for v in (val or "").split(",") if v]

    def _query(self, sparql: str) -> list[dict[str, Any]]:
        self._sparql.setQuery(sparql)
        result = self._sparql.query().convert()
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected SPARQL response type: {type(result)}")
        return result["results"]["bindings"]

    def get_persons(self) -> list[Person]:
        rows = self._query(f"""
            {PREFIXES}
            SELECT ?iri ?name ?github ?email ?orcid ?infoscience ?url
                   (GROUP_CONCAT(DISTINCT ?contribution; SEPARATOR=",") AS ?contributions)
                   (GROUP_CONCAT(DISTINCT ?membership; SEPARATOR=",") AS ?memberships)
                   (GROUP_CONCAT(DISTINCT ?owns; SEPARATOR=",") AS ?ownedRepos)
            WHERE {{
                ?iri a schema:Person ;
                     schema:name ?name .
                OPTIONAL {{ ?iri pulse:githubUsername ?github }}
                OPTIONAL {{ ?iri schema:email ?email }}
                OPTIONAL {{ ?iri pulse:orcidIdentifier ?orcid }}
                OPTIONAL {{ ?iri pulse:infosciencePersonIdentifier ?infoscience }}
                OPTIONAL {{ ?iri schema:url ?url }}
                OPTIONAL {{ ?iri pulse:hasContribution ?contribution }}
                OPTIONAL {{ ?iri org:hasMembership ?membership }}
                OPTIONAL {{ ?iri pulse:owns ?owns }}
            }}
            GROUP BY ?iri ?name ?github ?email ?orcid ?infoscience ?url
        """)
        return [
            Person(
                iri=self._req(r, "iri"),
                name=self._req(r, "name"),
                github_username=self._val(r, "github"),
                email=self._val(r, "email"),
                orcid=self._val(r, "orcid"),
                infoscience_id=self._val(r, "infoscience"),
                url=self._val(r, "url"),
                has_contribution=self._split_iris(self._val(r, "contributions")),
                has_membership=self._split_iris(self._val(r, "memberships")),
                owns=self._split_iris(self._val(r, "ownedRepos")),
            )
            for r in rows
        ]
