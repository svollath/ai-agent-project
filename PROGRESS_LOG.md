# Progress Log

Working notes for continuity across sessions. Not a graded deliverable — the actual submissions live in `deliverables/`. Update this file at the end of each work session so any future session (or teammate) can resume without re-reading the whole conversation history.

## Availability This Week (as of 2026-09-01)

Lunch 13:00–13:30 every day.

| Day | Window |
| --- | --- |
| Tue 2026-09-01 (today) | until 16:00 |
| Wed 2026-09-02 | 12:00–16:00 |
| Thu 2026-09-03 | 10:00–16:00 |
| Fri 2026-09-04 | 10:00–12:00 |

Flagged risk: Phases 8–10 (comparative evaluation, Docker packaging, release decision) will not comfortably fit after Phase 4–7 work on Thursday — likely needs a follow-up session beyond Friday.

## Product Direction (Locked In)

- **Primary employee profile:** Leo Martins, Software Engineer.
- **Workflow:** release-readiness and blocker triage for the Atlas billing migration — "what's blocking this release, why did the date move, what's next, and who owns it" — synthesized from Slack, GitHub issues, and release docs instead of manual cross-referencing.
- **Priority questions** (see `deliverables/PRODUCT_BRIEF.md` for full detail):
  1. What is blocking the Atlas release, why did the target date move from 5 Sept to 18 Sept, and what's the resolution path?
  2. Which Atlas GitHub issues are still open, and who owns them (live repo + local fallback)?
  3. Draft an issue asking Finance to validate the Atlas reconciliation fix (human-approval demo case).
- Full source/case grounding: `GH-142`, `GH-149`, `DOC-ATLAS-403`, `SLACK-ATLAS-101/102/103`, eval cases `EVAL-002/005/006/009/010/011/012`.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| 1 — Product Brief | **Done** | `deliverables/PRODUCT_BRIEF.md` complete. Merged two independently-drafted versions (mine + a parallel `PRODUCT_BRIEF_adw01.md` from another agent/tool run, since deleted by the user). |
| 2 — Access Matrix | **Done** | `deliverables/ACCESS_MATRIX.md` complete, grounded in actual fixture `allowed_roles`/`confidentiality` values (not guessed). Two judgment calls approved by the user (see Decisions below). |
| 3 — Deterministic baseline | **Not started** | Next step. Recreate the DB, run Streamlit baseline, capture evidence Leo can retrieve Atlas evidence but never `DOC-HR-001`. No model/network call needed. |
| 4 — Live GitHub connector | Not started | |
| 5 — Managed RAG (Chroma, hybrid) | Not started | |
| 6 — Tools + agent | Not started | Database-layer role checks (see below) are already done ahead of this phase; still need LangChain tool wrappers + the agent itself. |
| 7 — Full product experience | Not started | |
| 8 — Comparative evaluation | Not started | |
| 9 — Docker packaging | Not started | |
| 10 — Decide and demonstrate | Not started | |

## Key Decisions Made Today

Full detail in `deliverables/DECISIONS.md`. Summary:

1. **Customer communications access is per-record, not a blanket per-role rule.** Engineering sees the two Atlas customer emails (`EMAIL-ACME-301/302`) but not the general customer-ops Slack channel (`SLACK-CX-201`) — matches what's already encoded in the fixtures' `allowed_roles`. Approved.
2. **SQLite access split by table**, not treated as one "financial records" blob: `projects` table → Allow `customer_success`/`engineering`/`finance`; `customers`/`support_cases` tables → Allow only `customer_success`/`finance`. Approved.
3. **Closed the `get_support_case()` permission gap immediately** (rather than deferring to Phase 6), since it was small and contained to the data layer:
   - `src/company_assistant/database.py`: `get_support_case()` now requires an `employee: EmployeeContext` argument and returns `None` for both "not found" and "role denied" (so a denied role can't infer a record exists).
   - Added `list_project_status(employee, path=...)`, same deny-by-default pattern, returns `[]` when denied.
   - Verified directly (no model/network call) with normal, denied, and not-found inputs — see transcript around this decision for the exact checks run.
   - Phase 6 still needs to wrap both as typed LangChain tools that receive `employee` from verified caller identity, not from the model.

## Files Changed So Far (uncommitted)

```
M data/database/company.db          (regenerated teaching fixture, expected)
M deliverables/ACCESS_MATRIX.md
M deliverables/DECISIONS.md
M deliverables/PRODUCT_BRIEF.md
M src/company_assistant/database.py
```

Nothing has been committed yet — all work is in the working tree on `main`.

## Open Items / Not Yet Decided

- Whether the numeric success-measure placeholders in `PRODUCT_BRIEF.md` (8s latency, 3/3 + 10/12 pass-rate targets) should be revisited once Phase 3's real baseline latency exists.
- Citation re-checking at resolution time (the `open_source` tool) is designed on paper in `ACCESS_MATRIX.md` but not implemented — planned for Phase 6.
- Live-GitHub-issue `allowed_roles` assignment policy (e.g., by label) is specified as a requirement in `ACCESS_MATRIX.md` but not yet built — Phase 4.

## Next Immediate Step

Start Phase 3: run `uv run python -m company_assistant.database`, start the Streamlit app and FastAPI, and capture baseline evidence (one permitted query, one forbidden query for Leo, one missing-answer query, one conflicting-evidence query) into `deliverables/EVALUATION_REPORT.md`.
