import json

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent.output import DuplicateCluster
from agent.prompts import SYSTEM_PROMPT
from models import Person


class DedupAgent:
    def __init__(self, model_name: str, base_url: str, api_key: str):
        model = OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )
        self._agent = Agent(
            model=model,
            output_type=list[DuplicateCluster],
            system_prompt=SYSTEM_PROMPT,
        )

    # -------------------------------------------------------------------------
    # Result validator — hook for feedback loop (e.g. SHACL validation)
    # -------------------------------------------------------------------------
    # @self._agent.output_validator
    # async def validate(self, clusters: list[DuplicateCluster]) -> list[DuplicateCluster]:
    #     ...

    def find_duplicates(self, persons: list[Person]) -> list[DuplicateCluster]:
        user_prompt = json.dumps(
            [p.model_dump() for p in persons],
            indent=2,
            default=str,
        )
        result = self._agent.run_sync(user_prompt)
        return result.output
