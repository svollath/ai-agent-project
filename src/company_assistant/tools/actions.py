"""Action proposals: draftable by the agent, approvable only by a human.

`propose_action` is the only function in this module wrapped as an
agent-callable tool. `approve_action`, `reject_action`, `edit_action`, and
`execute_action` are plain functions with no tool wrapper at all, so the
agent has no way to call them, and text inside a retrieved document (a
prompt-injection attempt) has no path to invoking them either — approval can
only come from whatever separate, human-facing interaction calls these
functions directly (a future Streamlit control, in Phase 7).

State is an in-memory, per-process store. That's a known, accepted limitation
for this prototype (no persistence across restarts) — see `DECISIONS.md`.
"""

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from company_assistant.models import ActionProposal, EmployeeContext

_PROPOSALS: dict[str, ActionProposal] = {}


class AuditEvent(TypedDict):
    proposal_id: str
    event: str
    actor: str
    at: str


_AUDIT_LOG: list[AuditEvent] = []


def _record(proposal_id: str, event: str, actor: str) -> None:
    _AUDIT_LOG.append(
        AuditEvent(proposal_id=proposal_id, event=event, actor=actor, at=datetime.now(UTC).isoformat())
    )


def build_propose_action_tool(employee: EmployeeContext):
    def propose_action(
        action_type: str,
        destination: str,
        payload: dict[str, str | int | float | bool | None | list[str]],
    ) -> dict:
        """Draft an exact action for a separate human approval step.

        Creates a proposal in `pending_approval` state and returns it. This
        tool has no ability to approve, edit, reject, or execute anything —
        it can only draft. Always show the exact destination and payload
        before assuming a human will approve it.
        """

        proposal = ActionProposal(
            proposal_id=f"ACTION-{uuid.uuid4().hex[:8]}",
            action_type=action_type,
            destination=destination,
            payload=payload,
            requested_by=employee.employee_id,
            status="pending_approval",
        )
        _PROPOSALS[proposal.proposal_id] = proposal
        _record(proposal.proposal_id, "drafted", employee.employee_id)
        return proposal.model_dump(mode="json")

    return propose_action


def get_proposal(proposal_id: str) -> ActionProposal | None:
    return _PROPOSALS.get(proposal_id)


def list_pending_proposals() -> list[ActionProposal]:
    return [p for p in _PROPOSALS.values() if p.status == "pending_approval"]


def list_audit_log(proposal_id: str | None = None) -> list[AuditEvent]:
    if proposal_id is None:
        return list(_AUDIT_LOG)
    return [event for event in _AUDIT_LOG if event["proposal_id"] == proposal_id]


def edit_action(
    proposal_id: str,
    payload: dict[str, str | int | float | bool | None | list[str]],
    editor: EmployeeContext,
) -> ActionProposal:
    """Update a still-pending proposal's payload. Never called by the agent."""

    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise ValueError(f"No such proposal: {proposal_id}")
    if proposal.status != "pending_approval":
        raise ValueError(f"Proposal {proposal_id} is {proposal.status}, not pending_approval")
    proposal.payload = payload
    _record(proposal_id, "edited", editor.employee_id)
    return proposal


def reject_action(proposal_id: str, approver: EmployeeContext) -> ActionProposal:
    """Reject a pending proposal. Never called by the agent."""

    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise ValueError(f"No such proposal: {proposal_id}")
    if proposal.status != "pending_approval":
        raise ValueError(f"Proposal {proposal_id} is {proposal.status}, not pending_approval")
    proposal.status = "rejected"
    _record(proposal_id, "rejected", approver.employee_id)
    return proposal


def approve_action(proposal_id: str, approver: EmployeeContext) -> ActionProposal:
    """Approve a pending proposal. Never called by the agent.

    Must come from a separate, human-facing interaction — a proposal's own
    payload or any retrieved document text can never satisfy this call.
    Refuses self-approval: the employee who requested the action cannot also
    approve it.
    """

    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise ValueError(f"No such proposal: {proposal_id}")
    if proposal.status != "pending_approval":
        raise ValueError(f"Proposal {proposal_id} is {proposal.status}, not pending_approval")
    if approver.employee_id == proposal.requested_by:
        raise ValueError("The requester cannot approve their own proposal")
    proposal.status = "approved"
    _record(proposal_id, "approved", approver.employee_id)
    return proposal


def execute_action(proposal_id: str, approver: EmployeeContext) -> ActionProposal:
    """Simulate executing an approved proposal. Never called by the agent.

    Rechecks that the proposal is actually `approved` (not, say, already
    executed or somehow still pending) immediately before running. This
    project keeps every action's effect simulated — see `AGENTS.md`'s
    read-only mandate — so "execution" here only transitions state and
    records the outcome; it never calls a real write API.
    """

    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise ValueError(f"No such proposal: {proposal_id}")
    if proposal.status != "approved":
        proposal.status = "failed"
        _record(proposal_id, "failed", approver.employee_id)
        return proposal
    proposal.status = "executed"
    _record(proposal_id, "executed", approver.employee_id)
    return proposal
