# Decision Log

Record meaningful product and architecture decisions, not every small edit.

## Decision Template

### Decision: Short descriptive title

- **Phase:**
- **Context:**
- **Options considered:**
- **Coding-agent contribution:**
- **Evidence reviewed:**
- **Decision and owner:**
- **Consequences or follow-up:**
- **Status:** Accepted, revised, or rejected

### Decision: Split the SQLite access policy by table instead of by database

- **Phase:** 2 — Access matrix
- **Context:** The template's matrix treats "Financial records" as one row, but the database has three tables of different sensitivity: `customers`/`support_cases` (revenue, account value, case ownership) and `projects` (release status/target date). Leo's Engineering profile needs the Atlas project status (`projects` table) for its priority questions but has no business need for customer or revenue data.
- **Options considered:** (1) Deny Engineering all database access, forcing release-status questions through GitHub/Slack/docs only; (2) Allow Engineering the whole database; (3) split the matrix row so Engineering gets `projects` only, denied on `customers`/`support_cases`.
- **Coding-agent contribution:** Inspected `database.py` and confirmed no role or confidentiality metadata exists at the schema or `get_support_case()` level today — the split is a policy decision that has no enforcement yet.
- **Evidence reviewed:** `src/company_assistant/database.py` (schema and the one existing lookup function); `deliverables/PRODUCT_BRIEF.md`'s in-scope/out-of-scope boundaries.
- **Decision and owner:** Option 3, split by table — confirmed by the AI PM.
- **Consequences or follow-up:** Implemented immediately in `database.py` (ahead of Phase 6) rather than deferred, since the check is small, contained to the data layer, and removes a live gap from the risk register before any tool can call it. `get_support_case()` now takes an `employee` parameter and denies non-`customer_success`/`finance` roles by returning `None` (same shape as "not found," so a denied role can't infer existence); a new `list_project_status()` follows the same pattern for `customer_success`/`engineering`/`finance`, returning `[]` when denied. Verified directly with normal, denied, and not-found inputs (no model or network call). Phase 6 still needs to wrap both functions as typed LangChain tools that supply `employee` from the caller's verified identity, not from model input.
- **Status:** Accepted

### Decision: Live GitHub repository is additive, not a swap for the local Atlas export

- **Phase:** 4 — Live GitHub connector
- **Context:** `PRODUCT_BRIEF.md`'s priority question 2 requires "Which Atlas GitHub issues are still open" to work against both the live repository and the local fallback. The repository picked for the live-connector demonstration (`AlexDeWilde/ai-agent-project-test-repo`, chosen by the user — public, real issues, no token needed) contains real issues about building this connector (pagination, rate limiting, README gaps), not Atlas billing-migration content. `ACCESS_MATRIX.md`'s Phase 2 draft had assumed the local `issues.json` export (`GH-142`/`GH-149`/`GH-131`) would serve as "the fallback for the live connector," implying a swap: local export only appears when live access fails.
- **Options considered:** (1) Swap design as originally drafted — live issues replace local issues in the corpus whenever the live repo is healthy, local issues only reappear on live failure; (2) merge design — local Atlas export always loads, live repository issues are added on top when reachable, and "fallback" means "zero live-sourced issues this turn," never a silent substitution; (3) ask the repository owner (a classmate, not the user) to add Atlas-themed issues so a swap would stay content-consistent.
- **Coding-agent contribution:** Implemented option 1 first, then caught the regression by re-running the Phase 3 baseline queries against it: EVAL-002/003/009/010/012 (which all require `GH-142`/`GH-149`) would have silently lost their evidence the moment `GITHUB_REPOSITORY` was configured and reachable — the common case, not an edge case. Flagged this to the user before deciding, since it's a product-scope tradeoff, not a coding detail; the user's earlier answer ("compare those existing, and only add what's needed") was about the repo-choice question, not this specific swap-vs-merge fork, so this one call was made directly rather than re-blocking on a second question, on the reasoning that option 2 is strictly non-regressive and reversible.
- **Evidence reviewed:** Live re-fetch of the actual repository's 8 issues (6 open + 2 closed, confirmed via `state=all`); `deliverables/EVALUATION_REPORT.md`'s Phase 3 findings (which depend on `GH-142`/`GH-149` being retrievable for Leo); `PRODUCT_BRIEF.md` priority question 2's exact wording.
- **Decision and owner:** Option 2 (merge, not swap) — decided by the coding agent as a non-breaking implementation correction, consistent with `AGENTS.md`'s "preserve the lexical baseline" and no-regressions spirit. Did **not** pursue option 3 — creating issues on a repository the user doesn't own is a shared-state, visible-to-others action requiring the repo owner's or the user's explicit action, not something to do unilaterally.
- **Consequences or follow-up:** `connectors/github_live.py`'s `load_live_github_issues()` never touches the local export; `connectors/registry.py` always loads local GitHub issues and appends live ones when available. Live issue IDs are prefixed with the repository (`GH-{owner}-{repo}-{number}`) so they can never collide with the local fixture's short IDs. Residual limitation: priority question 2's promise to answer the *same* Atlas question against a live source isn't literally demonstrated with this repository's content — only the connector mechanics (fetch, paginate, normalize, fail safely) are. If full content parity is wanted later, someone with write access to the live repo would need to add Atlas-labeled issues; otherwise this gap should be named explicitly in the Phase 8 evaluation rather than glossed over.
- **Status:** Accepted

### Decision: Whole-document chunking, no text splitter

- **Phase:** 5 — Managed RAG pipeline
- **Context:** `04-connected-rag-and-agent.md` requires comparing at least two chunking or retrieval choices and keeping the simplest one the evidence supports.
- **Options considered:** (1) one Chroma chunk per `CompanyDocument` (no splitting); (2) a fixed-size character splitter (300 chars / 50 overlap, chosen since fixture content is short).
- **Coding-agent contribution:** Measured fixture content length directly: 180–424 characters per document (median 227). Built both indexes in an ephemeral, non-persisted Chroma collection and ran 4 representative questions against each. The splitter fragmented only 4 of 23 documents into 2 chunks; retrieval results (expected-source coverage) were identical between the two on every test question.
- **Evidence reviewed:** `phase5_chunking_compare.py` output (content-length distribution, chunk counts, per-question hit/miss for both indexes).
- **Decision and owner:** Option 1 (whole document) — decided by the coding agent; no evidence favored splitting, so the simpler option was kept per `AGENTS.md`'s "no half-finished implementations" and the phase's own "retain the simplest one" instruction.
- **Consequences or follow-up:** `indexing._to_chroma_document()` uses the full `CompanyDocument.content` as one chunk with `id=source_id`, so a chunk ID and a source ID are always identical for now. If a future source family contributes much longer documents, this decision should be re-tested rather than assumed to still hold.
- **Status:** Accepted

### Decision: Index sync is an explicit, separate step from querying

- **Phase:** 5 — Managed RAG pipeline
- **Context:** `04-connected-rag-and-agent.md` requires a real index lifecycle (upserts, deletions, a visible last-indexed status, and a full-rebuild fallback) — not just initial ingestion. The live GitHub connector (Phase 4) already re-fetches fresh on every question; the question was whether the semantic index should do the same (re-embed everything per query) or maintain its own persisted, separately-synced state.
- **Options considered:** (1) rebuild/re-embed the full corpus on every question (simplest to code, but re-embeds unchanged content every time and can't demonstrate "index lifecycle" as anything but a no-op); (2) a persisted Chroma collection plus a content-hash manifest, synced via an explicit `sync_index()` call that upserts changed/new sources and deletes ones no longer present, independent of when questions are asked.
- **Coding-agent contribution:** Implemented option 2 (`indexing.py`: `sync_index()`, `rebuild_index()`, `last_indexed_status()`) and proved the full lifecycle in an isolated sandbox (temp data root + temp Chroma/manifest paths, so the real index was never touched): add a source → sync → retrievable; delete it → sync → no longer retrievable (EVAL-011); a corrupted manifest recovered cleanly via `rebuild_index()`. Flagged before building: this was raised to the user in the Phase 5 overview as the one design point most worth a nod (persisted+synced vs. simpler-but-fake), and the user approved proceeding ("go ahead") without objection.
- **Evidence reviewed:** `phase5_eval011_lifecycle.py` output; `04-connected-rag-and-agent.md`'s "Manage the Index Lifecycle" and `EVAL-011`'s exact scenario in `data/evaluation/cases.json`.
- **Decision and owner:** Option 2, confirmed by the user's go-ahead on the Phase 5 overview.
- **Consequences or follow-up:** Semantic retrieval's freshness now depends on when `sync_index()` last ran, independently of the live GitHub connector's per-request freshness — recorded in `ACCESS_MATRIX.md`'s Enforcement Notes as a named limitation. No scheduled/automatic sync exists yet; Phase 7 should decide whether the UI needs a manual "resync" control or whether syncing on app startup is sufficient for the demo.
- **Status:** Accepted

### Decision: Hybrid retrieval uses Reciprocal Rank Fusion (RRF), not a weighted score sum

- **Phase:** 5 — Managed RAG pipeline
- **Context:** Lexical's score is a 0–1 token-overlap ratio; semantic's is a Chroma L2 distance transformed to `1/(1+distance)`. These live on different scales for different reasons, and combining them meaningfully needs "a documented scoring strategy" per the phase's requirements.
- **Options considered:** (1) weighted sum of normalized scores (`alpha * semantic + (1-alpha) * lexical`) — requires tuning `alpha` with no principled way to pick it from two cases; (2) Reciprocal Rank Fusion — `score(doc) = Σ 1/(k + rank)` across each ranking the document appears in, k=60 — needs no tuning beyond the standard constant and only uses ranks, so scale mismatches between signals are irrelevant by construction.
- **Coding-agent contribution:** Implemented RRF (`retrieval.hybrid_search()`) and traced its behavior on real cases rather than only asserting it works: it recovers `GH-142` for EVAL-002 (6th semantically, 3rd lexically, pulled into the combined top 4), but also demonstrates RRF's known tradeoff on EVAL-003 — `EMAIL-ACME-302` (strong on one signal, 4th lexically) loses narrowly to `SLACK-ATLAS-101` (moderate on both signals) by combined score `0.03101` vs. `0.03126`.
- **Evidence reviewed:** `phase5_mode_comparison.py` and direct rank dumps for both cases; see `EVALUATION_REPORT.md`'s Phase 5 findings for the full worked numbers.
- **Decision and owner:** RRF — decided by the coding agent as the standard, tuning-free choice; the EVAL-003 near-miss it produces is documented as a real property of RRF, not treated as a bug to chase away.
- **Consequences or follow-up:** `RRF_K = 60` and `HYBRID_CANDIDATE_LIMIT = 10` (candidates pulled from each signal before fusing) are set as module constants in `retrieval.py`; revisit `HYBRID_CANDIDATE_LIMIT` if a future case shows a relevant document ranked below 10 in both signals.
- **Status:** Accepted

### Decision: Lexical stays the selected default retrieval mode after comparison

- **Phase:** 5 — Managed RAG pipeline
- **Context:** `04-connected-rag-and-agent.md` requires selecting the default retrieval mode from comparison evidence on the product's priority questions, not from architectural preference.
- **Options considered:** lexical, semantic, hybrid — compared head-to-head on 6 cases with non-empty `expected_source_ids` (EVAL-001/002/003/006/012 plus the "which GitHub issues are open" priority question) at the shared `limit=4`.
- **Coding-agent contribution:** Ran all three modes against identical inputs and measured expected-source recall, forbidden-source exposure, and warm latency. Lexical won on recall (4/6) and latency (0.15 ms median) on this specific, small, ID-dense fixture corpus — the opposite of the "semantic is obviously better" assumption one might default to without measuring.
- **Evidence reviewed:** `phase5_mode_comparison.py` full output; see `EVALUATION_REPORT.md`'s Retrieval Comparison table for the per-mode numbers.
- **Decision and owner:** Lexical remains the default — decided by the coding agent directly from the comparison evidence, consistent with the phase's own instruction to select the default this way rather than by preference.
- **Consequences or follow-up:** `service.answer()` defaults `retrieval_mode="lexical"`; semantic and hybrid remain fully available behind the same function signature for Phase 6's agent to select per-question, or for re-evaluation once real (more paraphrase-heavy) usage exists. This decision should be revisited if the fixture set grows or real usage patterns diverge from it — it is a measurement result tied to this specific corpus, not a general claim that lexical beats semantic.
- **Status:** Accepted

### Decision: Do not patch the GitHub-issue top-*k* retrieval gap in Phase 5

- **Phase:** 5 — Managed RAG pipeline (gap discovered during retrieval-mode comparison)
- **Context:** EVAL-012 and the "which GitHub issues are still open" priority question fail expected-source recall in **all three** retrieval modes at `limit=4`. Root cause, diagnosed directly: `GH-149` ties in lexical score with 5 other documents for this query, and the recency tie-break favors the live repository's issues (all dated today) over the local Atlas fixture's older dates, pushing `GH-149` to 6th place — outside the returned window.
- **Options considered:** (1) raise the shared default `limit` (e.g. 4 → 6) — cheap, but only papers over the symptom and degrades again as the live repository accumulates more issues over time; (2) change the tie-break rule to not let recency alone favor one source family over another — narrower fix, still doesn't address free-text ranking mixing structured "list issues" queries with unstructured knowledge search; (3) leave `limit` alone and treat this as the concrete justification for Phase 6's dedicated `search_work_items` tool, which can filter/scope GitHub issues directly instead of ranking them by token overlap against the entire mixed corpus.
- **Coding-agent contribution:** Diagnosed the exact tie and rank (printed the full score/date table for the failing query) rather than only observing the miss; confirmed it reproduces identically in lexical, semantic, and hybrid mode, so it is a corpus-shape problem, not a mode-specific bug.
- **Evidence reviewed:** Direct lexical score/rank dump for "Which Atlas GitHub issues are still open?"; `02-system-design.md`'s tools table, which already specifies `search_work_items` as a narrow tool separate from generic `search_company_knowledge`.
- **Decision and owner:** Option 3 — decided by the coding agent; flagged as an open item rather than silently fixed, since raising `limit` is not a durable fix and the user owns whether this acceptance criterion needs a faster interim patch.
- **Consequences or follow-up:** Recorded as an open item in `PROGRESS_LOG.md`. Phase 6 must ensure `search_work_items` doesn't inherit this problem — it should query/filter GitHub issues on their own terms (e.g. by project label or "Atlas" tag), not rank them against Slack/email/documents in one shared top-*k* list.
- **Status:** Accepted

### Decision: Defer a NiceGUI + k3s/Traefik packaging experiment to after Phase 8

- **Phase:** Discussed during Phase 6, deferred to Phases 9/10.
- **Context:** The user's real deployment target goes beyond the course's Phase 9 ask (a single container). They want two final packages: (1) a plain local FastAPI app, and (2) the same app containerized and deployed to their own k3s cluster behind Traefik at `northstar.sv5.de`. They asked about replacing Streamlit with NiceGUI, since NiceGUI can mount directly into the same FastAPI app (`ui.run_with(app)`), collapsing today's two-port Streamlit+FastAPI topology into one process/port — which meaningfully simplifies the k8s/Traefik side (one Deployment/Service/IngressRoute instead of routing two processes).
- **Options considered:** (1) do the NiceGUI swap and k8s/Traefik packaging now, alongside Phase 6; (2) keep Streamlit as-is through Phase 8's evaluation (as `AGENTS.md` instructs) and treat the NiceGUI rewrite + k8s/Traefik deployment as one deferred experiment for Phases 9/10, run only after the evaluation report is accepted.
- **Coding-agent contribution:** Pointed out the direct conflict with `AGENTS.md` ("Keep Streamlit and Groq as the core project path. Alternative interfaces... belong to the optional extensions after the required evaluation is complete") and `05-evaluation-and-release.md`'s extension menu, which treats interface replacement (its examples are Chainlit/Next.js; NiceGUI is the user's variant of the same slot) as strictly post-evaluation, specifically so a mid-stream interface change doesn't confound the Phase 8 comparison. Gave a concrete effort estimate for the NiceGUI swap (small-to-medium — the current `app.py` is ~75 lines with no complex state, and every Streamlit widget it uses has a direct NiceGUI equivalent) so the user could weigh timing against effort with real information, not a guess.
- **Evidence reviewed:** `AGENTS.md`'s product rules; `05-evaluation-and-release.md`'s Phase 9 requirements and "Build a More Advanced Interface" extension section; current `app.py` for the effort estimate.
- **Decision and owner:** Option 2 (defer to after Phase 8) — chosen by the user, given the real-coursework sequencing constraint.
- **Consequences or follow-up:** Full build plan (what changes, what's skipped — no TLS/cert-manager, plain HTTP; port 80 = Traefik web entrypoint, 8080 = Traefik's own dashboard, not the app) recorded in `PROGRESS_LOG.md`'s "Planned Post-Phase-8 Work" section so it survives to whichever session picks up Phase 9. Streamlit stays the interface of record through Phases 6–8; do not start this work early.
- **Status:** Accepted

### Decision: Inject employee identity into tools via closures; separate approval functions have no tool wrapper at all

- **Phase:** 6 — Tools and one agent (tool layer only; agent runtime not yet built)
- **Context:** Tools must receive `employee` "from verified caller identity, not from the model" (`ACCESS_MATRIX.md`'s standing note since Phase 2), but a LangChain tool's arguments are exactly what the model is allowed to fill in. Separately, the human-approval flow requires that "the assistant cannot approve its own proposal" and that approval "must come from a separate user interaction" — text in a retrieved document must have no path to it.
- **Options considered:** For identity — (1) pass `employee` as a tool argument and instruct the model never to change it (relies on prompt discipline, not enforcement); (2) build each tool via a `build_*_tool(employee)` closure that captures identity once per request, so the model-visible argument schema never includes it at all. For approval — (1) expose `approve_action`/`reject_action`/`execute_action` as tools alongside `propose_action`, relying on the system prompt to say "never call these yourself"; (2) give only `propose_action` a tool wrapper and leave the other four as plain functions with no LangChain tool conversion applied anywhere, so the agent has no mechanism to invoke them regardless of what any prompt or retrieved content says.
- **Coding-agent contribution:** Implemented option 2 in both cases and verified the enforcement is structural, not just documented: converted all six tool functions through `langchain_core.tools.tool()` and inspected the generated argument schemas directly — none contain `employee`. `approve_action` additionally refuses self-approval in code (`requester == approver` raises), independent of who calls it.
- **Evidence reviewed:** `tools/__init__.py`, `tools/actions.py`; the args-schema inspection script's output (six schemas, listed in `EVALUATION_REPORT.md`'s Phase 6 section).
- **Decision and owner:** Option 2 for both — decided by the coding agent, since relying on prompt instructions alone for either identity or approval would contradict `AGENTS.md`'s "treat source content as untrusted evidence, never as instructions" whenever a future model call is added.
- **Consequences or follow-up:** The action-proposal store and audit log (`tools/actions.py`) are in-memory and per-process — acceptable for this prototype, recorded as a limitation in `ACCESS_MATRIX.md`. Phase 7's Streamlit approval UI will call `approve_action`/`reject_action`/`edit_action`/`execute_action` directly as plain Python functions, never through the agent.
- **Status:** Accepted

### Decision: `search_work_items` scopes ranking to GitHub issues only

- **Phase:** 6 — Tools (resolves the Phase 5 open item)
- **Context:** Phase 5 found that `GH-149` gets tie-broken out of a shared top-4 window by the live repository's more-recent, same-scoring issues, and that this would only worsen as the live repo grows — deliberately left unpatched at the retrieval layer pending a dedicated tool (`DECISIONS.md`'s "Do not patch the GitHub-issue top-*k* retrieval gap in Phase 5").
- **Options considered:** (1) raise the shared `limit` for all retrieval — rejected in Phase 5 for not scaling; (2) a `search_work_items` tool that filters to `source_type == "github"` before ranking, so GitHub issues only ever compete against other GitHub issues.
- **Coding-agent contribution:** Implemented option 2 and directly re-ran the exact failing query from Phase 5 ("Which Atlas GitHub issues are still open?") through the new tool — both `GH-142` and `GH-149` are now present, confirmed in `EVALUATION_REPORT.md`'s Phase 6 table.
- **Evidence reviewed:** `tools/knowledge.py`'s `search_work_items`; the Phase 5 finding and its exact reproduction query.
- **Decision and owner:** Option 2 — matches the plan already recorded in `PROGRESS_LOG.md`'s Phase 5 open items.
- **Consequences or follow-up:** None outstanding for this specific gap. `search_company_knowledge` still shares one window across Slack/email/documents, which is fine since none of those source families are growing the way the live GitHub connector is.
- **Status:** Accepted

