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

### Decision: Record the live GitHub repository as committed project config, not a per-developer `.env` value

- **Phase:** 4 — Live GitHub connector (prep)
- **Context:** Chose `AlexDeWilde/ai-agent-project-test-repo` (new, public, created for this project) as the one live GitHub source required by file `04`. `04` only requires the **token** to live in `.env` ("Keep the token in `.env`"); it says nothing about the repository name needing the same treatment. The repository identifier is not sensitive — it's a public URL — so requiring every group member to privately discover it and hand-copy it into their own untracked `.env` is pure friction with no security upside.
- **Options considered:** (1) Leave `GITHUB_REPOSITORY` as a blank line in `.env.example`, same as the token, relying on each collaborator being told the value out-of-band; (2) fill in the real value directly inside `.env.example`; (3) record it in this decision log and `ACCESS_MATRIX.md` (both committed, both places a collaborator would already look for source configuration), and have Phase 4's connector code fall back to this value as a committed default when the `GITHUB_REPOSITORY` env var is unset.
- **Coding-agent contribution:** Confirmed no config-loading code exists yet (Phase 4 not implemented) and that `python-dotenv` is a declared but unused dependency, so there's no existing convention this decision needs to conform to.
- **Evidence reviewed:** `04-connected-rag-and-agent.md` (exact wording of the `.env` requirement — token only), `.env.example`, `pyproject.toml`.
- **Decision and owner:** Option 3 — confirmed by the user.
- **Consequences or follow-up:** `.env.example` keeps `GITHUB_REPOSITORY=` blank (avoids implying it's secret alongside the token) but now points readers here. `ACCESS_MATRIX.md`'s "Live GitHub work items" row and Source Governance table, previously abstract ("the live repo"), now name the actual repository. When Phase 4's connector is implemented, it must treat `os.environ.get("GITHUB_REPOSITORY")` as an override of this documented default, not a requirement — so the app runs against the shared repo with zero local setup, while still letting a developer point at a different repo temporarily via their own `.env`. If the override path is ever used, that fact should be visible in the trace/UI (same "disclose which state is active" requirement already flagged for live-vs-fallback in `PROGRESS_LOG.md`), so a silently overridden repo doesn't look identical to the team default.
- **Status:** Accepted
