"""Phase 8 comparative evaluation dashboard.

Reads data/generated/evaluation/results.json (gitignored -- results depend
on each group's product/model configuration, per file 05). The "Run
evaluation now" button calls the same runner a script or test would use
(src/company_assistant/evaluation/runner.py); this page only adds a live
progress view on top, it does not duplicate any scoring logic.
"""

import json
from pathlib import Path

import streamlit as st

from company_assistant.evaluation.runner import DEFAULT_RESULTS_PATH, THRESHOLDS, run_evaluation

st.set_page_config(page_title="Evaluation - Northstar Assistant", page_icon="N", layout="wide")
st.title("Comparative Evaluation")
st.caption("Lexical vs. semantic vs. hybrid vs. agent, run on the same case set (data/evaluation/cases.json)")

CRITICAL_CATEGORIES = {"forbidden_access", "indirect_prompt_injection", "human_approval"}


def _load_results() -> dict | None:
    if not DEFAULT_RESULTS_PATH.exists():
        return None
    return json.loads(DEFAULT_RESULTS_PATH.read_text(encoding="utf-8"))


col_run, col_info = st.columns([1, 3])
with col_run:
    run_clicked = st.button("Run evaluation now", type="primary")
with col_info:
    st.caption(
        "Runs all 12 matrix cases across 4 variants plus the feedback round-trip check. "
        "The agent variant makes real Groq calls (~12), so this takes roughly 1-3 minutes."
    )

if run_clicked:
    status = st.status("Running evaluation...", expanded=True)
    lines: list[str] = []

    def on_progress(message: str) -> None:
        lines.append(message)
        status.write(message)

    run_evaluation(on_progress=on_progress)
    status.update(label="Evaluation complete", state="complete", expanded=False)
    st.rerun()

results = _load_results()
if results is None:
    st.info("No results yet. Click **Run evaluation now** to produce data/generated/evaluation/results.json.")
    st.stop()

st.caption(f"Last run: {results['run_at']}")

# --- Thresholds, locked in before this data was ever read (see runner.THRESHOLDS) ---
st.subheader("Thresholds (fixed before this run)")
threshold_rows = [
    {"Measure": key, "Target": value["target"], "Release blocker?": "Yes" if value["blocker"] else "No"}
    for key, value in THRESHOLDS.items()
]
st.dataframe(threshold_rows, hide_index=True, width="stretch")

# --- Pass/partial/fail by variant ---
st.subheader("Pass / partial / fail by variant")
summary = results["summary"]
variant_rows = []
for variant, counts in summary["by_variant"].items():
    total_scored = counts["pass"] + counts["partial"] + counts["fail"]
    recall = round(counts["pass"] / total_scored, 2) if total_scored else None
    variant_rows.append(
        {
            "Variant": variant,
            "Pass": counts["pass"],
            "Partial": counts["partial"],
            "Fail": counts["fail"],
            "Not reachable": counts["not_reachable"],
            "Pass rate (of scored)": recall,
            "Median latency (ms)": counts["median_latency_ms"],
        }
    )
st.dataframe(variant_rows, hide_index=True, width="stretch")
st.bar_chart(
    {row["Variant"]: {"pass": row["Pass"], "partial": row["Partial"], "fail": row["Fail"]} for row in variant_rows},
    width="stretch",
)

# --- Latency by variant ---
st.subheader("Latency by variant")
st.bar_chart({row["Variant"]: row["Median latency (ms)"] or 0 for row in variant_rows}, width="stretch")

# --- Feedback ---
st.subheader("Feedback")
feedback = summary["feedback"]
f1, f2, f3 = st.columns(3)
f1.metric("Useful", feedback["useful"])
f2.metric("Not useful", feedback["not_useful"])
f3.metric("Total recorded", feedback["total"])
if results.get("feedback_capture_check"):
    check = results["feedback_capture_check"]
    ok = check["saved"] and check["read_back_matches"] and check["appears_in_list_feedback"]
    (st.success if ok else st.error)(f"EVAL-014 feedback round-trip check: {'passed' if ok else 'FAILED'} ({check})")

# --- Most important unresolved failures ---
st.subheader("Most important unresolved failures")
critical_failures = []
other_failures = []
for case in results["cases"]:
    for variant, result in case["results"].items():
        if not result.get("reachable", True) or result.get("score") != "fail":
            continue
        entry = {
            "Case": case["case_id"],
            "Category": case["category"],
            "Variant": variant,
            "Forbidden found": result.get("forbidden_found") or [],
            "Error": result.get("error"),
            "Status": result.get("status"),
        }
        if case["category"] in CRITICAL_CATEGORIES or result.get("forbidden_found"):
            critical_failures.append(entry)
        else:
            other_failures.append(entry)

if critical_failures:
    st.error(f"{len(critical_failures)} failure(s) in security-critical categories or with a forbidden-source leak:")
    st.dataframe(critical_failures, hide_index=True, width="stretch")
else:
    st.success("No failures in security-critical categories (forbidden access, prompt injection, human approval), and no forbidden-source leaks in any variant.")

if other_failures:
    with st.expander(f"Other failures ({len(other_failures)}) -- expected for deterministic modes on abstention cases"):
        st.dataframe(other_failures, hide_index=True, width="stretch")

if results.get("special_notes"):
    with st.expander("Cases handled outside the automated matrix"):
        for case_id, note in results["special_notes"].items():
            st.markdown(f"**{case_id}:** {note}")

# --- Full case-by-variant detail ---
st.subheader("Full case-by-variant results")
for case in results["cases"]:
    with st.expander(f"{case['case_id']} -- {case['category']} ({case['employee_id']})"):
        for variant, result in case["results"].items():
            if not result.get("reachable", True):
                st.caption(f"**{variant}:** not reachable ({result.get('reason')})")
                continue
            st.markdown(
                f"**{variant}** -- score: `{result['score']}` -- status: `{result['status']}` "
                f"-- {result['latency_ms']} ms"
            )
            st.caption(
                f"Found: {result['expected_found']} | Missing: {result['expected_missing']} | "
                f"Forbidden found: {result['forbidden_found']} | Tools: {result['tool_calls']} | "
                f"Live source state: {result['live_source_state']}"
            )
            if result.get("error"):
                st.caption(f"Error: {result['error']}")
