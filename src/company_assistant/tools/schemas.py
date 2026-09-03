"""Typed inputs and outputs for every agent-facing tool.

Keeping these separate from `models.py` (the application-layer contracts)
because tool schemas are what the model sees and fills in — narrower and more
defensive than the internal `CompanyDocument`/`SearchResult` types.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """One permitted, citable piece of evidence returned by a search tool."""

    source_id: str
    title: str
    source_type: str
    excerpt: str
    occurred_at: datetime | None = None


class SearchCompanyKnowledgeResult(BaseModel):
    query: str
    results: list[EvidenceItem] = Field(default_factory=list)


class WorkItem(BaseModel):
    """One GitHub issue, ranked only against other GitHub issues.

    Kept separate from `search_company_knowledge` so GitHub evidence never
    has to compete with Slack/email/documents for a shared top-k window —
    see the Phase 5 finding in `deliverables/DECISIONS.md`.
    """

    source_id: str
    title: str
    state: str | None = None
    number: int | None = None
    owner_or_author: str | None = None
    url: str
    occurred_at: datetime | None = None


class SearchWorkItemsResult(BaseModel):
    query: str
    results: list[WorkItem] = Field(default_factory=list)


class SupportCaseResult(BaseModel):
    """Deny-by-default: `found=False` for both "not found" and "not permitted".

    Never distinguishes the two reasons, so a denied role cannot infer that a
    case exists from the tool's response shape (matches `database.py`'s
    existing `get_support_case()` contract).
    """

    found: bool
    case_id: str
    subject: str | None = None
    status: str | None = None
    severity: str | None = None
    owner: str | None = None
    updated_at: str | None = None
    source_id: str | None = None


class ProjectStatusItem(BaseModel):
    source_id: str
    project_id: str
    name: str
    owner: str
    status: str
    target_date: str


class ListProjectStatusResult(BaseModel):
    results: list[ProjectStatusItem] = Field(default_factory=list)


class OpenSourceResult(BaseModel):
    """Re-resolves a citation at the moment it's opened, not from a cache.

    `found=False` covers "no such source" and "no longer permitted"
    identically — same deny-by-default shape as `SupportCaseResult`.
    """

    found: bool
    source_id: str
    title: str | None = None
    source_type: str | None = None
    content: str | None = None
    source_path: str | None = None
    occurred_at: datetime | None = None
