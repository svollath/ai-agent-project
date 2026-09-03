"""FastAPI boundary for the internal assistant application layer."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from company_assistant.agent import answer_with_agent, decide_action_proposal
from company_assistant.app_state import (
    ApprovalDecision,
    get_action_proposal,
    list_pending_proposals,
    save_feedback,
)
from company_assistant.indexing import DEFAULT_SEMANTIC_INDEX_DIR, read_last_indexed
from company_assistant.models import (
    ActionProposal,
    Answer,
    EmployeeContext,
    EmployeeRole,
    Feedback,
    ReasonCategory,
    RetrievalMode,
)

app = FastAPI(title="Northstar Internal Assistant", version="0.1.0")

EMPLOYEES = {
    "maya": EmployeeContext(
        employee_id="maya", display_name="Maya Chen", role="customer_success"
    ),
    "leo": EmployeeContext(
        employee_id="leo", display_name="Leo Martins", role="engineering"
    ),
    "priya": EmployeeContext(
        employee_id="priya", display_name="Priya Shah", role="people_operations"
    ),
    "omar": EmployeeContext(
        employee_id="omar", display_name="Omar Haddad", role="finance"
    ),
}


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    employee_id: str
    conversation_id: str | None = None


class AskResponse(BaseModel):
    conversation_id: str
    answer: Answer


class HealthResponse(BaseModel):
    status: str
    employee_roles: list[EmployeeRole]
    last_indexed: datetime | None = None


class DecideProposalRequest(BaseModel):
    employee_id: str
    decision: ApprovalDecision
    edited_payload: dict[str, str | int | float | bool | None] | None = None


class FeedbackRequest(BaseModel):
    answer_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    rating: Literal["useful", "not_useful"]
    reason_category: ReasonCategory | None = None
    retrieval_mode: RetrievalMode


def _resolve_employee(employee_id: str) -> EmployeeContext:
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown employee profile.",
        )
    return employee


@app.get("/health")
def health() -> HealthResponse:
    """Return a small readiness response without calling a model."""

    return HealthResponse(
        status="ok",
        employee_roles=[
            "customer_success",
            "engineering",
            "people_operations",
            "finance",
        ],
        # read_last_indexed only reads the on-disk manifest — it never
        # constructs a SemanticIndex (which would load the embeddings model),
        # so /health keeps its documented "no model call" contract.
        last_indexed=read_last_indexed(DEFAULT_SEMANTIC_INDEX_DIR),
    )


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Run the Groq-backed agent for one known fictional employee.

    Returns the conversation_id used for this turn — generated here when the
    caller omits one — so a stateless HTTP client can continue the same
    conversation on its next call.
    """

    employee = _resolve_employee(request.employee_id)
    conversation_id = request.conversation_id or str(uuid.uuid4())
    answer = answer_with_agent(request.question, employee, conversation_id=conversation_id)
    return AskResponse(conversation_id=conversation_id, answer=answer)


@app.get("/proposals", response_model=list[ActionProposal])
def list_proposals(employee_id: str) -> list[ActionProposal]:
    """List one employee's proposals still awaiting a decision."""

    employee = _resolve_employee(employee_id)
    return list_pending_proposals(employee)


@app.post("/proposals/{proposal_id}/decide", response_model=ActionProposal)
def decide_proposal(proposal_id: str, request: DecideProposalRequest) -> ActionProposal:
    """Approve, reject, or edit one pending proposal via a separate user interaction."""

    employee = _resolve_employee(request.employee_id)
    if get_action_proposal(proposal_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No such proposal: {proposal_id}",
        )
    try:
        return decide_action_proposal(
            proposal_id, employee, request.decision, request.edited_payload
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.post("/feedback", response_model=Feedback)
def submit_feedback(request: FeedbackRequest) -> Feedback:
    """Persist a useful/not-useful rating for one answer."""

    feedback = Feedback(
        answer_id=request.answer_id,
        conversation_id=request.conversation_id,
        rating=request.rating,
        reason_category=request.reason_category,
        retrieval_mode=request.retrieval_mode,
        created_at=datetime.now(UTC),
    )
    save_feedback(feedback)
    return feedback
