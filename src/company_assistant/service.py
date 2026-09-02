"""Interface-independent assistant service: lexical, semantic, and hybrid."""

from pathlib import Path
from textwrap import shorten

from company_assistant.connectors import load_all_documents
from company_assistant.indexing import SemanticIndex, chunk_by_paragraph
from company_assistant.models import Answer, Citation, EmployeeContext, RetrievalMode, SearchResult
from company_assistant.retrieval import hybrid_search, lexical_search, semantic_search

# Paragraph chunking was chosen over whole-document chunking based on
# evidence in deliverables/EVALUATION_REPORT.md's Phase 5 section: 12/15 vs
# 9/15 expected sources found on the same pinned corpus, comparable latency.
DEFAULT_SEMANTIC_INDEX_DIR = Path("data/index/semantic")

_index_cache: dict[str, SemanticIndex] = {}


def _get_semantic_index(index_dir: Path) -> SemanticIndex:
    """Reuse one SemanticIndex (and its loaded embedding model) per directory."""

    key = str(index_dir)
    if key not in _index_cache:
        _index_cache[key] = SemanticIndex(index_dir)
    return _index_cache[key]


def _excerpt(content: str, width: int = 240) -> str:
    """Create a compact readable preview without cutting a word in half."""

    normalized = " ".join(content.split())
    return shorten(normalized, width=width, placeholder="...")


def _answer_from_results(
    results: list[SearchResult],
    employee: EmployeeContext,
    retrieval_mode: RetrievalMode,
    trace: list[str],
) -> Answer:
    if not results:
        return Answer(
            status="insufficient_evidence",
            text="I could not find permitted evidence for this question.",
            retrieval_mode=retrieval_mode,
            trace=[*trace, "Applied role filter", f"Ran {retrieval_mode} search"],
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
        text=f"{retrieval_mode.capitalize()} evidence found:\n" + "\n".join(evidence_lines),
        retrieval_mode=retrieval_mode,
        citations=citations,
        trace=[
            *trace,
            f"Applied role filter for {employee.role}",
            f"Returned {len(results)} {retrieval_mode} results",
            "No generative language model or agent was used (embeddings only)"
            if retrieval_mode != "lexical"
            else "No language model or agent was used",
        ],
    )


def answer_with_baseline(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
) -> Answer:
    """Return extractive evidence from the deterministic starter retriever.

    Participants replace or extend this baseline with semantic retrieval and a
    tool-using agent. Keeping it runnable provides a comparison point.
    """

    documents, source_notes = load_all_documents(data_root)
    results = lexical_search(question, documents, employee)
    if not results:
        return Answer(
            status="insufficient_evidence",
            text="I could not find permitted evidence for this question.",
            trace=[
                "Loaded local exports",
                *source_notes,
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
            *source_notes,
            f"Applied role filter for {employee.role}",
            f"Returned {len(results)} lexical results",
            "No language model or agent was used",
        ],
    )


def answer_with_semantic(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
    index_dir: Path = DEFAULT_SEMANTIC_INDEX_DIR,
) -> Answer:
    """Return evidence from the semantic (embedding-based) retriever.

    Syncs the index against the currently loaded documents on every call
    (cheap once embedded: unchanged documents are skipped by content hash),
    so changed and deleted records are reflected without a separate manual
    reindex step.
    """

    documents, source_notes = load_all_documents(data_root)
    index = _get_semantic_index(index_dir)
    sync_result = index.sync(documents, chunk_by_paragraph)
    results = semantic_search(question, documents, employee, index)
    return _answer_from_results(
        results,
        employee,
        "semantic",
        trace=[
            "Loaded local exports",
            *source_notes,
            f"Synced semantic index (upserted={len(sync_result.upserted_sources)}, "
            f"deleted={len(sync_result.deleted_sources)}, "
            f"unchanged={sync_result.unchanged_sources})",
        ],
    )


def answer_with_hybrid(
    question: str,
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
    index_dir: Path = DEFAULT_SEMANTIC_INDEX_DIR,
) -> Answer:
    """Return evidence from reciprocal-rank fusion of lexical and semantic results."""

    documents, source_notes = load_all_documents(data_root)
    index = _get_semantic_index(index_dir)
    sync_result = index.sync(documents, chunk_by_paragraph)
    results = hybrid_search(question, documents, employee, index)
    return _answer_from_results(
        results,
        employee,
        "hybrid",
        trace=[
            "Loaded local exports",
            *source_notes,
            f"Synced semantic index (upserted={len(sync_result.upserted_sources)}, "
            f"deleted={len(sync_result.deleted_sources)}, "
            f"unchanged={sync_result.unchanged_sources})",
        ],
    )
