from datetime import date, datetime
from typing import Annotated

from pydantic import AnyUrl, BaseModel, Field, model_validator

Url = Annotated[str, AnyUrl]


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------

class Person(BaseModel):
    iri: str
    name: str
    github_username: str | None = None
    email: Annotated[str, Field(pattern=r'^[\w\-\.]+@([\w-]+\.)+[\w-]{2,4}$')] | None = None
    url: Url | None = None
    orcid: Annotated[str, Field(pattern=r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$')] | None = None
    infoscience_id: str | None = None
    has_contribution: list[str] = []   # IRIs of pulse:Contribution
    has_membership: list[str] = []     # IRIs of org:Membership
    owns: list[str] = []               # IRIs of schema:SoftwareSourceCode

    @model_validator(mode='after')
    def at_least_one_identifier(self) -> 'Person':
        if not any([self.github_username, self.email,
                    self.infoscience_id, self.orcid]):
            raise ValueError(
                'Person must have at least one of: github_username, email, '
                'infoscience_id, orcid'
            )
        return self


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class Organization(BaseModel):
    iri: str
    name: str
    ror_id: Annotated[str, Field(pattern=r'^https://ror\.org/[0-9a-z]{9}$')] | None = None
    github_handle: str | None = None
    infoscience_id: Annotated[
        str,
        Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
    ] | None = None
    org_type: str | None = None        # IRI from pulse:OrganizationTypeEnumeration
    github_followers: int | None = None
    has_unit: list[str] = []           # IRIs of org:Organization
    unit_of: list[str] = []            # IRIs of org:Organization
    owns: list[str] = []               # IRIs of schema:SoftwareSourceCode

    @model_validator(mode='after')
    def at_least_one_identifier(self) -> 'Organization':
        if not any([self.ror_id, self.github_handle, self.infoscience_id]):
            raise ValueError(
                'Organization must have at least one of: ror_id, github_handle, infoscience_id'
            )
        return self


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class Repository(BaseModel):
    iri: str
    name: str
    github_handle: Annotated[str, Field(pattern=r'^[a-zA-Z0-9\-_]+/[a-zA-Z0-9\-_\.]+$')]
    author_iris: list[str]             # schema:author — minCount 1
    repo_type: str | None = None       # IRI from pulse:RepositoryTypeEnumeration
    discipline: str | None = None      # IRI from pulse:DisciplineEnumeration
    github_stars: int | None = None
    github_forks: int | None = None
    date_created: datetime | None = None
    license: Url | None = None
    citation: Url | None = None
    programming_language: str | None = None
    owned_by: str | None = None        # IRI of Person or Organization
    is_fork_of: str | None = None      # IRI of schema:SoftwareSourceCode


# ---------------------------------------------------------------------------
# Contribution
# ---------------------------------------------------------------------------

class Contribution(BaseModel):
    iri: str
    repo_iri: str                      # pulse:contributionTo — minCount 1, maxCount 1
    person_iri: str                    # schema:author — minCount 1, maxCount 1
    count: int                         # pulse:contributionCount — minCount 1
    first_contribution_date: datetime | None = None
    last_contribution_date: datetime | None = None


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

class Membership(BaseModel):
    iri: str
    org_iri: str                       # org:organization — minCount 1, maxCount 1
    role: str | None = None
    start_date: date | None = None     # time:hasBeginning
    end_date: date | None = None       # time:hasEnd


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------

class Article(BaseModel):
    iri: str
    name: str
    doi: Annotated[str, Field(pattern=r'^10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+$')]
    date_published: date
    author_iris: list[str]             # schema:author — minCount 1
    infoscience_id: str | None = None
    source_org_iris: list[str] = []    # schema:sourceOrganization