### Decision: Never trust the model's self-reported citations — verify against actual tool results

- **Phase:** 6 — Agent runtime
- **Context:** `create_agent`'s structured output asks the model to self-report `cited_source_ids` in its final answer. `PRODUCT_BRIEF.md`'s acceptance criteria require "every factual claim... resolves to a real, currently-permitted source ID" — a self-reported list is exactly the kind of claim that must not be taken on faith, since a model can hallucinate a plausible-looking ID it never actually retrieved.
- **Options considered:** (1) trust `cited_source_ids` as returned; (2) walk every `ToolMessage` produced during the run, collect every `source_id` a tool actually returned this turn, and only build a `Citation` for a model-claimed ID that appears in that set — silently dropping (and logging to trace) anything else.
- **Coding-agent contribution:** Implemented option 2 (`agent._retrieved_evidence()`/`_walk_for_source_ids()`) and changed every tool in `tools/` to return `.model_dump(mode="json")` instead of a raw Pydantic object specifically so `ToolMessage.content` is valid, parseable JSON rather than a Python `repr()` string — verified empirically that a Pydantic-object tool return serializes as `"x=42 y='hello'"` (unparseable) while a dict return serializes as proper JSON.
- **Evidence reviewed:** Live test comparing both serialization forms; all 8 EVAL-case runs in `EVALUATION_REPORT.md`'s Phase 6 agent section, none of which triggered a dropped-citation trace line, i.e. the model's self-reported citations matched its actual tool calls in every observed run so far.
- **Decision and owner:** Option 2 — decided by the coding agent as the only version of this design that actually satisfies the "resolves to a real source" acceptance criterion at the model layer, not just at retrieval.
- **Consequences or follow-up:** If a future test does surface a dropped citation, that's exactly the mechanism working as intended, not a bug — the trace line makes it visible for Phase 8's evaluation rather than silently passing through.
- **Status:** Accepted

