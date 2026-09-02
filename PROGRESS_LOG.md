# Progress Log

Working notes for continuity across sessions. Not a graded deliverable — the actual submissions live in `deliverables/`. Update this file at the end of each work session so any future session (or teammate) can resume without re-reading the whole conversation history.

## Availability This Week (refreshed 2026-09-02 13:57 CEST)

Lunch 13:00–13:30 every day.

| Day | Window | Status |
| --- | --- | --- |
| Tue 2026-09-01 | until 16:00 | Used — Phases 1–2 (Product Brief, Access Matrix) |
| **Wed 2026-09-02 (today)** | 12:00–16:00 | In progress — Phase 3 done this session; ~2h left today (now 13:57) for Phase 4 |
| Thu 2026-09-03 | 10:00–16:00 | Planned for Phases 5–7 |
| Fri 2026-09-04 | 10:00–12:00 | Planned for Phase 8 start only (2h) |

Flagged risk (unchanged, now more concrete): Phases 8–10 (comparative evaluation,
Docker packaging, release decision) do not fit in Friday's 2-hour window even if
Thursday's Phases 5–7 go smoothly — a follow-up session beyond Friday is likely
needed. Worth deciding now whether to compress scope (e.g. skip hybrid retrieval
comparison, or reduce the evaluation case set) or explicitly plan a Phase
8–10 session next week.

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
| 3 — Deterministic baseline | **Done, pending human review** | DB recreated; baseline exercised via `answer_with_baseline` directly (same function both `app.py` and `api.py` call) for 4 representative queries, plus direct `filter_permitted`/connector checks. Full evidence in `deliverables/EVALUATION_REPORT.md` ("Phase 3 — Deterministic Baseline Findings"). Key finding: HR record never leaks to any non-`people_operations` role (0/4); but the lexical baseline has no relevance threshold, so it returns permitted-but-irrelevant evidence for both a forbidden query (EVAL-005) and a no-evidence query (EVAL-007) instead of abstaining — a real product failure, distinct from a leak. Conflicting-evidence case (EVAL-003) retrieves all 3 expected sources but doesn't flag which is superseded (needs Phase 6 model/agent). Malformed-metadata handling verified to fail loudly (`ValueError`/Pydantic `ValidationError`), not silently. |
| 4 — Live GitHub connector | **Done, pending human review** | Connected `AlexDeWilde/ai-agent-project-test-repo` (public, no token) via new `connectors/github_live.py` (httpx, pagination, `state=all`, PR-filtering, by-label `allowed_roles`, real `html_url` citations). Wired additively into `registry.py`/`service.py` — verified via direct fetch, pagination stress test (no dupes/gaps across 4 pages), forced-failure test (`GitHubConnectorError`, no fabrication), and an actual FastAPI `/ask` call citing a live issue with a real URL. **Important correction made mid-phase:** first wired it as a swap (live replaces local GitHub), which would have broken every Atlas eval case (`GH-142`/`GH-149`) whenever the live repo was reachable — caught via regression-testing against Phase 3, fixed to merge (local Atlas export always loads, live issues are additive). Full detail: `deliverables/DECISIONS.md` ("Live GitHub repository is additive, not a swap"). **Known residual gap:** this repo's content is about the connector itself, not Atlas, so priority question 2 ("must work against live + local") is proven at the mechanism level, not with matching Atlas content on the live side — see `EVALUATION_REPORT.md`. |
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

## Files Changed So Far

Committed on `main` at `5eaad98` ("update to day1 status"):

```
M data/database/company.db          (regenerated teaching fixture, expected)
M deliverables/ACCESS_MATRIX.md
M deliverables/DECISIONS.md
M deliverables/PRODUCT_BRIEF.md
M src/company_assistant/database.py
```

Not yet committed (this session, Phases 3–4):

```
M data/database/company.db          (re-regenerated, byte-for-byte same fixture data)
M deliverables/EVALUATION_REPORT.md (Phase 3 baseline findings + Phase 4 live-connector evidence)
M deliverables/ACCESS_MATRIX.md     (Source Governance rows corrected to "additive" model; Enforcement Notes)
M deliverables/DECISIONS.md         (new decision: live GitHub is additive, not a swap)
M pyproject.toml, uv.lock           (added httpx as the live connector's HTTP client)
M src/company_assistant/service.py  (loads via load_all_documents_with_github_status; trace discloses live/local state)
M src/company_assistant/connectors/registry.py   (local GitHub always loads; live issues appended when reachable)
M src/company_assistant/connectors/__init__.py   (exports load_all_documents_with_github_status)
A src/company_assistant/connectors/github_live.py (new: live fetch, pagination, by-label roles, GitHubConnectorError)
M .env                              (added GITHUB_REPOSITORY; GITHUB_TOKEN left blank — repo is public)
```

## Open Items / Not Yet Decided

- Whether the numeric success-measure placeholders in `PRODUCT_BRIEF.md` (8s latency, 3/3 + 10/12 pass-rate targets) should be revisited once Phase 3's real baseline latency exists. (No timer was instrumented in Phase 3 — calls were sub-second in-process with no model/network round trip, so this is still open.)
- Citation re-checking at resolution time (the `open_source` tool) is designed on paper in `ACCESS_MATRIX.md` but not implemented — planned for Phase 6.
- Whether the abstention gap found in Phase 3 (baseline returns irrelevant-but-permitted evidence instead of abstaining, EVAL-005/EVAL-007) should be patched with a minimal relevance-score cutoff in the lexical baseline itself, or left as-is and solved only by the semantic/agent layers in Phase 5–6 (current lean: leave it — `AGENTS.md` says "preserve the lexical baseline" and the whole point of Phase 3 is to document this as the comparison point, not fix it prematurely).
- **New from Phase 4:** priority question 2 ("which Atlas GitHub issues are open, live + local") isn't content-complete — the live repo (`AlexDeWilde/ai-agent-project-test-repo`) has no Atlas-themed issues, so the live path proves connector mechanics, not the actual Atlas answer. Decide whether to (a) ask the repo owner to add 1–2 Atlas/billing-labeled issues, (b) accept and explicitly narrow priority question 2's wording, or (c) leave as a named residual risk for Phase 8. See `DECISIONS.md`.

## Next Immediate Step

Phase 4 evidence is captured in `deliverables/EVALUATION_REPORT.md` and `DECISIONS.md`.
Per `AGENTS.md`'s collaboration workflow, this needs human review/acceptance — including
a call on the priority-question-2 content gap above — before Phase 5 starts.
Once accepted: begin Phase 5 (managed RAG) per `04-connected-rag-and-agent.md` — build
Chroma + local Hugging Face embeddings, combine with the existing lexical baseline into
a comparable hybrid mode, and design the index lifecycle (upserts, deletions, last-indexed
status) per its "Manage the Index Lifecycle" section.
