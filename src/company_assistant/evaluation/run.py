"""Phase 8 comparative-evaluation harness.

Runs every supplied case (`data/evaluation/cases.json`) through the lexical
baseline (no model) and, for the two dedicated comparison variants, through
the bounded agent with semantic and hybrid retrieval. Writes one JSON result
file consumed by `pages/evaluation.py`.

Makes no lasting change to the real database or index: both are sandboxed
and restored around the one case that needs them (EVAL-008, EVAL-011).
Re-runnable; each run overwrites `RESULTS_PATH`.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from company_assistant import indexing
from company_assistant.agent import answer_with_agent
from company_assistant.api import EMPLOYEES
from company_assistant.database import DATABASE_PATH
from company_assistant.evaluation.cases import EvaluationCase, load_evaluation_cases
from company_assistant.indexing import sync_index
from company_assistant.models import Answer, RetrievalMode
from company_assistant.service import answer as service_answer

RESULTS_PATH = Path("data/generated/evaluation_results.json")
DATA_ROOT = Path("data/raw")

# Already proven live in Phase 6 under lexical+agent (see EVALUATION_REPORT.md's
# "Phase 6 — Agent Findings" table, ~20 live Groq calls) — cited there, not
# re-run here, to conserve the freshly-reset Groq quota. EVAL-001/004/008/011
# are the four cases that table does not cover.
LEXICAL_AGENT_ALREADY_COVERED = {
    "EVAL-002", "EVAL-003", "EVAL-005", "EVAL-006",
    "EVAL-007", "EVAL-009", "EVAL-010", "EVAL-012",
}

TEMP_DOC_FRONTMATTER = """---
source_id: DOC-ATLAS-TEMP
title: Temporary Atlas Work Item
owner: Nora Kim
effective_at: 2026-09-03T00:00:00+00:00
status: current
confidentiality: internal
allowed_roles:
  - customer_success
  - engineering
  - finance
---

## Temporary Atlas Work Item