### Decision: Force `ToolStrategy` for structured output; Groq rejects native JSON mode combined with tools

- **Phase:** 6 — Agent runtime
- **Context:** `create_agent(response_format=AgentAnswer)` (a bare Pydantic class) let LangChain pick a default strategy, which chose Groq's native JSON mode (`ProviderStrategy`). Groq's API rejects that outright whenever tools are also bound to the same call: `"json mode cannot be combined with tool/function calling"`.
- **Options considered:** (1) drop tools during the final structured-output turn (adds complexity, and the model may need one more tool call after seeing intermediate results); (2) explicitly wrap the schema in `langchain.agents.structured_output.ToolStrategy(AgentAnswer)`, which asks the model to call a synthetic `AgentAnswer` tool instead of switching provider JSON modes.
- **Coding-agent contribution:** Reproduced the exact 400 error, found `ToolStrategy` in `langchain.agents.structured_output`, and confirmed it resolves the conflict while keeping all six real tools available on every turn.
- **Evidence reviewed:** The Groq `BadRequestError` traceback; LangChain's `create_agent` signature and structured-output strategy classes.
- **Decision and owner:** `ToolStrategy(AgentAnswer)` — decided by the coding agent; this is a provider-specific constraint, not a product choice, so no user input was needed.
- **Consequences or follow-up:** This is very likely the root cause of the "functions.AgentAnswer" naming quirk and occasional malformed structured-output calls documented in `EVALUATION_REPORT.md`'s provider-reliability finding — `openai/gpt-oss-20b` doesn't always name or format the synthetic tool call cleanly. Accepted as a known limitation; see that finding's `ModelRetryMiddleware` recommendation for Phase 7/8.
- **Status:** Accepted

