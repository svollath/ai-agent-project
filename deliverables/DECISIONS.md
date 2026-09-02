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
