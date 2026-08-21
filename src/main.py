import logging
from orchestrator import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s — %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per embedding/LLM HTTP call otherwise
logging.getLogger("httpx2").setLevel(logging.WARNING)  # pydantic-ai's newer HTTP client, same reason

if __name__ == "__main__":
    run()
