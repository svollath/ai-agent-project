"""Minimal supplied interface for the Northstar internal assistant project."""

import streamlit as st

from company_assistant.api import EMPLOYEES
from company_assistant.models import Answer
from company_assistant.service import answer_with_baseline


def render_answer(answer: Answer) -> None:
    """Render the complete answer so citations survive Streamlit reruns."""

    st.caption(f"Status: `{answer.status}` | Retrieval: `{answer.retrieval_mode}`")
    st.markdown(answer.text)
    if answer.citations:
        with st.expander("Sources"):
            for citation in answer.citations:
                date = (
                    citation.occurred_at.date().isoformat()
                    if citation.occurred_at
                    else "No date"
                )
                st.markdown(
                    f"- **{citation.source_id}** - {citation.title} "
                    f"(`{citation.source_type}`, {date})"
                )
    with st.expander("Execution trace"):
        for step in answer.trace:
            st.markdown(f"- {step}")
    if answer.action_proposal:
        st.warning("Action awaiting separate approval")
        st.markdown(f"**Action:** {answer.action_proposal.action_type}")
        st.markdown(f"**Destination:** {answer.action_proposal.destination}")
        st.json(answer.action_proposal.payload)


st.set_page_config(page_title="Northstar Assistant", page_icon="N", layout="centered")
st.title("Northstar Internal Assistant")
st.caption("Permission-aware company knowledge prototype")

employee_id = st.selectbox(
    "Fictional employee profile",
    options=list(EMPLOYEES),
    format_func=lambda key: f"{EMPLOYEES[key].display_name} - {EMPLOYEES[key].role}",
)

with st.sidebar:
    st.header("Prototype status")
    st.info(
        "The starter uses lexical retrieval and does not call a model. "
        "Replace this baseline with your evaluated tool-using agent."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

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

    answer = answer_with_baseline(question, EMPLOYEES[employee_id])
    with st.chat_message("assistant"):
        render_answer(answer)
    st.session_state.messages.append(
        {"role": "assistant", "answer": answer.model_dump(mode="json")}
    )
