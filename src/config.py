import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Secrets and endpoints — machine-specific, kept out of git (.env).
SPARQL_ENDPOINT = os.environ["SPARQL_ENDPOINT"]
SPARQL_USER     = os.getenv("SPARQL_USER")
SPARQL_PASSWORD = os.getenv("SPARQL_PASSWORD")
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_MODEL = os.environ["LLM_MODEL"]
AUDIT_LOG_PATH  = os.getenv("AUDIT_LOG_PATH", "audit.jsonl")
SPARQL_LOG_PATH = os.getenv("SPARQL_LOG_PATH", "sparql.jsonl")

# Tunable parameters — committed in pyproject.toml [tool.kgent] for reproducibility.
_params = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())["tool"]["kgent"]

CLUSTER_K         = _params["cluster"]["k"]
CLUSTER_THRESHOLD = _params["cluster"]["threshold"]
EMBEDDING_MODEL   = _params["embedding"]["model"]
EMBED_BATCH_SIZE  = _params["embedding"]["batch_size"]
EMBED_CONCURRENCY = _params["embedding"]["concurrency"]
