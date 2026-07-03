"""
Trial: run DedupAgent on candidate clusters from the real EPFL dataset.

Clusters come from scan_real.py (FAISS ANN on metadata-epfl-related).
Each cluster is fetched in full from GraphDB and passed to the agent.

Usage:
    uv run python src/trial_real.py
"""

import json
import logging
from typing import Any

from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON

from agent.dedup.agent import DedupAgent
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ENDPOINT = "http://localhost:7200/repositories/first-openpulse-epfl-dump-slack"
GME = "https://openpulse.science/git-metadata-extractor#"

# label: "duplicate" | "potential" | "negative" | "random"
CANDIDATE_CLUSTERS: list[tuple[str, list[str]]] = [
    # Confirmed duplicates (manual review)
    ("duplicate", ["https://github.com/daniel-roulin",       "https://github.com/daniel-roulin-epfl"]),
    ("duplicate", ["https://github.com/assafandrew",         "https://github.com/assafandrew1"]),
    ("duplicate", ["https://github.com/nvarini1",            "https://github.com/nvarini12"]),
    ("duplicate", ["https://github.com/sthithpragya",        "https://github.com/sthithpragyagupta"]),
    ("duplicate", ["https://github.com/amaulap",             "https://github.com/amaulap2"]),
    # Potentials
    ("potential", ["https://github.com/finfinack",           "https://github.com/l3akage"]),
    ("potential", ["https://github.com/ClementEPFL",         "https://github.com/clementcharmillot"]),
    # Confirmed non-duplicates (false positives from clustering)
    ("negative",  ["https://github.com/Auron-X",             "https://github.com/vovanz"]),
    ("negative",  ["https://github.com/beckyfeng08",         "https://github.com/rchen152"]),
    ("negative",  ["https://github.com/Duri01",              "https://github.com/majvan"]),
    # Random pairs — completely unrelated people
    ("random",    ["https://github.com/daniel-roulin",       "https://github.com/beckyfeng08"]),
    ("random",    ["https://github.com/nvarini1",            "https://github.com/finfinack"]),
    ("random",    ["https://github.com/max-mapper",          "https://github.com/sthithpragya"]),
]

PREFIXES = f"""
    PREFIX schema: <http://schema.org/>
    PREFIX pulse:  <https://open-pulse.epfl.ch/ontology#>
    PREFIX org:    <http://www.w3.org/ns/org#>
    PREFIX gme:    <{GME}>
"""


def _val(b: dict[str, Any], k: str) -> str | None:
    e = b.get(k)
    return e["value"] if e else None


