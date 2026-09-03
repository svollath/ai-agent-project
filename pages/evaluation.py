"""Phase 8 evaluation dashboard: reads the harness's results and recorded feedback.

Read-only — never re-runs the harness or writes feedback. Verdicts are the
hand-reviewed ones written back into `evaluation_results.json` after Phase
8's manual review; see `EVALUATION_REPORT.md`'s "Phase 8" section for the
reasoning behind each correction.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from company_assistant.feedback import list_feedback

RESULTS_PATH = Path("data/generated/evaluation_results.json")

st.set_page_config(page_title="Evaluation — Northstar Assistant", page_icon="N", layout="wide")
st.title("Evaluation results")

if not RESULTS_PATH.exists():
    st.warning("No results yet — run `uv run python -m company_assistant.evaluation.run` first.")
    st.stop()

data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
results = pd.DataFrame(data["results"])
st.caption(
    f"Generated {data['generated_at']} — {data['cases_run']} cases, {len(results)} result rows"
)

st.subheader("Pass / Partial / Fail / N/A by category")
by_category = results.groupby(["category", "verdict"]).size().unstack(fill_value=0)
for column in ("Pass", "Partial", "Fail", "N/A"):
    if column not in by_category.columns:
        by_category[column] = 0
st.dataframe(by_category[["Pass", "Partial", "Fail", "N/A"]], use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Expected-evidence coverage by variant")
    with_expected = results[results["expected_source_ids"].map(len) > 0].copy()
    with_expected["coverage"] = with_expected["expected_found"].map(len) / with_expected[
        "expected_source_ids"
    ].map(len)
    st.bar_chart(with_expected.groupby("variant")["coverage"].mean())

with col_b:
    st.subheader("Mean latency by variant (ms)")
    st.bar_chart(results.groupby("variant")["latency_ms"].mean())

st.subheader("Feedback")
feedback = list_feedback()
if feedback:
    useful = sum(1 for entry in feedback if entry.rating == "useful")
    not_useful = len(feedback) - useful
    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("Useful", useful)
    metric_col2.metric("Not useful", not_useful)
    st.dataframe(
        pd.DataFrame([entry.model_dump(mode="json") for entry in feedback]),
        use_container_width=True,
    )
else:
    st.info("No feedback recorded yet — use the chat page's Useful / Not useful buttons.")

st.subheader("Unresolved failures")
unresolved = results[results["verdict"].isin(["Fail", "Partial"])][
    ["case_id", "variant", "verdict", "note"]
].sort_values(["case_id", "variant"])
st.dataframe(unresolved, use_container_width=True, hide_index=True)
