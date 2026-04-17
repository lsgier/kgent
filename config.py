from dotenv import load_dotenv
import os

load_dotenv()

SPARQL_ENDPOINT = os.environ["SPARQL_ENDPOINT"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_MODEL = os.environ["LLM_MODEL"]
