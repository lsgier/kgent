from dotenv import load_dotenv
import os

load_dotenv()

SPARQL_ENDPOINT = os.environ["SPARQL_ENDPOINT"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_MODEL = os.environ["LLM_MODEL"]
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
AUDIT_LOG_PATH  = os.getenv("AUDIT_LOG_PATH", "audit.jsonl")
SPARQL_LOG_PATH = os.getenv("SPARQL_LOG_PATH", "sparql.jsonl")
