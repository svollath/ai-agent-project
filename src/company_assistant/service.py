"""Interface-independent baseline assistant service."""

from pathlib import Path
from textwrap import shorten

from company_assistant.connectors import load_all_documents_with_github_status
from company_assistant.models import Answer, Citation, EmployeeContext
from company_assistant.retrieval import lexical_search


def _excerpt(content: str, width: int = 240) -> str:
    """Create a compact readable preview without cutting a word in half."""

    normalized = " ".join(content.split())
    return shorten(normalized, width=width, placeholder="...")


def answer_with_baseline(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
) -> Answer:
    """Return extractive evidence from the deterministic starter retriever.

    Participants replace or extend this baseline with semantic retrieval and a
    tool-using agent. Keeping it runnable provides a comparison point.
    """

    documents, github_state = load_all_documents_with_github_status(data_root)
    github_trace = (
        "GitHub source: local export + live repository"
        if github_state == "live"
        else "GitHub source: local export only (live unavailable or not configured)"
    )
    results = lexical_search(question, documents, employee)
    if not results:
        return Answer(
            status="insufficient_evidence",
            text="I could not find permitted evidence for this question.",
            trace=[
                "Loaded local exports",
                github_trace,
                "Applied role filter",
                "Ran lexical search",
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
        citations=citations,
        trace=[
            "Loaded local exports",
            github_trace,
            f"Applied role filter for {employee.role}",
            f"Returned {len(results)} lexical results",
            "No language model or agent was used",
        ],
    )