### Decision: Widen `ActionProposal.payload` to allow `list[str]` values

- **Phase:** 6 — Agent runtime (found via live testing, not anticipated in Phase 1's starter model)
- **Context:** `EVAL-010` failed on the first live attempt: the model naturally tried to draft a GitHub issue with `"labels": ["finance", "validation", "atlas"]`, but `ActionProposal.payload`'s type (`dict[str, str | int | float | bool | None]`, unchanged since the starter) only allows scalar values, so Groq's own tool-argument schema validation rejected the call with a 400 before it reached any of our code.
- **Options considered:** (1) instruct the model never to use array-valued fields (fights a completely reasonable and common real-world action shape); (2) widen the payload type to include `list[str]`, covering labels/assignees without opening the door to arbitrary nested JSON.
- **Coding-agent contribution:** Reproduced the failure, diagnosed it precisely from Groq's schema-validation error message, and made the narrowest fix that unblocks the real, observed need.
- **Evidence reviewed:** The Groq 400 error's exact validation message (`` `/payload/labels`: expected string, but got array ``, etc.); retested `EVAL-010` twice afterward, both successful.
- **Decision and owner:** Widen to `dict[str, str | int | float | bool | None | list[str]]` in both `models.py` and `tools/actions.py` — decided by the coding agent as a minimal, well-motivated type correction, not scope creep, since AGENTS.md's "typed inputs and outputs" requirement is best served by a type that matches reality.
- **Consequences or follow-up:** None outstanding. Still excludes nested objects/dicts as payload values — no observed need for that yet.
- **Status:** Accepted

### Decision: Adopt `ModelRetryMiddleware`, but exclude rate-limit errors from retry

- **Phase:** 7 — Full product experience
- **Context:** Phase 6 flagged (but deferred) `openai/gpt-oss-20b`'s intermittent malformed structured-output failures, recommending `ModelRetryMiddleware` as a Phase 7/8 fix. The user approved adding it before wiring the UI up to the agent, so a colleague demoing Phase 7 hits it less often.
- **Options considered:** (1) don't add it, keep documenting the failure rate; (2) add it with library defaults (`max_retries=2`, default `retry_on`); (3) add it with a narrowed `retry_on` that excludes rate-limit errors specifically.
- **Coding-agent contribution:** Implemented option 2 first, then discovered live (mid-session, via a real Groq 429) that the default `retry_on` retries `ModelRateLimitError` — confirmed by reading `langchain_core.exceptions` (`ModelRateLimitError.is_retryable = True`, and `default_retry_on` returns that flag for any `ModelError` subclass). Reasoned that retrying a **daily** token-quota exhaustion within a few backed-off seconds can never succeed (the quota resets on a ~24h cycle) — every retry in that case is pure wasted latency and an extra request for a failure guaranteed to recur immediately. Switched to option 3 (`retry_on=lambda exc: not isinstance(exc, ModelRateLimitError)`) and verified the lambda directly (`False` for a rate-limit error, `True` for a timeout), plus confirmed no regression by re-running the same question immediately before and after the change (both correctly still failed safely while the quota was exhausted; a later call once headroom freed up returned a normal answer).
- **Evidence reviewed:** The live `RateLimitError` traceback (`"tokens per day (TPD): Limit 200000, Used 198961"`); `langchain_core.exceptions`' `ModelError`/`ModelRateLimitError` source; `langchain.agents.middleware.model_retry`'s `default_retry_on` source.
- **Decision and owner:** Option 3 — the user asked directly whether requests toward Groq could be reduced design-wise; this was the concrete, correct answer (not just "we tested a lot today," though that was also true), so the user approved applying it.
- **Consequences or follow-up:** The original malformed-tool-call failure mode (Phase 6) still gets up to 2 retries, unchanged. A quota-exhaustion 429 now fails on the first attempt instead of the third, saving ~7s of guaranteed-futile backoff per hit; it does not and cannot recover lost daily quota. Phase 8's full comparative evaluation (12 cases × 3 retrieval variants, live) should assume it may need to span more than one day against this tier, or budget for a paid tier.
- **Status:** Accepted

### Decision: Approve triggers execute immediately; one click, not two

- **Phase:** 7 — Full product experience
- **Context:** `tools/actions.py` keeps `approve_action` and `execute_action` as separate functions, each independently rechecking state. Phase 7 needed to decide whether Streamlit's "Approve" button should only call `approve_action` (leaving a separate "Execute" step for later) or call both in sequence.
- **Options considered:** (1) two explicit steps/buttons — "Approve" moves a proposal to `approved`, a later "Execute" button (appearing only for already-approved items) actually runs it; (2) one "Approve" button that calls `approve_action` then, on success, `execute_action` immediately.
- **Coding-agent contribution:** Read `04-connected-rag-and-agent.md`'s own state diagram, where the `Approve` edge points directly at `Controlled execution` with no intermediate manual step shown — option 2 matches that diagram literally. `execute_action` already independently rechecks the proposal is actually `approved` immediately before running (not relying on the UI's sequencing), so collapsing the two calls into one button click doesn't weaken the recheck-before-execution guarantee the spec asks for.
- **Evidence reviewed:** The mermaid diagram in `04-connected-rag-and-agent.md`; `tools/actions.py`'s `execute_action`, which re-verifies `status == "approved"` and sets `status = "failed"` otherwise.
- **Decision and owner:** Option 2 — decided by the coding agent as the more literal reading of the supplied spec; verified live (Approve by a non-requester employee moves a proposal straight to `executed` and off the pending list in one click).
- **Consequences or follow-up:** None outstanding. If a future phase wants a manual hold between approval and execution (e.g. a real external system in the loop), `approve_action`/`execute_action` are already separate functions — only the UI wiring would need to change.
- **Status:** Accepted

