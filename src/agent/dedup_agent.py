import json

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from audit import LLMLog
from models import Person


SYSTEM_PROMPT = """
You are an expert at identifying duplicate person records in a knowledge graph of open-source contributors.

You will receive a list of Person entities in JSON format. Your task is to decide whether they refer to the same real-world individual who appears under multiple identities (e.g. personal vs. institutional account, old vs. new account, different username conventions).

You MUST always return exactly one result containing ALL input entity IRIs.

## Evidence to weigh

Strong signals FOR the same person:
- Username is a variation of the other (suffix, prefix, numeric appendage, full name appended)
- Shared contribution to the same repository
- Matching name, hashed email, twitter handle, blog URL, or ORCID
- One account has almost no activity and was created later — typical of a lost-credentials or context-switch duplicate

Signals that do NOT distinguish separate people:
- Different avatar, creation date, follower/repo counts — these naturally differ on a secondary account
- Contributing to different repositories — people use different accounts for different contexts

## Output fields
- "entities": all input IRI strings
- "is_duplicate": true if same real-world person
- "certainty": float 0.0–1.0 — how certain you are in your verdict, regardless of direction. 1.0 = completely certain, 0.5 = coin flip.
- "reason": one or two sentences citing the decisive evidence
""".strip()


class DuplicateCluster(BaseModel):
    entities: list[str] = Field(description="IRIs of all input Person entities")
    is_duplicate: bool = Field(description="Whether these entities refer to the same real-world person")
    certainty: float = Field(ge=0.0, le=1.0, description="Certainty in the verdict: 1.0=completely certain, 0.5=coin flip")
    reason: str = Field(description="Brief explanation of the decision")


class DedupAgent:
    def __init__(self, model_name: str, base_url: str, api_key: str, llm_log: LLMLog | None = None):
        model = OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )
        self._agent = Agent(
            model=model,
            output_type=DuplicateCluster,
            system_prompt=SYSTEM_PROMPT,
        )
        self._llm_log = llm_log

    def find_duplicates(self, persons: list[Person]) -> list[DuplicateCluster]:
        user_prompt = json.dumps(
            [p.model_dump(exclude_defaults=True) for p in persons],
            indent=2,
            default=str,
        )
        result = self._agent.run_sync(user_prompt)
        if self._llm_log:
            self._llm_log.log(user_prompt, result.output.model_dump())
        return [result.output]
