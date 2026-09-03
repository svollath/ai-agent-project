# Progress Log

Working notes for continuity across sessions. Not a graded deliverable — the actual submissions live in `deliverables/`. Update this file at the end of each work session so any future session (or teammate) can resume without re-reading the whole conversation history.

## Availability This Week (refreshed 2026-09-03 11:09 CEST)

Lunch 13:00–13:30 every day.

| Day | Window | Status |
| --- | --- | --- |
| Tue 2026-09-01 | until 16:00 | Used — Phases 1–2 (Product Brief, Access Matrix) |
| Wed 2026-09-02 | 12:00–~17:30 (ran past the planned end) | Phases 3, 4, and 5 all done |
| **Thu 2026-09-03 (today)** | 10:00–16:00 | Phase 6 (tools + agent), Phase 7 (full product experience), and Phase 8 (comparative evaluation) all completed this session — see Phase Status below |
| Fri 2026-09-04 | 10:00–12:00 | Planned for Phase 9 (Docker packaging) start |

Flagged risk (updated): Phases 6, 7, and 8 all landed Thursday. Groq's
free-tier daily token quota (200k TPD) was hit twice this session — once
during Phase 7's live testing, and again at the start of Phase 8, where a
"new" API key issued within the *same organization* did not reset it (only
a genuinely different-org key did). Any future live-evaluation batch should
confirm the org differs before assuming a key rotation helps, and should
still budget for pacing across more than one day or a paid tier. Phase 8
also surfaced a real, undecided product question (documented, not fixed —
see `DECISIONS.md`): the agent can exhaust its tool-call budget on
ambiguously-worded questions. Phases 9–10 still likely won't fit in a single
2-hour session — worth deciding whether to compress scope or plan a
follow-up.

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
| 5 — Managed RAG (Chroma, hybrid) | **Done, pending human review** | New `indexing.py` (chunking, manifest, `sync_index()`/`rebuild_index()`) + `retrieval.semantic_search()`/`hybrid_search()` (RRF, k=60) alongside the untouched lexical baseline; `service.answer()` now takes a `retrieval_mode`. Verified: permissions enforced *inside* Chroma via per-role boolean metadata + `where` filter (HR-record test + a Priya positive control); full EVAL-011 index-lifecycle proof (add → sync → retrievable → delete → sync → gone) run in an isolated sandbox that never touched the real index; `rebuild_index()` recovers from a corrupted manifest. Compared all 3 modes on 6 cases: **lexical wins on this fixture** (4/6 recall, 0.15 ms) vs. hybrid (3/6, 8.4 ms) and semantic (2/6, 9.1 ms) — kept lexical as the default. Full detail and worked RRF examples (one recovery, one instructive near-miss) in `EVALUATION_REPORT.md`'s Phase 5 section and `DECISIONS.md`. **New finding, not a regression from this phase but surfaced by its comparison work:** EVAL-012 / "which GitHub issues are open" fails expected-source recall in *all three* modes because the live connector's same-dated issues out-tie the older local Atlas fixture at `limit=4` — deliberately not patched by raising `limit`; flagged as justification for Phase 6's `search_work_items` tool instead. See Open Items. |
| 6 — Tools + agent | **Done, pending human review** | Tool layer (`src/company_assistant/tools/`): `search_company_knowledge`, `search_work_items` (fixes Phase 5's GitHub top-*k* gap), `get_support_case`, `list_project_status`, `open_source`, `propose_action`, all verified with normal/denied/empty/failure inputs; identity injected via closure (verified via schema inspection — no tool exposes `employee`); full approve/reject/edit/execute lifecycle with no tool wrapper on any of the four (agent structurally cannot call them). Agent runtime (`src/company_assistant/agent/`): one bounded `create_agent` + `ChatGroq` (`openai/gpt-oss-20b`), `ToolStrategy`-based structured output (`AgentAnswer`), citations verified against actual tool results before becoming real `Citation`s (never trust the model's self-report). Tested with ~20 **live Groq calls** across 8 EVAL cases — see `EVALUATION_REPORT.md`'s Phase 6 sections and 5 new `DECISIONS.md` entries for full evidence. **Two real bugs found and fixed via live testing:** (1) `ActionProposal.payload` was too narrow (no array values — Groq rejected a natural `labels: [...]` field, widened the type); (2) the agent burned its whole tool-call budget rephrasing an unanswerable query instead of abstaining, and separately conflated "sounds financial" with "forbidden" — both fixed (a tool-call-count cap on `search_company_knowledge` specifically, plus a clearer forbidden-vs-insufficient-evidence prompt section), verified 3/3 clean afterward. **New reliability finding (not a bug in this code):** `openai/gpt-oss-20b` on Groq intermittently fails to produce a valid structured tool call (malformed JSON, a "functions."-prefixed name, or plain text instead of a tool call) — always safely caught as `status="error"`, never a crash or fabrication; recommend `ModelRetryMiddleware` in Phase 7/8. Also hit Groq's free-tier rate limit (8000 TPM) after ~20 calls in quick succession — pace future live-evaluation batches. Security properties (no HR leak, injection resistance, no self-approval, no execution without approval) held across every live run. |
| 7 — Full product experience | **Done, pending human review** | `app.py`/`api.py` now call `agent.answer_with_agent()` instead of the Phase 3 lexical-only baseline. Streamlit gained: identity-switch history clearing (a self-identified gap in the starter, see below), a system-status sidebar (index freshness, GitHub state, manual "Resync index" button), a "Pending actions" panel with Approve/Reject/Edit buttons calling `tools.actions` directly (never through the agent), status-colored answer banners, conditional clickable citations, a renamed "Tool trace" expander, and a Useful/Not-useful (+ reason) feedback control persisting to a new `feedback.py` module (JSONL under `data/feedback/`). FastAPI gained `/status`, `/feedback`, and `/actions/{id}/approve\|reject\|edit`, plus an agent-backed `/ask`. Verified live in a real browser (no project run skill existed, so a one-off Playwright driver script was used) and via `fastapi.testclient.TestClient` for the API — see `EVALUATION_REPORT.md`'s new Phase 7 section and 5 new `DECISIONS.md` entries. **Two real findings from live testing:** (1) the Phase 0 starter never cleared chat history on identity switch — a real cross-identity evidence-leak vector, fixed; (2) `ModelRetryMiddleware`'s default `retry_on` was retrying Groq's daily-token-quota (TPD) 429s, which can never succeed within a few backed-off seconds — narrowed to exclude `ModelRateLimitError` specifically. Groq's 200k-token daily quota was hit (~99.5% used) partway through live testing; every failure degraded safely to `status="error"`, never a crash or fabrication, confirming the safety design holds under a real production-like failure. |
| 8 — Comparative evaluation | **Done, pending human review** | New `src/company_assistant/evaluation/run.py` harness ran all 12 cases through the lexical baseline, the shipped lexical+agent default (only the 4 cases Phase 6 hadn't already covered live), and semantic+agent/hybrid+agent (all 12 each) — 44 live result rows, `data/generated/evaluation_results.json`. **Release-blocking metric: 0 forbidden-source leaks across all 44 rows.** Verdicts hand-corrected after reviewing actual stored text/citations/traces (13 corrections vs. the harness's automatic first pass — written back into the JSON so the report and the new `pages/evaluation.py` dashboard never disagree): 25 Pass / 7 Partial / 8 Fail / 4 N/A (structural baseline limitations). **Two operational findings, same session:** (1) a "new" Groq API key issued within the *same organization* as an already-exhausted one does not reset the daily quota — confirmed the hard way; only a genuinely different-org key worked. (2) New product weakness: EVAL-011/012's agent variants repeatedly hit the global 10-tool-call ceiling without answering — one clear cause (a wrong-tool retry loop on `search_work_items`, unguarded by the per-tool retry cap that only covers `search_company_knowledge`), one still-unexplained sub-pattern (stopping after 0–1 tool calls with the same message). Documented as-is per the user's explicit choice, not fixed this phase. `EVALUATION_REPORT.md`'s `Scenario Results`, `Product and Operational Evidence`, `Failure Analysis`, and `Residual Risks` are now filled in (`Release Recommendation` deliberately left for Phase 10). New `pages/evaluation.py` (Streamlit multipage dashboard) verified live in a real browser, zero exceptions. 3 real feedback entries seeded via live UI clicks (2 useful, 1 not-useful+reason), per the user's explicit choice over synthetic data. |
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

