import logging

from agent import DedupAgent
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SPARQL_ENDPOINT
from repository import KnowledgeGraphRepository

log = logging.getLogger(__name__)


def run() -> None:
    repo = KnowledgeGraphRepository(SPARQL_ENDPOINT)
    agent = DedupAgent(model_name=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    log.info("Fetching persons...")
    persons = repo.get_persons()
    log.info("Found %d persons", len(persons))

    log.info("Running deduplication agent...")
    clusters = agent.find_duplicates(persons)
    log.info("Found %d duplicate clusters", len(clusters))

    for cluster in clusters:
        log.info(cluster)
