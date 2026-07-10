from typing import Annotated

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------

class Person(BaseModel):
    iri: str
    name: str
    github_username: str | None = None
    email: Annotated[str, Field(pattern=r'^[\w\-\.]+@([\w-]+\.)+[\w-]{2,4}$')] | None = None
    url: str | None = None
    orcid: Annotated[str, Field(pattern=r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$')] | None = None
    infoscience_id: str | None = None
    has_contribution: list[str] = []   # IRIs of pulse:Contribution
    has_membership: list[str] = []     # IRIs of org:Membership
    owns: list[str] = []               # IRIs of schema:SoftwareSourceCode
    # GME enrichment fields — agent context only, not written back to the graph
    bio: str | None = None
    location: str | None = None
    company: str | None = None
    blog: str | None = None
    twitter_username: str | None = None
    avatar_url: str | None = None
    github_created_at: str | None = None
    github_updated_at: str | None = None
    public_repos: int | None = None
    followers_count: int | None = None

    @model_validator(mode='after')
    def at_least_one_identifier(self) -> 'Person':
        if not any([self.github_username, self.email,
                    self.infoscience_id, self.orcid]):
            raise ValueError(
                'Person must have at least one of: github_username, email, '
                'infoscience_id, orcid'
            )
        return self