Committed on branch `phase3-4-baseline-live-github` at `3773b76` (Phases 3–4;
branched off `main` before committing, `main` untouched):

```
M data/database/company.db
M deliverables/EVALUATION_REPORT.md
M deliverables/ACCESS_MATRIX.md
M deliverables/DECISIONS.md
M pyproject.toml, uv.lock
M src/company_assistant/service.py
M src/company_assistant/connectors/registry.py
M src/company_assistant/connectors/__init__.py
A src/company_assistant/connectors/github_live.py
```

Not yet committed (this session, Phase 5, still on `phase3-4-baseline-live-github`):

```
A src/company_assistant/indexing.py       (chunking, manifest, sync_index/rebuild_index)
M src/company_assistant/retrieval.py      (added semantic_search, hybrid_search; lexical_search untouched)
M src/company_assistant/service.py        (answer() takes retrieval_mode; answer_with_baseline now a thin wrapper)
M deliverables/EVALUATION_REPORT.md       (Retrieval Comparison table filled in + Phase 5 findings section)
M deliverables/DECISIONS.md               (5 new decisions: chunking, sync-as-separate-step, RRF, lexical-as-default, GH top-k gap not patched)
M deliverables/ACCESS_MATRIX.md           (Enforcement Notes: citation recheck partially done, semantic/live freshness clocks are independent)
```

