import json

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import Person


SYSTEM_PROMPT = """
You are an expert at identifying duplicate entities in knowledge graphs.

You will receive a list of Person entities in JSON format. Your task is to identify
groups of entities that refer to the same real-world person.

Rules:
- Only group entities you are confident are duplicates — when in doubt, do not group.
- Return only groups with at least 2 entities.
- If no duplicates are found, return an empty list.

Each duplicate group must have exactly these fields:
- "entities": list of IRI strings (the "iri" field values of the duplicate persons)
- "confidence": float between 0.0 and 1.0
- "reason": short explanation string
""".strip()


class DuplicateCluster(BaseModel):
    entities: list[str] = Field(description="IRIs of Person entities that refer to the same real-world person")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reason: str = Field(description="Brief explanation of why these entities are considered duplicates")


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

    def find_duplicates(self, persons: list[Person]) -> list[DuplicateCluster]:
        user_prompt = json.dumps(
            [p.model_dump() for p in persons],
            indent=2,
            default=str,
        )
        result = self._agent.run_sync(user_prompt)
        return result.output
