"""Deterministic lexical baseline, plus semantic and hybrid retrieval."""

import re
from collections.abc import Iterable

from company_assistant.indexing import SemanticIndex
from company_assistant.models import CompanyDocument, EmployeeContext, SearchResult
from company_assistant.security import filter_permitted

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text) if len(token) > 2}


def lexical_search(
    query: str,
    documents: Iterable[CompanyDocument],
    employee: EmployeeContext,
    limit: int = 4,
) -> list[SearchResult]:
    """Rank permitted documents by query-token coverage.

    This transparent baseline is intentionally limited. Preserve it when adding
    semantic retrieval so the project can measure whether complexity helps.
    """

    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    results: list[SearchResult] = []
    for document in filter_permitted(documents, employee):
        document_tokens = _tokens(f"{document.title} {document.content}")
        score = len(query_tokens.intersection(document_tokens)) / len(query_tokens)
        if score > 0:
            results.append(SearchResult(document=document, score=score))

    results.sort(
        key=lambda result: (
            result.score,
            result.document.occurred_at.timestamp()
            if result.document.occurred_at
            else 0.0,
        ),
        reverse=True,
    )
    return results[:limit]


def semantic_search(
    query: str,
    documents: Iterable[CompanyDocument],
    employee: EmployeeContext,
    index: SemanticIndex,
    limit: int = 4,
) -> list[SearchResult]:
    """Rank permitted documents by embedding similarity via a synced SemanticIndex.

    The index's own `where` filter already excludes documents the employee's
    role can't see before the ANN search runs. This function re-checks each
    result against the *current* CompanyDocument's allowed_roles (not the
    possibly-stale indexed metadata) before it can become a citation, per
    file 04's "recheck permissions when resolving citations" requirement.
    """

    documents_by_id = {document.source_id: document for document in documents}
    ranked = index.query(query, employee.role, limit=limit)

    results: list[SearchResult] = []
    for source_id, score in ranked:
        document = documents_by_id.get(source_id)
        if document is None:
            continue  # deleted since the index was last synced; never serve stale content
        if employee.role not in document.allowed_roles:
            continue  # stale index metadata disagrees with the live document; deny wins
        results.append(SearchResult(document=document, score=score))
    return results


def hybrid_search(
    query: str,
    documents: Iterable[CompanyDocument],
    employee: EmployeeContext,
    index: SemanticIndex,
    limit: int = 4,
    rrf_k: int = 60,
) -> list[SearchResult]:
    """Combine lexical and semantic rankings via reciprocal rank fusion.

    RRF sidesteps reconciling lexical's token-overlap ratio with semantic's
    cosine distance on a shared scale — only each list's rank order matters.
    """

    documents = list(documents)
    lexical_results = lexical_search(query, documents, employee, limit=max(limit, 10))
    semantic_results = semantic_search(query, documents, employee, index, limit=max(limit, 10))

    fused_scores: dict[str, float] = {}
    document_by_id: dict[str, CompanyDocument] = {}
    for result_list in (lexical_results, semantic_results):
        for rank, result in enumerate(result_list):
            source_id = result.document.source_id
            fused_scores[source_id] = fused_scores.get(source_id, 0.0) + 1.0 / (rrf_k + rank + 1)
            document_by_id[source_id] = result.document

    ranked_ids = sorted(fused_scores, key=lambda source_id: fused_scores[source_id], reverse=True)
    return [
        SearchResult(document=document_by_id[source_id], score=fused_scores[source_id])
        for source_id in ranked_ids[:limit]
    ]
