"""Streamlit interface for the Northstar internal assistant project."""

import uuid

import streamlit as st

from company_assistant.agent import answer_with_agent, decide_action_proposal
from company_assistant.api import EMPLOYEES
from company_assistant.app_state import (
    get_feedback_for_answer,
    list_pending_proposals,
    save_feedback,
)
from company_assistant.indexing import DEFAULT_SEMANTIC_INDEX_DIR, read_last_indexed
from company_assistant.models import Answer, Feedback

REASON_CATEGORIES = ["missing_source", "wrong_answer", "stale_evidence", "bad_citation", "other"]


def render_answer(answer: Answer) -> None:
    """Render the complete answer so citations survive Streamlit reruns."""

    st.caption(f"Status: `{answer.status}` | Retrieval: `{answer.retrieval_mode}`")
    for warning in answer.warnings:
        st.warning(warning)
    st.markdown(answer.text)
    if answer.citations:
        with st.expander("Sources"):
            for citation in answer.citations:
                date = (
                    citation.occurred_at.date().isoformat()
                    if citation.occurred_at
                    else "No date"
                )
                if citation.source_path.startswith(("http://", "https://")):
                    link = f" — [Open source]({citation.source_path})"
                else:
                    link = f" — `{citation.source_path}`"
                st.markdown(
                    f"- **{citation.source_id}** - {citation.title} "
                    f"(`{citation.source_type}`, {date}){link}"
                )
    with st.expander("Execution trace"):
        for step in answer.trace:
            st.markdown(f"- {step}")
    if answer.action_proposal:
        st.warning("Action awaiting separate approval — see the sidebar's Pending approvals panel.")
        st.markdown(f"**Action:** {answer.action_proposal.action_type}")
        st.markdown(f"**Destination:** {answer.action_proposal.destination}")
        st.json(answer.action_proposal.payload)

    existing_feedback = get_feedback_for_answer(answer.answer_id)
    if existing_feedback is not None:
        note = f" ({existing_feedback.reason_category})" if existing_feedback.reason_category else ""
        st.caption(f"Feedback recorded: {existing_feedback.rating}{note}")
        return

    rating_value = st.feedback("thumbs", key=f"feedback_{answer.answer_id}")
    if rating_value == 1:
        save_feedback(
            Feedback(
                answer_id=answer.answer_id,
                conversation_id=st.session_state.conversation_id,
                rating="useful",
                retrieval_mode=answer.retrieval_mode,
            )
        )
        st.rerun()
    elif rating_value == 0:
        reason = st.selectbox(
            "What went wrong? (optional)",
            options=[None, *REASON_CATEGORIES],
            format_func=lambda value: "Select a reason..." if value is None else value,
            key=f"reason_{answer.answer_id}",
        )
        if st.button("Submit feedback", key=f"submit_feedback_{answer.answer_id}"):
            save_feedback(
                Feedback(
                    answer_id=answer.answer_id,
                    conversation_id=st.session_state.conversation_id,
                    rating="not_useful",
                    reason_category=reason,
                    retrieval_mode=answer.retrieval_mode,
                )
            )
            st.rerun()


def render_pending_approvals(employee_id: str) -> None:
    """A persisted, always-visible panel: pending proposals survive a page reload."""

    st.subheader("Pending approvals")
    pending = list_pending_proposals(EMPLOYEES[employee_id])
    if not pending:
        st.caption("No pending actions for this employee.")
        return

    for proposal in pending:
        with st.expander(f"{proposal.proposal_id} — {proposal.action_type}"):
            st.markdown(f"**Destination:** {proposal.destination}")
            st.caption("Saving an edit keeps this pending — approve it separately after.")
            with st.form(key=f"decide_{proposal.proposal_id}"):
                title = st.text_input("Title", value=proposal.payload.get("title", ""))
                body = st.text_area("Body", value=proposal.payload.get("body", ""))
                labels = st.text_input(
                    "Labels (comma-separated)", value=proposal.payload.get("labels", "")
                )
                approve = st.form_submit_button("Approve")
                edit = st.form_submit_button("Save edit (stays pending)")
                reject = st.form_submit_button("Reject")

            employee = EMPLOYEES[employee_id]
            if approve:
                decide_action_proposal(proposal.proposal_id, employee, "approve")
                st.rerun()
            elif reject:
                decide_action_proposal(proposal.proposal_id, employee, "reject")
                st.rerun()
            elif edit:
                decide_action_proposal(
                    proposal.proposal_id,
                    employee,
                    "edit",
                    {"title": title, "body": body, "labels": labels},
                )
                st.rerun()


st.set_page_config(page_title="Northstar Assistant", page_icon="N", layout="centered")
st.title("Northstar Internal Assistant")
st.caption("Permission-aware company knowledge prototype")

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_employee_id" not in st.session_state:
    st.session_state.selected_employee_id = None

employee_id = st.selectbox(
    "Fictional employee profile",
    options=list(EMPLOYEES),
    format_func=lambda key: f"{EMPLOYEES[key].display_name} - {EMPLOYEES[key].role}",
)

# get_conversation_history() filters only by conversation_id, not employee_id,
# so switching roles mid-session would otherwise let the agent read back a
# prior turn framed for a different role. Reset both on switch.
if employee_id != st.session_state.selected_employee_id:
    st.session_state.selected_employee_id = employee_id
    st.session_state.conversation_id = str(uuid.uuid4())
    st.session_state.messages = []

with st.sidebar:
    st.header("Prototype status")
    last_indexed = read_last_indexed(DEFAULT_SEMANTIC_INDEX_DIR)
    st.caption(
        f"Last indexed: {last_indexed.isoformat() if last_indexed else 'Never (ask a question to build it)'}"
    )
    render_pending_approvals(employee_id)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            render_answer(Answer.model_validate(message["answer"]))

if question := st.chat_input("Ask about projects, customers, policies, or work items"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = answer_with_agent(
                question, EMPLOYEES[employee_id], conversation_id=st.session_state.conversation_id
            )
        render_answer(answer)
    st.session_state.messages.append(
        {"role": "assistant", "answer": answer.model_dump(mode="json")}
    )
