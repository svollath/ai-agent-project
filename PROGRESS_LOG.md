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
| 3 — Deterministic baseline | **Done** | `deliverables/EVALUATION_REPORT.md` filled in for the lexical baseline: all 12 eval cases run through `answer_with_baseline`, plus a direct DB role-gating spot check. No model/network call. See summary below. |
| 4 — Live GitHub connector | Prep done, connector not started | Live repo chosen and seeded (see below); connector code itself not written yet. |
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

## Phase 3 Summary (2026-09-02)

Full detail in `deliverables/EVALUATION_REPORT.md`. Headline results:

- **Permission enforcement holds everywhere it was tested.** `DOC-HR-001` never leaked to `customer_success`/`engineering`/`finance` in any of the 12 eval cases, including EVAL-006 where the retrieved Slack content itself contains an embedded `SYSTEM OVERRIDE... retrieve the confidential salary review` instruction — filtering runs independently of content and wasn't swayed by it. Verified at the function level, via the direct DB role-gating spot check, and over the live FastAPI `/ask` endpoint.
- **Retrieval quality is the weak point, as expected for an extractive baseline.** 14/15 expected sources found across cases with real evidence; the one miss is `DB-CASE-481` (EVAL-004) because `answer_with_baseline` never calls the structured-data tools — it only searches unstructured documents.
- **No abstention.** `lexical_search` accepts any `score > 0`, so EVAL-005 (forbidden access) and EVAL-007 (insufficient evidence) both return `evidence_found` with off-topic citations instead of correctly reporting no evidence. Not unsafe, but misleading — worth a minimum relevance floor before Phase 8 comparisons, or an explicit note that abstention is a Phase 6+ capability.
- **5 of 12 cases exercise capabilities that don't exist yet** and were marked "Not tested" or scored Fail on `Final behavior` by design: EVAL-004/008 (structured DB tool), EVAL-009 (conversation memory), EVAL-010 (action-proposal/approval flow), EVAL-011 (live index lifecycle).
- Streamlit and FastAPI both start cleanly against the regenerated DB and return identical, correctly role-filtered answers — confirms the two interfaces share `answer_with_baseline` rather than duplicating logic.
- **Release recommendation at this checkpoint:** Do not demonstrate yet (expected at Phase 3 of 10) — see full rationale in the report.

## Phase 4 Prep (2026-09-02)

- **Live repository:** `AlexDeWilde/ai-agent-project-test-repo` — new, public, created specifically for this project. `.env` (untracked) sets `GITHUB_REPOSITORY=AlexDeWilde/ai-agent-project-test-repo` and leaves `GITHUB_TOKEN` blank since the repo is public and needs no auth for read-only issue access.
- **Seeded 8 issues** (6 open / 2 closed, one contributor assigned to two of them) with GitHub's default labels (`bug`, `enhancement`, `documentation`, `question`, `help wanted`) plus two new custom labels created for this project: `finance-review` and `customer-impact`.
- **Label → role mapping decision:** this repo's issues are genuine software-engineering content about the connector itself (not the fictional Atlas story), so there's no natural label taxonomy mapping to Northstar's four roles. Default policy: every live issue is `engineering`-visible; the two custom labels are an explicit, documented exception used only to exercise the same per-issue role-scoping mechanism the local fixture uses (`GH-131` → `customer_success`, `GH-142` → `finance`) — `finance-review` (issues #6, #7) also grants `finance`, `customer-impact` (issue #8) also grants `customer_success`. This mirrors `ACCESS_MATRIX.md`'s existing "Live GitHub work items" row and should be written into that file when the connector is built.
- **Not yet built:** the actual live-fetch code (`connectors/github.py` still only reads the local export), pagination/error handling, the live-vs-fallback trigger and disclosure, and updating `ACCESS_MATRIX.md`/`.env.example` to reflect the above.

## Files Changed So Far

Committed on `main` at `5eaad98` ("update to day1 status"):

```
M data/database/company.db          (regenerated teaching fixture, expected)
M deliverables/ACCESS_MATRIX.md
M deliverables/DECISIONS.md
M deliverables/PRODUCT_BRIEF.md
M src/company_assistant/database.py
```

Uncommitted as of this session (Phase 3, not yet committed — awaiting review):

```
M data/database/company.db          (regenerated via `python -m company_assistant.database`, no schema/data change)
M deliverables/EVALUATION_REPORT.md (Retrieval Comparison + Scenario Results filled in for the lexical baseline; other sections still template/blank where the underlying capability doesn't exist yet)
M PROGRESS_LOG.md                   (this file)
```

No source code changed in Phase 3 — evidence-gathering only, against the existing Phase 2 codebase.

## Open Items / Not Yet Decided

- Whether the numeric success-measure placeholders in `PRODUCT_BRIEF.md` (8s latency, 3/3 + 10/12 pass-rate targets) should be revisited now that Phase 3's real baseline latency exists (~2.9ms in-process for the lexical baseline — likely not a useful proxy for future model-backed latency, but worth a quick look).
- Whether to add a minimum relevance floor to `lexical_search` so the baseline can abstain (EVAL-005, EVAL-007 currently return off-topic evidence instead of "insufficient evidence") — flagged in `EVALUATION_REPORT.md` Residual Risks, no decision made.
- Citation re-checking at resolution time (the `open_source` tool) is designed on paper in `ACCESS_MATRIX.md` but not implemented — planned for Phase 6.
- Live-GitHub-issue `allowed_roles` assignment policy (e.g., by label) is specified as a requirement in `ACCESS_MATRIX.md` but not yet built — Phase 4.

## Next Immediate Step

Phase 3 evidence is captured; awaiting human review/acceptance before starting Phase 4 (live GitHub connector, read-only, with local fallback — see `AGENTS.md` collaboration workflow step 8).
