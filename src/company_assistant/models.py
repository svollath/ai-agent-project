"""Shared application contracts."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

EmployeeRole = Literal[
    "customer_success",
    "engineering",
    "people_operations",
    "finance",
]
AnswerStatus = Literal[
    "evidence_found",
    "answered",
    "insufficient_evidence",
    "forbidden",
    "error",
]
RetrievalMode = Literal["lexical", "semantic", "hybrid"]
ActionStatus = Literal[
    "pending_approval",
    "approved",
    "rejected",
    "executed",
    "failed",
]
ReasonCategory = Literal[
    "missing_source",
    "wrong_answer",
    "stale_evidence",
    "bad_citation",
    "other",
]


class EmployeeContext(BaseModel):
    """Identity information propagated into retrieval and tools."""

    employee_id: str
    display_name: str
    role: EmployeeRole


class CompanyDocument(BaseModel):
    """Normalized record shared by all unstructured-source connectors."""

    source_id: str
    source_type: Literal["slack", "email", "document", "github"]
    title: str
    content: str
    source_path: str
    allowed_roles: frozenset[EmployeeRole]
    confidentiality: Literal["internal", "restricted"] = "internal"
    author: str | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Permission-approved search result returned by the baseline retriever."""

    document: CompanyDocument
    score: float


class Citation(BaseModel):
    """Stable reference to one retrieved company source."""

    source_id: str
    title: str
    source_type: str
    source_path: str
    occurred_at: datetime | None = None


class ActionProposal(BaseModel):
    """Exact operation that remains inert until a separate approval step."""

    proposal_id: str
    action_type: str
    destination: str
    payload: dict[str, str | int | float | bool | None]
    requested_by: str
    status: ActionStatus = "pending_approval"


class Answer(BaseModel):
    """Interface-independent answer contract."""

    answer_id: str = Field(default_factory=lambda: f"ANS-{uuid.uuid4().hex[:8]}")
    status: AnswerStatus
    text: str
    retrieval_mode: RetrievalMode = "lexical"
    citations: list[Citation] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    action_proposal: ActionProposal | None = None


class Feedback(BaseModel):
    """Persisted useful/not-useful rating for one answer turn."""

    answer_id: str
    conversation_id: str
    rating: Literal["useful", "not_useful"]
    reason_category: ReasonCategory | None = None
    retrieval_mode: RetrievalMode
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