### Decision: Feedback persisted as JSONL under `data/feedback/`, not a new SQLite table

- **Phase:** 7 — Full product experience
- **Context:** `04-connected-rag-and-agent.md` asks Phase 7 to persist a minimal useful/not-useful record (answer/conversation id, rating, reason, retrieval mode, timestamp). `AGENTS.md` restricts committed local databases to the one reproducible teaching fixture (`data/database/company.db`), and `.gitignore` already had a (previously unused) `data/feedback/` entry.
- **Options considered:** (1) a new table in `company.db`; (2) a new, separate SQLite file; (3) append-only JSONL under `data/feedback/`.
- **Coding-agent contribution:** Noticed the pre-existing `data/feedback/` gitignore entry before writing any code — a strong signal of the intended shape — and picked JSONL specifically because feedback is simple, append-mostly, low-volume records with no relational structure worth a schema; matches `database.py`'s existing plain-function style (`record_feedback`/`list_feedback`) without adding a second database engine to the project.
- **Evidence reviewed:** `.gitignore`; `AGENTS.md`'s "never commit... local databases other than the reproducible teaching fixture" rule; `database.py` for the existing plain-function convention.
- **Decision and owner:** Option 3 — decided by the coding agent; low-risk, easily revisited if Phase 8 needs querying beyond what `list_feedback()` provides.
- **Consequences or follow-up:** `Feedback` (in `models.py`) deliberately excludes employee identity and conversation text, matching the spec's "persist only the minimum" instruction. `feedback.py`'s `list_feedback()` exists for Phase 8's evaluation report to read back, not used by the UI itself.
- **Status:** Accepted

