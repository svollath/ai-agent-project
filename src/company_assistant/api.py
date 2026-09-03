"""FastAPI boundary for the internal assistant application layer."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from company_assistant.agent import answer_with_agent
from company_assistant.connectors.registry import load_all_documents_with_github_status
from company_assistant.feedback import record_feedback
from company_assistant.indexing import last_indexed_status
from company_assistant.models import (
    ActionProposal,
    Answer,
    EmployeeContext,
    EmployeeRole,
    Feedback,
    FeedbackRating,
    FeedbackReason,
    RetrievalMode,
)
from company_assistant.tools.actions import (
    approve_action,
    edit_action,
    execute_action,
    list_pending_proposals,
    reject_action,
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


def _employee_or_404(employee_id: str) -> EmployeeContext:
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown employee profile.",
        )
    return employee


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    employee_id: str
    conversation_id: str | None = None
    conversation_history: list[dict] | None = None
    retrieval_mode: RetrievalMode = "lexical"


class HealthResponse(BaseModel):
    status: str
    employee_roles: list[EmployeeRole]


class StatusResponse(BaseModel):
    last_indexed: dict | None
    github_state: str


class FeedbackRequest(BaseModel):
    answer_id: str
    rating: FeedbackRating
    reason: FeedbackReason | None = None
    retrieval_mode: RetrievalMode = "lexical"


class ApproverRequest(BaseModel):
    employee_id: str


class EditActionRequest(BaseModel):
    employee_id: str
    payload: dict[str, str | int | float | bool | None | list[str]]


@app.get("/health")
def health() -> HealthResponse:
    """Return a small readiness response without calling a model or reading disk."""

    return HealthResponse(
        status="ok",
        employee_roles=[
            "customer_success",
            "engineering",
            "people_operations",
            "finance",
        ],
    )


@app.get("/status")
def system_status() -> StatusResponse:
    """Surface index freshness and GitHub connector state for visibility."""

    _, github_state = load_all_documents_with_github_status(Path("data/raw"))
    return StatusResponse(last_indexed=last_indexed_status(), github_state=github_state)


@app.post("/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    """Run the bounded agent for one known fictional employee."""

    employee = _employee_or_404(request.employee_id)
    return answer_with_agent(
        request.question,
        employee,
        conversation_history=request.conversation_history,
        retrieval_mode=request.retrieval_mode,
    )


@app.post("/feedback", response_model=Feedback)
def submit_feedback(request: FeedbackRequest) -> Feedback:
    """Persist one minimal useful/not-useful record."""

    feedback = Feedback(
        answer_id=request.answer_id,
        rating=request.rating,
        reason=request.reason,
        retrieval_mode=request.retrieval_mode,
    )
    record_feedback(feedback)
    return feedback


@app.get("/actions/pending", response_model=list[ActionProposal])
def pending_actions() -> list[ActionProposal]:
    """List every action awaiting a separate human approval."""

    return list_pending_proposals()


@app.post("/actions/{proposal_id}/approve", response_model=ActionProposal)
def approve(proposal_id: str, request: ApproverRequest) -> ActionProposal:
    """Approve then immediately, controllably execute a pending proposal.

    A single endpoint for both steps mirrors the approval state diagram in
    `04-connected-rag-and-agent.md` (Approve leads directly to Controlled
    execution); `execute_action` still separately rechecks the proposal's
    state right before running.
    """

    approver = _employee_or_404(request.employee_id)
    try:
        approve_action(proposal_id, approver)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return execute_action(proposal_id, approver)


@app.post("/actions/{proposal_id}/reject", response_model=ActionProposal)
def reject(proposal_id: str, request: ApproverRequest) -> ActionProposal:
    approver = _employee_or_404(request.employee_id)
    try:
        return reject_action(proposal_id, approver)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@app.post("/actions/{proposal_id}/edit", response_model=ActionProposal)
def edit(proposal_id: str, request: EditActionRequest) -> ActionProposal:
    editor = _employee_or_404(request.employee_id)
    try:
        return edit_action(proposal_id, request.payload, editor)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