`data/index/` (the Chroma persistent store + `manifest.json`) is git-ignored, as intended — not part of this list.

Committed on branch `phase3-4-baseline-live-github` at `bab5035` ("Complete
Phase 5 (managed RAG) and Phase 6 (tools + agent)"):

```
A src/company_assistant/tools/__init__.py         (build_tools(employee, data_root, retrieval_mode) — the agent's entry point)
A src/company_assistant/tools/schemas.py          (typed tool inputs/outputs)
A src/company_assistant/tools/knowledge.py        (search_company_knowledge [now retrieval_mode-aware for Phase 8], search_work_items, open_source)
A src/company_assistant/tools/structured_data.py  (get_support_case, list_project_status wrappers)
A src/company_assistant/tools/actions.py          (propose_action tool + approve/reject/edit/execute, no tool wrapper)
A src/company_assistant/agent/__init__.py         (create_agent + ChatGroq wiring, system prompt, citation verification, Answer mapping)
M src/company_assistant/retrieval.py              (renamed private _tokens -> public tokenize(), reused by search_work_items)
M src/company_assistant/models.py                 (ActionProposal.payload widened to allow list[str] values — found via live testing)
M deliverables/EVALUATION_REPORT.md               (Phase 6 tool-layer AND agent findings sections, live Groq-call evidence)
M deliverables/DECISIONS.md                       (7 new decisions total: closure-based identity injection, search_work_items scoping, citation verification, ToolStrategy, payload widening, + the two live-testing bug fixes)
M deliverables/ACCESS_MATRIX.md                   (citation recheck and pre-execution identity recheck both marked done; confirmed live through the agent, not just direct tool calls)
```

Not yet committed (this session, Phase 7 — full product experience, still on `phase3-4-baseline-live-github`):

```
M app.py                                          (agent-backed chat, identity-switch history reset, system-status sidebar + resync button, pending-actions approval panel, status banners, conditional citation links, feedback control)
M src/company_assistant/api.py                    (agent-backed /ask, new /status, /feedback, /actions/pending, /actions/{id}/approve|reject|edit)
M src/company_assistant/agent/__init__.py         (ModelRetryMiddleware added, then narrowed to exclude ModelRateLimitError from retry)
M src/company_assistant/models.py                 (Answer.answer_id; new Feedback/FeedbackRating/FeedbackReason)
A src/company_assistant/feedback.py               (record_feedback/list_feedback — JSONL under data/feedback/, git-ignored)
M deliverables/EVALUATION_REPORT.md               (new Phase 7 section: live browser + TestClient evidence, both live-testing findings)
M deliverables/DECISIONS.md                       (5 new decisions: ModelRetryMiddleware + retry_on narrowing, approve-triggers-execute, feedback-as-JSONL, identity-switch history clearing)
```

Not yet committed (this session, Phase 8 — comparative evaluation, still on
`phase3-4-baseline-live-github`):

```
A src/company_assistant/evaluation/run.py         (harness: runs all 12 cases through 3 variants, writes data/generated/evaluation_results.json)
A pages/evaluation.py                             (Streamlit multipage dashboard: Pass/Partial/Fail/N/A by category, coverage/latency by variant, feedback counts, unresolved-failures table)
M deliverables/EVALUATION_REPORT.md               (Thresholds table filled in; new Phase 8 section; Scenario Results, Product and Operational Evidence, Failure Analysis, and Residual Risks all filled in — Release Recommendation deliberately left for Phase 10; Product Evaluated section corrected — model/version/date fields were stale since Phase 6/7)
M deliverables/DECISIONS.md                       (5 new decisions: 3-variant comparison scope, live-UI feedback seeding, document-not-fix the tool-call-limit finding, hand-corrected verdicts written back into the results JSON)
```

`data/generated/evaluation_results.json` and `data/feedback/feedback.jsonl`
are both git-ignored (generated/local state), not part of this list.

## Planned Post-Phase-8 Work: Packaging Experiment (Phases 9/10)

Discussed and agreed with the user ahead of time so it isn't lost; **do not start
until Phase 8's evaluation report is accepted.** Full rationale in
`deliverables/DECISIONS.md`.

Two deliverables, built together as one experiment:

1. **Local package:** the FastAPI app with NiceGUI mounted directly into it
   (`ui.run_with(app)`) — one process, one port — replacing the Streamlit
   interface used through Phase 8. Runnable via `uvicorn` on `127.0.0.1:<port>`.
2. **Containerized k8s package:** the same single-process app, containerized,
   deployed via `kubectl` to the user's own k3s cluster. k3s already ships
   Traefik as its ingress controller, so only Traefik's `IngressRoute` CRD
   needs to be applied for routing — no separate ingress controller install.

Agreed constraints:
- Plain HTTP only — no TLS/cert-manager for this deliverable. The app is
  reached at `northstar.sv5.de`; Traefik's `IngressRoute` handles the
  hostname routing, no HTTPS termination needed.
- Port 80 = Traefik's web entrypoint; port 8080 = Traefik's own dashboard
  (not the app) — the app itself listens on its own container port behind
  the `IngressRoute`, never bound to 80/8080 directly.
- NiceGUI over Streamlit specifically because it collapses the two-port
  Streamlit+FastAPI topology into one Deployment/Service/IngressRoute.

When this starts: rewrite `app.py`'s Streamlit UI as NiceGUI pages mounted
into `api.py`'s existing FastAPI `app`; use `httpx` inside NiceGUI handlers to
call the app's own `/ask` endpoint over HTTP (clean client/API boundary, not a
direct Python import); write a Dockerfile for the unified process; write k8s
manifests (Deployment, Service) plus a Traefik `IngressRoute` for
`northstar.sv5.de`; write a short `kubectl apply -f` how-to.

