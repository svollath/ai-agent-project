"""Interface-independent assistant service: lexical, semantic, or hybrid."""

from pathlib import Path
from textwrap import shorten

from company_assistant.connectors import load_all_documents_with_github_status
from company_assistant.models import Answer, Citation, EmployeeContext, RetrievalMode
from company_assistant.retrieval import hybrid_search, lexical_search, semantic_search


def _excerpt(content: str, width: int = 240) -> str:
    """Create a compact readable preview without cutting a word in half."""

    normalized = " ".join(content.split())
    return shorten(normalized, width=width, placeholder="...")


def answer(
    question: str,
    employee: EmployeeContext,
    retrieval_mode: RetrievalMode = "lexical",
    data_root: Path = Path("data/raw"),
) -> Answer:
    """Return extractive evidence using the requested retrieval mode.

    Lexical and hybrid load the live document set on every call (so GitHub
    freshness matches Phase 4's per-request behavior); semantic only reads
    the persisted Chroma index built by `indexing.sync_index()` and never
    re-runs connectors. This keeps the three modes runnable side by side for
    comparison without one silently depending on another's freshness.
    """

    documents, github_state = load_all_documents_with_github_status(data_root)
    github_trace = (
        "GitHub source: local export + live repository"
        if github_state == "live"
        else "GitHub source: local export only (live unavailable or not configured)"
    )

    if retrieval_mode == "lexical":
        results = lexical_search(question, documents, employee)
    elif retrieval_mode == "semantic":
        results = semantic_search(question, employee)
    elif retrieval_mode == "hybrid":
        results = hybrid_search(question, documents, employee)
    else:
        raise ValueError(f"Unknown retrieval mode: {retrieval_mode}")

    if not results:
        return Answer(
            status="insufficient_evidence",
            text="I could not find permitted evidence for this question.",
            retrieval_mode=retrieval_mode,
            trace=[
                "Loaded local exports",
                github_trace,
                "Applied role filter",
                f"Ran {retrieval_mode} search",
            ],
        )

    evidence_lines = [
        f"- {result.document.title}: {_excerpt(result.document.content)}"
        for result in results
    ]
    citations = [
        Citation(
            source_id=result.document.source_id,
            title=result.document.title,
            source_type=result.document.source_type,
            source_path=result.document.source_path,
            occurred_at=result.document.occurred_at,
        )
        for result in results
    ]
    return Answer(
        status="evidence_found",
        text="Baseline evidence found:\n" + "\n".join(evidence_lines),
        retrieval_mode=retrieval_mode,
        citations=citations,
        trace=[
            "Loaded local exports",
            github_trace,
            f"Applied role filter for {employee.role}",
            f"Returned {len(results)} {retrieval_mode} results",
            "No language model or agent was used",
        ],
    )


def answer_with_baseline(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
) -> Answer:
    """Lexical-only entry point kept for the existing Streamlit/FastAPI callers.

    Participants replace or extend this with a tool-using agent. Keeping it
    runnable provides a comparison point for the semantic and hybrid modes.
    """

    return answer(question, employee, "lexical", data_root)