def fetch_persons(iris: list[str]) -> list[dict]:
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setReturnFormat(SPARQL_JSON)

    values = " ".join(f"<{iri}>" for iri in iris)
    sparql.setQuery(f"""
        {PREFIXES}
        SELECT ?iri ?name ?github ?email ?orcid ?infoscience ?url
               ?bio ?location ?company ?blog ?twitter ?avatar
               ?created_at ?updated_at ?public_repos ?followers
               (GROUP_CONCAT(DISTINCT ?contribution; SEPARATOR=",") AS ?contributions)
               (GROUP_CONCAT(DISTINCT ?owns_iri;     SEPARATOR=",") AS ?ownedRepos)
        WHERE {{
            VALUES ?iri {{ {values} }}
            ?iri schema:name ?name .
            OPTIONAL {{ ?iri pulse:githubUsername              ?github      }}
            OPTIONAL {{ ?iri schema:email                      ?email       }}
            OPTIONAL {{ ?iri pulse:orcidIdentifier             ?orcid       }}
            OPTIONAL {{ ?iri pulse:infosciencePersonIdentifier ?infoscience }}
            OPTIONAL {{ ?iri schema:url                        ?url         }}
            OPTIONAL {{ ?iri gme:bio                           ?bio         }}
            OPTIONAL {{ ?iri gme:location                      ?location    }}
            OPTIONAL {{ ?iri gme:company                       ?company     }}
            OPTIONAL {{ ?iri gme:blog                          ?blog        }}
            OPTIONAL {{ ?iri gme:twitter_username              ?twitter     }}
            OPTIONAL {{ ?iri gme:avatar_url                    ?avatar      }}
            OPTIONAL {{ ?iri gme:github_created_at             ?created_at  }}
            OPTIONAL {{ ?iri gme:github_updated_at             ?updated_at  }}
            OPTIONAL {{ ?iri gme:public_repos                  ?public_repos }}
            OPTIONAL {{ ?iri gme:followers_count               ?followers   }}
            OPTIONAL {{ ?iri pulse:hasContribution             ?contribution }}
            OPTIONAL {{ ?iri pulse:owns                        ?owns_iri    }}
        }}
        GROUP BY ?iri ?name ?github ?email ?orcid ?infoscience ?url
                 ?bio ?location ?company ?blog ?twitter ?avatar
                 ?created_at ?updated_at ?public_repos ?followers
    """)

    rows = sparql.query().convert()["results"]["bindings"]
    persons = []
    for r in rows:
        contribs = [v for v in (_val(r, "contributions") or "").split(",") if v]
        repos    = [v for v in (_val(r, "ownedRepos") or "").split(",") if v]
        persons.append({
            "iri":              _val(r, "iri"),
            "name":             _val(r, "name"),
            "github_username":  _val(r, "github"),
            "email":            _val(r, "email"),
            "orcid":            _val(r, "orcid"),
            "infoscience_id":   _val(r, "infoscience"),
            "url":              _val(r, "url"),
            "bio":              _val(r, "bio"),
            "location":         _val(r, "location"),
            "company":          _val(r, "company"),
            "blog":             _val(r, "blog"),
            "twitter_username": _val(r, "twitter"),
            "avatar_url":       _val(r, "avatar"),
            "github_created_at":_val(r, "created_at"),
            "github_updated_at":_val(r, "updated_at"),
            "public_repos":     int(_val(r, "public_repos")) if _val(r, "public_repos") else None,
            "followers_count":  int(_val(r, "followers")) if _val(r, "followers") else None,
            "has_contribution": contribs,
            "owns":             repos,
        })
    return persons


def main() -> None:
    from models import Person

    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    results = []  # (label, handles, is_duplicate, confidence, reason)

    for label, cluster_iris in CANDIDATE_CLUSTERS:
        handles = [iri.split("/")[-1] for iri in cluster_iris]
        log.info("\n%s  [%s]", "─" * 60, label)
        log.info("Cluster: %s", handles)

        raw = fetch_persons(cluster_iris)
        if len(raw) < 2:
            log.warning("  Could not fetch all persons, skipping")
            continue

        persons = []
        for p in raw:
            try:
                persons.append(Person(**p))
            except Exception as e:
                log.warning("  Skipping %s: %s", p.get("iri"), e)

        if len(persons) < 2:
            log.warning("  Not enough valid persons after validation, skipping")
            continue

        log.info("  Asking agent...")
        clusters = agent.find_duplicates(persons)

        for c in clusters:
            verdict = "DUPLICATE" if c.is_duplicate else "NOT duplicate"
            conf = c.certainty if c.is_duplicate else 1 - c.certainty
            log.info("  → %s  cert=%.2f  conf=%.2f  %s", verdict, c.certainty, conf, c.reason)
            results.append((label, handles, c.is_duplicate, conf, c.reason))

    # ── sorted summary ──────────────────────────────────────────────────────
    COL = 80
    print("\n\n" + "═" * COL)
    print(f"{'CONF':>5}  {'DUP':>3}  PAIR")
    print("─" * COL)
    for _label, handles, is_dup, conf, reason in sorted(results, key=lambda r: -r[3]):
        dupl_str = "✓" if is_dup else "✗"
        pair = f"{handles[0]}  /  {handles[-1]}"
        print(f"{conf:5.2f}   {dupl_str}   {pair}")
        print(f"             {reason}")
        print()


if __name__ == "__main__":
    main()
