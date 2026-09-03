"""Lexical, semantic, and hybrid retrieval, kept separately comparable."""

import re
from collections.abc import Iterable

from company_assistant.indexing import (
    ROLE_METADATA_PREFIX,
    document_from_chunk_metadata,
    get_vector_store,
)
from company_assistant.models import CompanyDocument, EmployeeContext, SearchResult
from company_assistant.security import filter_permitted

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")
RRF_K = 60
HYBRID_CANDIDATE_LIMIT = 10


def tokenize(text: str) -> set[str]:
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

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    results: list[SearchResult] = []
    for document in filter_permitted(documents, employee):
        document_tokens = tokenize(f"{document.title} {document.content}")
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
    employee: EmployeeContext,
    limit: int = 4,
) -> list[SearchResult]:
    """Rank documents by embedding similarity against the persisted index.

    Only ever reads what `indexing.sync_index()` last wrote — never re-runs
    connectors or re-embeds. Permissions are enforced twice: the vector
    store's `where` filter excludes other roles' documents from becoming
    candidates at all, and `filter_permitted()` rechecks the reconstructed
    documents afterward so stale or malformed index metadata can't bypass the
    first filter.
    """

    store = get_vector_store()
    raw_results = store.similarity_search_with_score(
        query,
        k=limit,
        filter={f"{ROLE_METADATA_PREFIX}{employee.role}": True},
    )
    candidates = [
        document_from_chunk_metadata(chunk.page_content, chunk.metadata)
        for chunk, _ in raw_results
    ]
    distance_by_source_id = {
        document.source_id: distance
        for document, (_, distance) in zip(candidates, raw_results, strict=True)
    }
    return [
        SearchResult(document=document, score=1 / (1 + distance_by_source_id[document.source_id]))
        for document in filter_permitted(candidates, employee)
    ]


def hybrid_search(
    query: str,
    documents: Iterable[CompanyDocument],
    employee: EmployeeContext,
    limit: int = 4,
) -> list[SearchResult]:
    """Combine lexical and semantic rankings with Reciprocal Rank Fusion.

    RRF combines ranks rather than raw scores, so lexical's 0-1 token-overlap
    ratio and semantic's embedding distance never need to be rescaled onto a
    shared axis: `score(doc) = sum(1 / (RRF_K + rank))` over every ranking the
    document appears in. A document found by both signals outranks one found
    by only one.
    """

    lexical_results = lexical_search(query, documents, employee, limit=HYBRID_CANDIDATE_LIMIT)
    semantic_results = semantic_search(query, employee, limit=HYBRID_CANDIDATE_LIMIT)

    combined_scores: dict[str, float] = {}
    documents_by_id: dict[str, CompanyDocument] = {}
    for ranking in (lexical_results, semantic_results):
        for rank, result in enumerate(ranking, start=1):
            source_id = result.document.source_id
            combined_scores[source_id] = combined_scores.get(source_id, 0.0) + 1 / (RRF_K + rank)
            documents_by_id.setdefault(source_id, result.document)

    ranked_ids = sorted(combined_scores, key=lambda source_id: combined_scores[source_id], reverse=True)
    return [
        SearchResult(document=documents_by_id[source_id], score=combined_scores[source_id])
        for source_id in ranked_ids[:limit]
    ]