## Open Items / Not Yet Decided

- Whether the numeric success-measure placeholders in `PRODUCT_BRIEF.md` (8s latency, 3/3 + 10/12 pass-rate targets) should be revisited once Phase 3's real baseline latency exists. (No timer was instrumented in Phase 3 — calls were sub-second in-process with no model/network round trip, so this is still open.)
- ~~Citation re-checking at resolution time (the `open_source` tool)~~ — done, see Phase 6 row above.
- Whether the abstention gap found in Phase 3 (baseline returns irrelevant-but-permitted evidence instead of abstaining, EVAL-005/EVAL-007) should be patched with a minimal relevance-score cutoff in the lexical baseline itself, or left as-is and solved only by the semantic/agent layers in Phase 5–6 (current lean: leave it — `AGENTS.md` says "preserve the lexical baseline" and the whole point of Phase 3 is to document this as the comparison point, not fix it prematurely).
- **New from Phase 4:** priority question 2 ("which Atlas GitHub issues are open, live + local") isn't content-complete — the live repo (`AlexDeWilde/ai-agent-project-test-repo`) has no Atlas-themed issues, so the live path proves connector mechanics, not the actual Atlas answer. Decide whether to (a) ask the repo owner to add 1–2 Atlas/billing-labeled issues, (b) accept and explicitly narrow priority question 2's wording, or (c) leave as a named residual risk for Phase 8. See `DECISIONS.md`.
- ~~EVAL-012/priority question 2 fails expected-source recall in every retrieval mode (`GH-149` tie-broken out of the top-4 window)~~ — resolved by Phase 6's `search_work_items` tool, which ranks GitHub issues only against each other. Verified: `GH-142` and `GH-149` both present for the exact failing query. The content-completeness item just above (Phase 4's residual gap — the live repo has no Atlas-themed issues) is separate and still open.
- ~~No scheduled/automatic index sync exists yet~~ — Phase 7 added a manual "Resync index" sidebar button (calls `sync_index()` directly); no automatic/scheduled sync, which is fine for a single-user demo.
- **New from Phase 6:** the action-proposal store and audit log are in-memory/per-process — restarting the app loses all proposal history. Fine for this prototype (recorded in `ACCESS_MATRIX.md`); flag if a persisted store becomes a Phase 8 evaluation requirement.
- ~~`openai/gpt-oss-20b` on Groq intermittently fails to produce a valid structured tool call~~ — Phase 7 added `ModelRetryMiddleware` (see `DECISIONS.md`); reduces but does not eliminate the failure rate, and every observed failure (with or without the middleware) degrades safely to `status="error"`, never a crash or fabrication.
- ~~**Groq's daily token quota (200k TPD)**~~ — hit again at the start of Phase 8 (a "new" key in the same org didn't reset it; confirmed by comparing organization IDs in the error payload). A genuinely different-org key resolved it for this session. Residual risk, not fully closed: rotating keys should never be assumed to reset the quota without confirming the org differs, and any future full comparative run should still budget for pacing across more than one day or a paid tier.
- ~~**New from Phase 7: citation-link rendering not re-verified after the `retry_on` fix**~~ — still open; not re-checked in Phase 8 either (no citation-bearing answer with an `http` source_path happened to come up in this phase's live checks). Low risk, unchanged assessment.
- **New from Phase 7, still open:** FastAPI's `/ask` accepts `conversation_history` but nothing currently exercises multi-turn conversation through it — only Streamlit drives real conversations today.
- **New from Phase 8:** tool-routing failures on ambiguous phrasing (EVAL-011/012) — a real, reproducible weakness where the agent hits its global tool-call ceiling instead of answering. One cause (a wrong-tool retry loop, unguarded by the per-tool retry cap) is understood; a second sub-pattern (stopping after 0–1 tool calls with the same message) is not. Documented, not fixed, per the user's explicit choice — see `EVALUATION_REPORT.md`'s Phase 8 section and Failure Analysis.
- **New from Phase 8:** the evaluation harness's automatic verdict function has no dedicated branch for `indirect_prompt_injection` (EVAL-006) — it produced a false `Fail` that trace review corrected to `Pass`. Worth a real fix in `run.py` if the harness is reused later.
- **New from Phase 8:** the Reject action button exists in `app.py` but has only ever been verified via direct function call (Phase 6), never clicked live in the UI.

## Next Immediate Step

Phase 8 (comparative evaluation) is fully captured in
`deliverables/EVALUATION_REPORT.md` — Thresholds, a new Phase 8 section, and
`Scenario Results`/`Product and Operational Evidence`/`Failure
Analysis`/`Residual Risks` are all filled in (`Release Recommendation`
deliberately left for Phase 10, per `05-evaluation-and-release.md`) — plus 5
new `DECISIONS.md` entries. Per `AGENTS.md`'s collaboration workflow, this
needs human review/acceptance before Phase 9 starts.

Once accepted: **Phase 9 — Docker packaging** per the course's numbered
files. Note the user's separate, larger packaging plan (NiceGUI + k3s/Traefik,
`DECISIONS.md`'s "Defer a NiceGUI + k3s/Traefik packaging experiment"
entry) — confirm with the user whether Phase 9 proceeds as the course's
plain single-container ask first, or whether to go straight to the larger
experiment.

**Housekeeping for whoever resumes this session:** the branch is
`phase3-4-baseline-live-github` (yes, named after Phases 3–4, now also carrying
5 and 6 — consider renaming or just merging soon to avoid confusion). Run
`uv run python -m company_assistant.database` if `data/database/company.db` looks
stale, and `python -c "from pathlib import Path; from company_assistant.indexing import sync_index; print(sync_index(Path('data/raw')))"`
to rebuild the semantic index if `data/index/` was cleaned or is missing (it's
git-ignored, so a fresh checkout starts with none).