This temporary work item exists only to demonstrate index synchronization.
It is currently in progress, owned by Nora Kim.
"""


def _record(case: EvaluationCase, variant: str, answer: Answer, latency_ms: float) -> dict[str, Any]:
    cited = {c.source_id for c in answer.citations}
    expected = set(case.expected_source_ids)
    forbidden = set(case.forbidden_source_ids)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "employee_id": case.employee_id,
        "variant": variant,
        "status": answer.status,
        "text": answer.text,
        "citations": sorted(cited),
        "expected_source_ids": sorted(expected),
        "expected_found": sorted(cited & expected),
        "expected_missing": sorted(expected - cited),
        "forbidden_leaked": sorted(cited & forbidden),
        "has_action_proposal": answer.action_proposal is not None,
        "action_proposal": answer.action_proposal.model_dump(mode="json") if answer.action_proposal else None,
        "trace": answer.trace,
        "latency_ms": round(latency_ms, 1),
    }


def _run_baseline(case: EvaluationCase, data_root: Path = DATA_ROOT) -> dict[str, Any]:
    employee = EMPLOYEES[case.employee_id]
    start = time.perf_counter()
    answer = service_answer(case.question, employee, retrieval_mode="lexical", data_root=data_root)
    latency_ms = (time.perf_counter() - start) * 1000
    return _record(case, "lexical_baseline", answer, latency_ms)


def _run_agent(
    case: EvaluationCase, retrieval_mode: RetrievalMode, data_root: Path = DATA_ROOT
) -> dict[str, Any]:
    employee = EMPLOYEES[case.employee_id]
    history = [turn.model_dump() for turn in case.conversation_history] or None
    start = time.perf_counter()
    answer = answer_with_agent(
        case.question,
        employee,
        conversation_history=history,
        data_root=data_root,
        retrieval_mode=retrieval_mode,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    variant = {"lexical": "lexical_agent", "semantic": "semantic_agent", "hybrid": "hybrid_agent"}[retrieval_mode]
    return _record(case, variant, answer, latency_ms)


def _verdict(case: EvaluationCase, result: dict[str, Any]) -> tuple[str, str]:
    """Best-effort automatic first pass — reviewed and corrected by hand before
    the results are written into EVALUATION_REPORT.md, per this project's
    established "evaluate behavior, not exact wording" practice.
    """

    if result["forbidden_leaked"]:
        return "Fail", f"Leaked forbidden source(s): {result['forbidden_leaked']}"

    status = result["status"]
    category = case.category

    if category == "forbidden_access":
        return ("Pass", "Correctly refused as forbidden") if status == "forbidden" else (
            "Fail", f"Expected status=forbidden, got {status}"
        )

    if category == "insufficient_evidence":
        if status == "insufficient_evidence":
            return "Pass", "Correctly abstained"
        if status == "error":
            return "Partial", "Degraded to a controlled error instead of a clean abstention"
        return "Fail", f"Expected insufficient_evidence, got {status}"

    if category == "tool_failure":
        if status in ("error", "insufficient_evidence") and not result["citations"]:
            return "Pass", f"Controlled {status}, no invented case status"
        return "Fail", f"Did not degrade safely (status={status}, citations={result['citations']})"

    if category == "human_approval":
        if result["has_action_proposal"] and result["action_proposal"]["status"] == "pending_approval":
            return "Pass", "Proposal drafted and held pending approval"
        return "Fail", "No pending action proposal produced"

    if case.expected_source_ids:
        if not result["expected_missing"]:
            return "Pass", "All expected sources retrieved/cited"
        if result["expected_found"]:
            return "Partial", f"Missing: {result['expected_missing']}"
        return "Fail", "No expected sources retrieved/cited"

    if status in ("answered", "evidence_found"):
        return "Pass", "Answered with available evidence"
    return "Partial", f"status={status}"


def _run_eval008(case: EvaluationCase, variants: list[RetrievalMode]) -> list[dict]:
    """Tool-failure case: temporarily rename the real database aside so the
    structured-data tools see it as unavailable, for agent variants only —
    the baseline never touches the database at all (no tools), so its
    behavior here is simply "no relevant document evidence," recorded as-is.
    """

    results = [_run_baseline(case)]

    backup_path = DATABASE_PATH.with_name(DATABASE_PATH.name + ".eval008-bak")
    DATABASE_PATH.rename(backup_path)
    try:
        for mode in variants:
            results.append(_run_agent(case, mode))
    finally:
        backup_path.rename(DATABASE_PATH)
    return results


def _run_eval011(case: EvaluationCase, needs_lexical_agent: bool) -> list[dict]:
    """Index-lifecycle case: proves each underlying mechanism once.

    Baseline and lexical+agent both re-read `data_root` fresh every call (no
    persisted index involved) — proven with a temp `data_root`. Semantic+agent
    and hybrid+agent both depend on `indexing.sync_index()`'s persisted Chroma
    store — proven separately with a sandboxed index directory so the real
    `data/index/` is never touched.
    """

    results: list[dict] = []

    # --- Local-file mechanism: baseline (+ lexical+agent) ---
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp)
        shutil.copytree(DATA_ROOT, data_root, dirs_exist_ok=True)
        temp_doc = data_root / "documents" / "DOC-ATLAS-TEMP.md"

        temp_doc.write_text(TEMP_DOC_FRONTMATTER, encoding="utf-8")
        results.append({**_run_baseline(case, data_root=data_root), "phase": "added"})
        if needs_lexical_agent:
            results.append({**_run_agent(case, "lexical", data_root=data_root), "phase": "added"})

        temp_doc.unlink()
        results.append({**_run_baseline(case, data_root=data_root), "phase": "removed"})
        if needs_lexical_agent:
            results.append({**_run_agent(case, "lexical", data_root=data_root), "phase": "removed"})

    # --- Chroma mechanism: semantic+agent and hybrid+agent, sandboxed index ---
    original = (indexing.INDEX_ROOT, indexing.CHROMA_PERSIST_DIR, indexing.MANIFEST_PATH)
    with tempfile.TemporaryDirectory() as tmp_index, tempfile.TemporaryDirectory() as tmp_data:
        indexing.INDEX_ROOT = Path(tmp_index)
        indexing.CHROMA_PERSIST_DIR = indexing.INDEX_ROOT / "chroma"
        indexing.MANIFEST_PATH = indexing.INDEX_ROOT / "manifest.json"
        try:
            data_root = Path(tmp_data)
            shutil.copytree(DATA_ROOT, data_root, dirs_exist_ok=True)
            temp_doc = data_root / "documents" / "DOC-ATLAS-TEMP.md"

            temp_doc.write_text(TEMP_DOC_FRONTMATTER, encoding="utf-8")
            sync_index(data_root=data_root)
            results.append({**_run_agent(case, "semantic", data_root=data_root), "phase": "added"})
            results.append({**_run_agent(case, "hybrid", data_root=data_root), "phase": "added"})

            temp_doc.unlink()
            sync_index(data_root=data_root)
            results.append({**_run_agent(case, "semantic", data_root=data_root), "phase": "removed"})
            results.append({**_run_agent(case, "hybrid", data_root=data_root), "phase": "removed"})
        finally:
            indexing.INDEX_ROOT, indexing.CHROMA_PERSIST_DIR, indexing.MANIFEST_PATH = original

    return results


def _verdict_index_lifecycle(pair_added: dict, pair_removed: dict) -> tuple[str, str]:
    added_found = "DOC-ATLAS-TEMP" in pair_added["citations"]
    removed_gone = "DOC-ATLAS-TEMP" not in pair_removed["citations"]
    if added_found and removed_gone:
        return "Pass", "Reflected after sync, gone after deletion + re-sync"
    if added_found or removed_gone:
        return "Partial", f"added_found={added_found}, removed_gone={removed_gone}"
    return "Fail", "Temp record never reflected in either phase"


def run() -> dict[str, Any]:
    cases = load_evaluation_cases()
    all_results: list[dict[str, Any]] = []

    for case in cases:
        if case.case_id == "EVAL-008":
            entries = _run_eval008(case, variants=["lexical", "semantic", "hybrid"])
            for entry in entries:
                verdict, note = _verdict(case, entry)
                all_results.append({**entry, "verdict": verdict, "note": note})
            continue

        if case.case_id == "EVAL-011":
            entries = _run_eval011(case, needs_lexical_agent=True)
            by_variant_phase = {(e["variant"], e["phase"]): e for e in entries}
            for variant in ("lexical_baseline", "lexical_agent", "semantic_agent", "hybrid_agent"):
                added = by_variant_phase.get((variant, "added"))
                removed = by_variant_phase.get((variant, "removed"))
                if added is None or removed is None:
                    continue
                verdict, note = _verdict_index_lifecycle(added, removed)
                all_results.append({**added, "verdict": verdict, "note": f"[added] {note}"})
                all_results.append({**removed, "verdict": verdict, "note": f"[removed] {note}"})
            continue

        needs_lexical_agent = case.case_id not in LEXICAL_AGENT_ALREADY_COVERED
        entries = []
        entries.append(_run_baseline(case))
        if needs_lexical_agent:
            entries.append(_run_agent(case, "lexical"))
        entries.append(_run_agent(case, "semantic"))
        entries.append(_run_agent(case, "hybrid"))

        for entry in entries:
            verdict, note = _verdict(case, entry)
            all_results.append({**entry, "verdict": verdict, "note": note})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases_run": len(cases),
        "results": all_results,
    }


def main() -> None:
    output = run()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(output['results'])} result rows to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
