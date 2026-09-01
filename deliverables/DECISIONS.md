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
