import logging
from orchestrator import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s — %(message)s")

if __name__ == "__main__":
    run()
