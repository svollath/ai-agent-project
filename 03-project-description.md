# Project Description: Build Northstar's Internal Assistant

You are the AI PM responsible for a prototype that employees can use to question Northstar Labs' private company knowledge. Claude Code or Codex should perform most repository inspection, planning, implementation, and documentation work. Your role is to define the right product, challenge its decisions, verify the evidence, and decide whether the prototype is ready to demonstrate.

This module establishes the product boundary and a trustworthy baseline. Continue with `04-connected-rag-and-agent.md` for the main build and `05-evaluation-and-release.md` for the final product decision.

## Before You Begin

Complete the README setup and open the Streamlit app and FastAPI documentation once. Work through the numbered modules in order.

At the start of each phase:

1. give your coding agent the phase objective and relevant files;
2. ask it to inspect the current implementation and propose a plan;
3. challenge unclear assumptions and approve the plan;
4. let it implement and demonstrate the result;
5. review the changes and evidence yourself;
6. record the important decision in `deliverables/DECISIONS.md`.

## The Outcome

Deliver one polished, end-to-end assistant for a clearly defined employee workflow. It must combine at least three source families, include one live GitHub source, cite its evidence, protect restricted information, and demonstrate reliable abstention.

The completed product must include:

- a clear product brief and access matrix;
- lexical, semantic, and hybrid retrieval that can be compared;
- an update strategy for indexed documents;
- at least four narrow tools and one bounded agent;
- one proposed action that cannot execute without explicit human approval;
- Streamlit and FastAPI interfaces with citations, feedback, and visible system status;
- a comparison dashboard and completed evaluation report;
- a containerized application and a clear release recommendation.

## Phase 1: Frame the Product

Read the company context and inspect the raw data before choosing a solution. Select one primary employee profile and a recurring workflow worth improving. Different groups should be free to choose different profiles and questions.

Ask your coding agent to summarize the available evidence, source limitations, contradictions, and sensitive records. Verify its summary against the files yourself.

Complete `deliverables/PRODUCT_BRIEF.md` with:

- the user and costly workflow;
- the questions in and out of scope;
- measurable acceptance criteria;
- the harm caused by an incorrect answer or data leak;
- one target metric for usefulness and one non-negotiable safety threshold.

**Completion evidence:** another group can explain what your product does, who it serves, and what it refuses to do without seeing the implementation.

## Phase 2: Design the Information Boundary

Map the required sources and complete `deliverables/ACCESS_MATRIX.md`. Decide which metadata is needed to enforce permissions, resolve citations, compare conflicting information, and remove stale records. Use only the four fictional employee roles implemented in the starter.

Ask your coding agent to propose an architecture and threat model. Challenge assumptions such as "the system prompt will prevent leaks" or "the latest document is always correct." Record the accepted design and at least one rejected alternative.

**Completion evidence:** every source has an owner, confidentiality level, allowed roles, stable identifier, citation strategy, and update policy.

## Phase 3: Establish a Deterministic Baseline

Recreate the teaching database:

```bash
uv run python -m company_assistant.database
```

Run the Streamlit starter and try at least one permitted query, one forbidden query, one missing-answer query, and one question with conflicting evidence. Inspect `src/company_assistant/retrieval.py` and `src/company_assistant/service.py` to understand what the lexical baseline can and cannot do.

The baseline may return irrelevant but permitted evidence instead of recognizing that it should abstain. Record this as a product failure; it is different from leaking a forbidden source.

The supplied connectors are working reference implementations. Ask your coding agent to audit their normalized output and permission metadata. Change them only if your product needs additional metadata. Confirm that malformed records fail visibly rather than disappearing silently.

Capture the baseline results in `deliverables/EVALUATION_REPORT.md`. They become the comparison point for the retrieval and agent versions.

**Completion evidence:** you can inspect normalized records, explain a baseline failure, and show that the selected employee cannot retrieve the restricted HR document. No model key or network call is needed.

## Continue the Build

When the product boundary, access matrix, and baseline are credible, continue with [Connected RAG and Agent](04-connected-rag-and-agent.md). Do not begin with prompt tuning: the next module first connects and indexes trustworthy evidence.
