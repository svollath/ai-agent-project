"""Deterministic lexical baseline for comparison with semantic retrieval."""

import re
from collections.abc import Iterable

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
