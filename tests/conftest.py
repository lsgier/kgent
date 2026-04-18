import os

# Provide dummy values so config.py can be imported without a real .env file.
# dotenv's load_dotenv() does NOT override env vars that are already set,
# so these only take effect when the real .env is absent (e.g. CI).
os.environ.setdefault("SPARQL_ENDPOINT", "http://localhost:7200/test")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
