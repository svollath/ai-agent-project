"""Streamlit interface for the Northstar internal assistant."""

import json
from typing import get_args

import streamlit as st

from company_assistant.agent import answer_with_agent
from company_assistant.api import EMPLOYEES
from company_assistant.connectors.registry import load_all_documents_with_github_status
from company_assistant.feedback import record_feedback
from company_assistant.indexing import last_indexed_status, sync_index
from company_assistant.models import Answer, Feedback, FeedbackReason
from company_assistant.tools.actions import (
    approve_action,
    edit_action,
    execute_action,
    list_pending_proposals,
    reject_action,
)

st.set_page_config(page_title="Northstar Assistant", page_icon="N", layout="centered")

# Gives each main-area section a persistent, visible boundary — even when
# empty — instead of looking like broken/unstructured blank space. Targets
# st.container(key=...)'s auto-generated `st-key-<key>` wrapper class.
st.markdown(
    """
    <style>
    .st-key-user-box, .st-key-queue-box, .st-key-conversation-box {
        background-color: #f0f2f6;
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }
    /* The selectbox's own idle-state border is the same color as its
       background, so it's invisible until focused (when Streamlit turns it
       red) — inconsistent with the always-visible expander border next to
       it. Give it the same visible, neutral border the expander already
       has, only while not focused (leave the focus state untouched). */
    [data-testid="stSelectbox"] div[role="group"]:not(:focus-within) {
        border: 1px solid rgba(49, 51, 63, 0.2) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _history_messages(messages: list[dict]) -> list[dict]:
    """Turn stored session messages into the role/content shape the agent expects."""

    history = []
    for message in messages:
        if message["role"] == "user":
            history.append({"role": "user", "content": message["content"]})
        else:
            history.append(
                {"role": "assistant", "content": Answer.model_validate(message["answer"]).text}
            )
    return history


def render_feedback(answer: Answer) -> None:
    """Useful/not-useful control. Persists at most one record per answer."""

    state_key = f"feedback-{answer.answer_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = {"submitted": False, "show_reason": False}
    state = st.session_state[state_key]

    if state["submitted"]:
        st.caption("Feedback recorded — thank you.")
        return

    useful_col, not_useful_col = st.columns(2)
    if useful_col.button("Useful", key=f"{state_key}-useful"):
        record_feedback(
            Feedback(answer_id=answer.answer_id, rating="useful", retrieval_mode=answer.retrieval_mode)
        )
        state["submitted"] = True
        st.rerun()
    if not_useful_col.button("Not useful", key=f"{state_key}-not-useful"):
        state["show_reason"] = True

    if state["show_reason"]:
        reason = st.selectbox(
            "What went wrong? (optional)",
            options=[None, *get_args(FeedbackReason)],
            format_func=lambda r: "No reason given" if r is None else r.replace("_", " "),
            key=f"{state_key}-reason",
        )
        if st.button("Submit feedback", key=f"{state_key}-submit"):
            record_feedback(
                Feedback(
                    answer_id=answer.answer_id,
                    rating="not_useful",
                    reason=reason,
                    retrieval_mode=answer.retrieval_mode,
                )
            )
            state["submitted"] = True
            st.rerun()


def render_answer(answer: Answer) -> None:
    """Render the complete answer so citations and controls survive reruns."""

    banner = {
        "answered": st.success,
        "evidence_found": st.success,
        "insufficient_evidence": st.warning,
        "forbidden": st.error,
        "error": st.error,
    }.get(answer.status, st.info)
    banner(f"Status: `{answer.status}` | Retrieval: `{answer.retrieval_mode}`")

    st.markdown(answer.text)

    if answer.citations:
        with st.expander("Sources"):
            for citation in answer.citations:
                date = (
                    citation.occurred_at.date().isoformat()
                    if citation.occurred_at
                    else "No date"
                )
                if citation.source_path.startswith("http"):
                    title = f"[{citation.title}]({citation.source_path})"
                    st.markdown(f"- **{citation.source_id}** - {title} (`{citation.source_type}`, {date})")
                else:
                    st.markdown(f"- **{citation.source_id}** - {citation.title} (`{citation.source_type}`, {date})")
                    st.caption(citation.source_path)

    with st.expander("Tool trace"):
        if answer.trace:
            for step in answer.trace:
                st.markdown(f"- {step}")
        else:
            st.caption("No tool activity recorded.")

    if answer.action_proposal:
        st.warning(
            f"Action **{answer.action_proposal.action_type}** drafted for "
            f"`{answer.action_proposal.destination}` — see \"Pending actions\" above to "
            "approve or reject it. The agent cannot approve or execute it itself."
        )
        st.json(answer.action_proposal.payload)

    render_feedback(answer)


col_logo, col_title = st.columns([1, 6], vertical_alignment="center")
with col_logo:
    st.image("material/northstar-logo-256.png", width=64)
with col_title:
    st.title("Northstar Internal Assistant")
    st.caption("Permission-aware company knowledge prototype")

ROLE_BADGE_COLORS = {
    "engineering": ("rgba(28, 131, 255, 0.1)", "rgb(0, 84, 163)"),
    "customer_success": ("rgba(33, 195, 84, 0.1)", "rgb(21, 130, 55)"),
    "finance": ("rgba(255, 164, 33, 0.1)", "rgb(226, 102, 12)"),
    "people_operations": ("rgba(154, 93, 255, 0.1)", "rgb(88, 63, 132)"),
}

with st.container(key="user-box"):
    employee_id = st.selectbox(
        "Fictional employee profile",
        options=list(EMPLOYEES),
        format_func=lambda key: EMPLOYEES[key].display_name,
    )

employee = EMPLOYEES[employee_id]
role = employee.role

if st.session_state.get("active_employee_id") != employee_id:
    st.session_state.active_employee_id = employee_id
    st.session_state.messages = []
    for key in [
        k for k in st.session_state if k.startswith("feedback-") or k.startswith("editing-")
    ]:
        del st.session_state[key]

with st.sidebar:
    st.header("System status")
    index_status = last_indexed_status()
    if index_status is None:
        st.caption("Semantic index: not yet built")
    else:
        st.caption(
            f"Semantic index: {index_status['indexed_sources']} sources, "
            f"last synced {index_status['last_synced_at']}"
        )
    _, github_state = load_all_documents_with_github_status()
    st.caption(
        "GitHub source: local export + live repository"
        if github_state == "live"
        else "GitHub source: local export only (live unavailable or not configured)"
    )
    if st.button("Resync index"):
        with st.spinner("Syncing index..."):
            try:
                result = sync_index()
                st.success(
                    f"Synced: +{result.added} added, ~{result.updated} updated, "
                    f"-{result.removed} removed ({result.total_indexed} total)"
                )
            except Exception as error:  # surfaced to the user, never silently swallowed
                st.error(f"Sync failed: {error}")

pending_proposals = list_pending_proposals()
with st.container(key="queue-box"):
    with st.expander(f"Pending actions ({len(pending_proposals)})", expanded=bool(pending_proposals)):
        if not pending_proposals:
            st.caption("No actions awaiting approval.")
        for proposal in pending_proposals:
            with st.container(border=True):
                st.markdown(f"**{proposal.action_type}** → `{proposal.destination}`")
                st.caption(f"Requested by {proposal.requested_by} · {proposal.proposal_id}")
                st.json(proposal.payload)

                approve_col, reject_col, edit_col = st.columns(3)
                if approve_col.button("Approve", key=f"approve-{proposal.proposal_id}"):
                    try:
                        approve_action(proposal.proposal_id, employee)
                        execute_action(proposal.proposal_id, employee)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                if reject_col.button("Reject", key=f"reject-{proposal.proposal_id}"):
                    try:
                        reject_action(proposal.proposal_id, employee)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                editing_key = f"editing-{proposal.proposal_id}"
                if edit_col.button("Edit", key=f"edit-toggle-{proposal.proposal_id}"):
                    st.session_state[editing_key] = not st.session_state.get(editing_key, False)

                if st.session_state.get(editing_key):
                    raw_payload = st.text_area(
                        "Payload (JSON)",
                        value=json.dumps(proposal.payload, indent=2),
                        key=f"edit-area-{proposal.proposal_id}",
                    )
                    if st.button("Save edit", key=f"save-edit-{proposal.proposal_id}"):
                        try:
                            new_payload = json.loads(raw_payload)
                            edit_action(proposal.proposal_id, new_payload, employee)
                            st.session_state[editing_key] = False
                            st.rerun()
                        except (json.JSONDecodeError, ValueError) as error:
                            st.error(str(error))

if "messages" not in st.session_state:
    st.session_state.messages = []

conversation_box = st.container(key="conversation-box")
with conversation_box:
    if not st.session_state.messages:
        st.caption("No messages yet — ask a question below to get started.")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                render_answer(Answer.model_validate(message["answer"]))

# Renders the current role as a badge-styled overlay inside the chat input
# itself (left of the send button) — not a separate section, so it's
# automatically always visible: it rides along with the input, which
# Streamlit already pins to the bottom of the page natively. Colors match
# st.badge()'s own palette exactly (measured live), so it looks like a real
# badge despite being pure CSS, since st.chat_input has no slot for
# embedding an actual widget inside it.
badge_bg, badge_color = ROLE_BADGE_COLORS.get(role, ("rgba(49, 51, 63, 0.1)", "rgb(49, 51, 63)"))
st.markdown(
    f"""
    <style>
    [data-testid="stChatInput"]::before {{
        content: "{role}";
        position: absolute;
        right: 56px;
        top: 50%;
        transform: translateY(-50%);
        background-color: {badge_bg};
        color: {badge_color};
        padding: 0 4px;
        border-radius: 4px;
        font-size: 0.875rem;
        white-space: nowrap;
        pointer-events: none;
        z-index: 10;
    }}
    [data-testid="stChatInputTextArea"] {{
        padding-right: 160px !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

if question := st.chat_input("Ask about projects, customers, policies, or work items"):
    history = _history_messages(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": question})
    with conversation_box:
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.status("Thinking...", expanded=True) as status:
                answer = answer_with_agent(
                    question,
                    employee,
                    conversation_history=history,
                    on_step=status.write,
                )
                status.update(
                    label="Done" if answer.status != "error" else "Ran into an error",
                    state="complete" if answer.status != "error" else "error",
                    expanded=False,
                )
            render_answer(answer)
    st.session_state.messages.append(
        {"role": "assistant", "answer": answer.model_dump(mode="json")}
    )
    st.rerun()