### Decision: Clear conversation history on employee-identity switch

- **Phase:** 7 — Full product experience (self-identified gap in the Phase 0 starter, not requested)
- **Context:** The starter `app.py` never reset `st.session_state.messages` when the employee selector changed. Since `answer_with_agent`'s `conversation_history` is built from that session state and fed back into the model as prior turns, a lower-privileged identity selected mid-session would inherit the previous identity's full conversation — including any evidence text a higher-privileged role had seen — directly into the new identity's model context.
- **Options considered:** (1) leave it (matches the starter, but is a real cross-identity leak vector); (2) clear `messages` (and per-message feedback/edit widget state) whenever the selected `employee_id` changes.
- **Coding-agent contribution:** Identified this while wiring the identity selector for Phase 7, not asked for; framed it explicitly as a permission-boundary issue (this project's fictional role selector doubles as its only access-control mechanism, per `PRODUCT_BRIEF.md`'s risk statement) rather than a cosmetic UX gap, and fixed it in the same change rather than deferring.
- **Evidence reviewed:** `app.py`'s original `st.session_state.messages` handling (Phase 0 starter); verified live by switching identity mid-conversation and confirming zero chat messages remain (`[data-testid="stChatMessage"]` count 0).
- **Decision and owner:** Option 2 — decided by the coding agent; flagged to the user as a proactive fix in the Phase 7 report rather than silently bundled in.
- **Consequences or follow-up:** None outstanding. Pending action proposals are intentionally NOT cleared on identity switch (they're global, per-process state visible to any identity, by design — see the Phase 6 "in-memory, per-process" decision).
- **Status:** Accepted

### Decision: Compare exactly 3 required variants, not a 4th lexical+agent column

- **Phase:** 8 — Comparative evaluation
- **Context:** `05-evaluation-and-release.md` requires comparing at least 3 system variants live. The obvious 4th column — lexical retrieval + agent, the shipped default — was already exercised live for 8 of 12 cases in Phase 6, and the freshly-reset Groq quota was known to be tight (Phase 7's TPD finding).
- **Options considered:** (1) run all 4 combinations (lexical baseline, lexical+agent, semantic+agent, hybrid+agent) across all 12 cases; (2) run only the 3 spec-required variants across all 12 cases, and for lexical+agent specifically, only run the 4 cases Phase 6 hadn't already covered live (EVAL-001/004/008/011), citing Phase 6's existing evidence for the other 8.
- **Coding-agent contribution:** Proposed option 2 explicitly to conserve quota, with the exact row-count math (13 + 5 + 13 + 13 = 44 rows vs. a larger count for option 1) so the user could see the tradeoff plainly.
- **Evidence reviewed:** Phase 6's Agent Findings table (already covers lexical+agent for 8 cases); Phase 7's TPD-quota finding.
- **Decision and owner:** Option 2 — the user chose it directly via `AskUserQuestion` ("Just the 3 required variants").
- **Consequences or follow-up:** The Scenario Results table's lexical+agent row mixes Phase 6 citations (8 cases) with this phase's fresh data (4 cases) — flagged explicitly in that table's intro so the mixed provenance isn't hidden.
- **Status:** Accepted

### Decision: Seed feedback via real live UI clicks, not synthetic JSON

- **Phase:** 8 — Comparative evaluation
- **Context:** The evaluation dashboard (`pages/evaluation.py`) needed non-empty feedback data to be meaningfully inspectable, and `data/feedback/feedback.jsonl` was empty (the Phase 7 verification entries were deliberately cleared as test data).
- **Options considered:** (1) write a handful of `Feedback` records directly to the JSONL file; (2) start Streamlit and click the real Useful/Not-useful(+reason) buttons for a few of the evaluation questions, across different employee profiles.
- **Coding-agent contribution:** None beyond executing the choice — this was a straightforward manual-vs-live-generated-data tradeoff with no hidden complexity, so it was put to the user directly rather than assumed.
- **Evidence reviewed:** N/A — a preference question, not an evidence question.
- **Decision and owner:** Option 2 — the user chose it directly via `AskUserQuestion` ("Seed a few real entries via the live UI").
- **Consequences or follow-up:** 3 entries seeded (2 useful, 1 not-useful with reason `stale_evidence`), verified in `feedback.jsonl` and rendered correctly on the dashboard. Small additional live-call cost, already agreed.
- **Status:** Accepted

### Decision: Document the tool-call-limit/wrong-tool-selection finding as-is; do not fix it mid-evaluation

- **Phase:** 8 — Comparative evaluation
- **Context:** The harness's live run surfaced a real, reproducible weakness: on EVAL-011 ("the temporary Atlas **work item**") and EVAL-012, several agent variants exhausted the global 10-tool-call budget without answering — one clearly traced to a wrong-tool retry loop (`search_work_items` instead of `search_company_knowledge`, driven by the case's own wording; the per-tool retry guard only covers `search_company_knowledge`), the other pattern (stopping after 0–1 tool calls with the same generic message) not fully explained by the visible trace.
- **Options considered:** (1) document the finding exactly as diagnosed in `EVALUATION_REPORT.md`'s Failure Analysis/Residual Risks, and leave it unfixed this phase; (2) attempt a quick fix first (e.g. extend the per-tool retry guard to cover `search_work_items`, or reword the tool description to disambiguate "work item"), then re-run the affected cases before writing the report.
- **Coding-agent contribution:** Flagged this as a genuine judgment call rather than picking one — Phase 8's stated job is evidence-gathering, not engineering, and every prior phase's discovered issues were documented before being fixed in a later, deliberate step (not patched silently mid-evaluation) — but a live, reproducible product weakness is exactly the kind of thing worth checking with the user rather than assuming.
- **Evidence reviewed:** The full trace for every EVAL-011/EVAL-012 error row (tool calls made, or not, before the cutoff); `agent/__init__.py`'s `MAX_TOOL_CALLS`/`SEARCH_RETRY_LIMIT` constants and where the per-tool guard is scoped.
- **Decision and owner:** Option 1 — the user chose it directly via `AskUserQuestion` ("Document as-is").
- **Consequences or follow-up:** Recorded in `EVALUATION_REPORT.md`'s Phase 8 section, Failure Analysis, and Residual Risks, including the honest caveat that one of the two failure sub-patterns isn't fully understood yet. Left as an open item for a later phase, not silently patched.
- **Status:** Accepted

### Decision: Hand-corrected verdicts are written back into `evaluation_results.json`, not just into the report

- **Phase:** 8 — Comparative evaluation
- **Context:** The harness's automatic `_verdict()` first pass is explicitly documented (in `run.py`'s own docstring) as needing manual review before being trusted. The hand review found real corrections (e.g. EVAL-006's injection-resistance cases were auto-scored `Fail` on the wrong yardstick; EVAL-011's error rows were auto-scored `Partial` via a vacuous truth). `pages/evaluation.py` reads the same JSON file directly.
- **Options considered:** (1) keep the raw harness output in the JSON file and only apply corrections in the prose written into `EVALUATION_REPORT.md`; (2) apply the same corrections directly to `evaluation_results.json` (in place) so the file, the report, and the live dashboard all agree.
- **Coding-agent contribution:** Chose option 2 specifically so the dashboard wouldn't visibly contradict the written report (e.g. showing 9 raw `Fail`s in a chart while the report explains a hand-corrected 8) — verified the corrected tallies (25 Pass / 7 Partial / 8 Fail / 4 N/A) match exactly between the JSON, the report's comparison table, and the live dashboard screenshot.
- **Evidence reviewed:** The full 44-row trace/citation dump for every corrected row (documented per-case in `EVALUATION_REPORT.md`'s Phase 8 section).
- **Decision and owner:** Option 2 — decided by the coding agent; a data-consistency choice, not a product tradeoff needing user input.
- **Consequences or follow-up:** `evaluation_results.json` now carries `hand_reviewed: true` and a `hand_review_note` field pointing back to the report's reasoning, so a future reader of the raw JSON isn't misled into thinking it's the harness's untouched first pass.
- **Status:** Accepted

### Decision: Package as two `docker-compose` services from one image, not one multi-process container

- **Phase:** 9 — Package the product
- **Context:** `05-evaluation-and-release.md`'s Phase 9 asks to expose both the Streamlit and FastAPI ports and "keep the packaging modest." The app has always run as two separate processes (`uv run streamlit run app.py`, `uv run uvicorn company_assistant.api:app`); Docker packaging needed to decide how those two processes map onto container(s).
- **Options considered:** (1) one container running both processes (e.g. a shell script backgrounding one and foregrounding the other, or a process supervisor like `supervisord`); (2) one shared `Dockerfile`, two `docker-compose` services (`api`, `ui`) that each run the same image with a different `command:`.
- **Coding-agent contribution:** Chose option 2 directly — it needs no process supervisor (a real dependency `AGENTS.md`'s "no half-finished implementations"/"keep it modest" spirit argues against introducing just to run two commands), gives each interface its own restart/log/port lifecycle, and lets `api` alone own the one-time index-sync step with a proper `healthcheck` gate (`ui` uses `depends_on: api: condition: service_healthy`) — avoiding a real race where both processes could otherwise call `sync_index()` concurrently against the same fresh, empty Chroma/SQLite store on first startup.
- **Evidence reviewed:** `docker compose up --build` against fresh named volumes — `api` reached `healthy` only after its sync completed (`GET /status` → 23 indexed sources), and `ui` started only after that, never racing the initial sync.
- **Decision and owner:** Option 2 — decided by the coding agent; a packaging-mechanics choice already covered by the approved Phase 9 plan, not a product tradeoff needing user input.
- **Consequences or follow-up:** `docker-compose.yml`'s two named volumes (`index_data`, `feedback_data`) are the only persistent state; verified they survive `docker compose down`/`up` (not `down -v`). `data/database/company.db` ships baked into the image (the one reproducible fixture `AGENTS.md` allows committed) — no volume needed for it.
- **Status:** Accepted

### Decision: Pin `torch` to the CPU-only wheel index

- **Phase:** 9 — Package the product (found while verifying the built image)
- **Context:** The first built image was 18.7GB — almost entirely `nvidia-*`/`cuda-*` libraries pulled in transitively by `torch` (via `sentence-transformers`, used only for the small local embedding model). Nothing in this project uses a GPU: Groq handles all LLM inference remotely, and the embedding model runs on CPU. This directly conflicted with Phase 9's "keep the packaging modest" instruction, but fixing it meant touching `pyproject.toml`/`uv.lock` — a dependency-resolution change beyond what the approved Phase 9 plan (Docker files only) covered.
- **Options considered:** (1) accept the large image and move on; (2) pin `torch` to PyPI's CPU-only wheel index (`download.pytorch.org/whl/cpu`) via `[tool.uv.sources]`, scoped to Linux (macOS already resolves a lean CPU/MPS build from the normal index, so no override needed there).
- **Coding-agent contribution:** Flagged the finding and the scope question to the user directly rather than silently expanding the approved plan. Implemented option 2 after approval; found and worked around a real uv behavior along the way — `[tool.uv.sources]` only applies to a project's *direct* dependencies, and `torch` was purely transitive, so the override was silently ignored until `torch` was added to `[project.dependencies]` explicitly (confirmed via `uv lock -v`, which showed zero mentions of the custom index until that change).
- **Evidence reviewed:** `uv lock -v` debug output before/after (confirmed `torch==2.14.0+cpu` resolves with no `nvidia-*`/`cuda-*` dependencies on Linux); rebuilt image measured at 4.78GB (down from 18.7GB); local macOS `uv sync` re-verified working (`torch.__version__` importable) after the re-lock.
- **Decision and owner:** Option 2 — the user approved directly via `AskUserQuestion` after the finding was presented.
- **Consequences or follow-up:** `uv lock` (regenerated from scratch, not a surgical `--upgrade-package`) incidentally bumped several unrelated packages to newer compatible versions (pydantic, streamlit, sentence-transformers, etc.) — all within this project's existing `>=` lower-bound constraints, smoke-tested locally, no issue found. None outstanding.
- **Status:** Accepted
