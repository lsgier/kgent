from pydantic import BaseModel, Field


class DuplicateCluster(BaseModel):
    iris: list[str] = Field(description="IRIs of Person entities that refer to the same real-world person")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reason: str = Field(description="Brief explanation of why these entities are considered duplicates")
