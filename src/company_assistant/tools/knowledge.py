"""Search and citation-resolution tools over unstructured company knowledge.

Every builder here takes `employee` once, from the caller's verified
identity, and returns a plain function that only exposes model-fillable
arguments (`query`, `source_id`, ...) — the model never sees or sets
`employee`, so permission enforcement cannot be bypassed by anything the
model says or is told by retrieved content.
"""

from pathlib import Path
from textwrap import shorten

from company_assistant.connectors import load_all_documents_with_github_status
from company_assistant.models import EmployeeContext, RetrievalMode
from company_assistant.retrieval import hybrid_search, lexical_search, semantic_search, tokenize
from company_assistant.security import filter_permitted
from company_assistant.tools.schemas import (
    EvidenceItem,
    OpenSourceResult,
    SearchCompanyKnowledgeResult,
    SearchWorkItemsResult,
    WorkItem,
)

WORK_ITEM_LIMIT = 10


def _excerpt(content: str, width: int = 240) -> str:
    return shorten(" ".join(content.split()), width=width, placeholder="...")


def build_search_company_knowledge_tool(
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
    retrieval_mode: RetrievalMode = "lexical",
):
    """`retrieval_mode` is fixed per agent build, never model-chosen.

    Exists so Phase 8 can compare "semantic with agent" and "hybrid with
    agent" against this same tool, per `04-connected-rag-and-agent.md`'s
    three required comparison variants. Lexical is the default, matching the
    Phase 5 decision recorded in `DECISIONS.md`.
    """

    def search_company_knowledge(query: str) -> dict:
        """Search Slack, email, and document evidence for the employee's role.

        Use this for general company knowledge questions (policies, release
        decisions, customer communications). For GitHub issue questions, use
        search_work_items instead. Permission filtering happens before
        ranking; forbidden sources never appear in the results.
        """

        if retrieval_mode == "semantic":
            results = semantic_search(query, employee)
        else:
            documents, _ = load_all_documents_with_github_status(data_root)
            if retrieval_mode == "hybrid":
                results = hybrid_search(query, documents, employee)
            else:
                results = lexical_search(query, documents, employee)
        return SearchCompanyKnowledgeResult(
            query=query,
            results=[
                EvidenceItem(
                    source_id=result.document.source_id,
                    title=result.document.title,
                    source_type=result.document.source_type,
                    excerpt=_excerpt(result.document.content),
                    occurred_at=result.document.occurred_at,
                )
                for result in results
            ],
        ).model_dump(mode="json")

    return search_company_knowledge


def build_search_work_items_tool(
    employee: EmployeeContext, data_root: Path = Path("data/raw")
):
    def search_work_items(query: str) -> dict:
        """Find relevant GitHub issues (local export plus the live repository).

        Ranks only against other GitHub issues, never against Slack, email,
        or documents, so a relevant issue can't be pushed out of the results
        by unrelated evidence in a shared ranking window. Use this for any
        question about GitHub issues, work items, or their status/owner.
        """

        documents, _ = load_all_documents_with_github_status(data_root)
        github_documents = [d for d in documents if d.source_type == "github"]
        permitted = filter_permitted(github_documents, employee)

        query_tokens = tokenize(query)
        scored = []
        for document in permitted:
            document_tokens = tokenize(f"{document.title} {document.content}")
            score = (
                len(query_tokens & document_tokens) / len(query_tokens)
                if query_tokens
                else 1.0
            )
            if score > 0:
                scored.append((score, document))
        scored.sort(
            key=lambda pair: (
                pair[0],
                pair[1].occurred_at.timestamp() if pair[1].occurred_at else 0.0,
            ),
            reverse=True,
        )

        return SearchWorkItemsResult(
            query=query,
            results=[
                WorkItem(
                    source_id=document.source_id,
                    title=document.title,
                    state=document.metadata.get("state"),
                    number=document.metadata.get("number"),
                    owner_or_author=document.author,
                    url=document.source_path,
                    occurred_at=document.occurred_at,
                )
                for _, document in scored[:WORK_ITEM_LIMIT]
            ],
        ).model_dump(mode="json")

    return search_work_items


def build_open_source_tool(employee: EmployeeContext, data_root: Path = Path("data/raw")):
    def open_source(source_id: str) -> dict:
        """Resolve one citation by its stable source ID.

        Re-runs the permission check against the current data, not a cached
        result, so a source deleted or reclassified after an earlier search
        cannot be opened. `found=False` covers both "no such source" and
        "no longer permitted" identically.
        """

        documents, _ = load_all_documents_with_github_status(data_root)
        matches = [document for document in documents if document.source_id == source_id]
        permitted = filter_permitted(matches, employee)
        if not permitted:
            return OpenSourceResult(found=False, source_id=source_id).model_dump(mode="json")

        document = permitted[0]
        return OpenSourceResult(
            found=True,
            source_id=document.source_id,
            title=document.title,
            source_type=document.source_type,
            content=document.content,
            source_path=document.source_path,
            occurred_at=document.occurred_at,
        ).model_dump(mode="json")

    return open_source
