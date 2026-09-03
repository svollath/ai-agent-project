"""Semantic index lifecycle: chunking, permission metadata, sync, and rebuild.

Indexing (this module) and querying (`retrieval.semantic_search`) are
deliberately separate. Querying only ever reads the already-persisted Chroma
collection; it never re-runs connectors or re-embeds anything. Freshness is
therefore governed by when `sync_index()` last ran, not by when a question was
asked — see `deliverables/DECISIONS.md` for why this tradeoff was chosen.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from company_assistant.connectors import load_all_documents_with_github_status
from company_assistant.models import CompanyDocument, EmployeeRole

INDEX_ROOT = Path("data/index")
CHROMA_PERSIST_DIR = INDEX_ROOT / "chroma"
MANIFEST_PATH = INDEX_ROOT / "manifest.json"
COLLECTION_NAME = "company_documents"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

ROLES: tuple[EmployeeRole, ...] = (
    "customer_success",
    "engineering",
    "people_operations",
    "finance",
)
ROLE_METADATA_PREFIX = "role_"
EXTRA_METADATA_PREFIX = "meta_"

_embeddings: HuggingFaceEmbeddings | None = None


class SyncResult(TypedDict):
    added: int
    updated: int
    removed: int
    unchanged: int
    total_indexed: int
    github_state: str
    last_synced_at: str


def _embedding_function() -> HuggingFaceEmbeddings:
    """Load the local embedding model once and reuse it.

    First call downloads the model from Hugging Face Hub; every later call in
    the process reuses the cached instance and does no network I/O.
    """

    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return _embeddings


def get_vector_store() -> Chroma:
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embedding_function(),
        persist_directory=str(CHROMA_PERSIST_DIR),
    )


def _fingerprint(document: CompanyDocument) -> str:
    """Detect any change to a source's content or governance metadata."""

    canonical = json.dumps(
        {
            "title": document.title,
            "content": document.content,
            "allowed_roles": sorted(document.allowed_roles),
            "confidentiality": document.confidentiality,
            "author": document.author,
            "occurred_at": document.occurred_at.isoformat()
            if document.occurred_at
            else None,
            "source_path": document.source_path,
            "metadata": document.metadata,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_chroma_document(document: CompanyDocument) -> Document:
    """Chunk one document.

    One chunk per document (no splitting): every fixture source is a single
    short message, email, issue, or policy excerpt (16-32 lines), so a
    splitter would fragment already-atomic context without a retrieval
    benefit. This was compared against a `RecursiveCharacterTextSplitter` on
    representative questions; see `deliverables/DECISIONS.md`.
    """

    metadata: dict[str, str | int | float | bool | None] = {
        "source_id": document.source_id,
        "source_type": document.source_type,
        "title": document.title,
        "source_path": document.source_path,
        "confidentiality": document.confidentiality,
        "author": document.author,
        "occurred_at": document.occurred_at.isoformat() if document.occurred_at else None,
    }
    for role in ROLES:
        metadata[f"{ROLE_METADATA_PREFIX}{role}"] = role in document.allowed_roles
    for key, value in document.metadata.items():
        metadata[f"{EXTRA_METADATA_PREFIX}{key}"] = value
    return Document(page_content=document.content, metadata=metadata, id=document.source_id)


def document_from_chunk_metadata(content: str, metadata: dict) -> CompanyDocument:
    """Reconstruct a `CompanyDocument` from a persisted chunk (no reload)."""

    allowed_roles = frozenset(
        role for role in ROLES if metadata.get(f"{ROLE_METADATA_PREFIX}{role}") is True
    )
    extra_metadata = {
        key[len(EXTRA_METADATA_PREFIX) :]: value
        for key, value in metadata.items()
        if key.startswith(EXTRA_METADATA_PREFIX)
    }
    occurred_at = metadata.get("occurred_at")
    return CompanyDocument(
        source_id=metadata["source_id"],
        source_type=metadata["source_type"],
        title=metadata["title"],
        content=content,
        source_path=metadata["source_path"],
        allowed_roles=allowed_roles,
        confidentiality=metadata.get("confidentiality", "internal"),
        author=metadata.get("author"),
        occurred_at=datetime.fromisoformat(occurred_at) if occurred_at else None,
        metadata=extra_metadata,
    )


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"sources": {}, "last_synced_at": None}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict) -> None:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def last_indexed_status() -> dict | None:
    """Return the manifest's freshness summary without syncing."""

    manifest = _load_manifest()
    if manifest.get("last_synced_at") is None:
        return None
    return {
        "last_synced_at": manifest["last_synced_at"],
        "indexed_sources": len(manifest["sources"]),
    }


def sync_index(data_root: Path = Path("data/raw")) -> SyncResult:
    """Upsert changed/new sources and remove deleted ones. Idempotent."""

    documents, github_state = load_all_documents_with_github_status(data_root)
    current = {document.source_id: document for document in documents}

    manifest = _load_manifest()
    known_sources: dict[str, dict] = manifest["sources"]
    store = get_vector_store()

    added = updated = removed = unchanged = 0

    for source_id, document in current.items():
        fingerprint = _fingerprint(document)
        existing = known_sources.get(source_id)
        if existing is None:
            store.add_documents([_to_chroma_document(document)])
            known_sources[source_id] = {"fingerprint": fingerprint}
            added += 1
        elif existing["fingerprint"] != fingerprint:
            store.delete(ids=[source_id])
            store.add_documents([_to_chroma_document(document)])
            known_sources[source_id] = {"fingerprint": fingerprint}
            updated += 1
        else:
            unchanged += 1

    deleted_source_ids = set(known_sources) - set(current)
    for source_id in deleted_source_ids:
        store.delete(ids=[source_id])
        del known_sources[source_id]
        removed += 1

    manifest["last_synced_at"] = datetime.now(UTC).isoformat()
    manifest["embedding_model"] = EMBEDDING_MODEL_NAME
    manifest["chunking_strategy"] = "whole_document"
    _save_manifest(manifest)

    return SyncResult(
        added=added,
        updated=updated,
        removed=removed,
        unchanged=unchanged,
        total_indexed=len(known_sources),
        github_state=github_state,
        last_synced_at=manifest["last_synced_at"],
    )


def rebuild_index(data_root: Path = Path("data/raw")) -> SyncResult:
    """Wipe the collection and manifest, then reindex from scratch.

    Use when incremental `sync_index()` is suspected to be inconsistent
    (e.g. the manifest and the collection disagree after a crash).
    """

    store = get_vector_store()
    existing_ids = store.get(include=[])["ids"]
    if existing_ids:
        store.delete(ids=existing_ids)
    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()
    return sync_index(data_root)
