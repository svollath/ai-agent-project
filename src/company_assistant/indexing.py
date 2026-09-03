"""Manage the semantic index: chunking, embeddings, and sync lifecycle.

Kept deliberately separate from retrieval.py: this module owns the Chroma
collection and the on-disk manifest that makes upserts/deletes possible.
retrieval.py's semantic_search() only ever reads through SemanticIndex.query(),
which already rechecks permissions against the live employee role via the
Chroma metadata filter — a second recheck against the *current* CompanyDocument
(not the possibly-stale indexed copy) happens in retrieval.py itself.
"""

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import chromadb
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel, Field

from company_assistant.connectors.common import VALID_ROLES
from company_assistant.models import CompanyDocument

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# One boolean metadata field per role, since Chroma's `where` filter needs
# scalar values, not list membership. Enforces permissions before a chunk
# can ever become a search candidate (not just as a post-filter).
ROLE_METADATA_KEYS = {role: f"role_{role}" for role in VALID_ROLES}


class DocumentChunk(BaseModel):
    chunk_id: str
    source_id: str
    chunk_index: int
    text: str


Chunker = Callable[[CompanyDocument], list[DocumentChunk]]


def chunk_by_document(document: CompanyDocument) -> list[DocumentChunk]:
    """One chunk per document: title plus full content."""

    text = f"{document.title}\n\n{document.content}".strip()
    return [
        DocumentChunk(
            chunk_id=f"{document.source_id}::0",
            source_id=document.source_id,
            chunk_index=0,
            text=text,
        )
    ]


def chunk_by_paragraph(document: CompanyDocument) -> list[DocumentChunk]:
    """One chunk per blank-line-delimited paragraph, title prefixed for context."""

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", document.content) if p.strip()]
    if not paragraphs:
        paragraphs = [document.content.strip()]
    return [
        DocumentChunk(
            chunk_id=f"{document.source_id}::{index}",
            source_id=document.source_id,
            chunk_index=index,
            text=f"{document.title}\n\n{paragraph}".strip(),
        )
        for index, paragraph in enumerate(paragraphs)
    ]


def _document_fingerprint(document: CompanyDocument) -> str:
    """Hash the fields that should trigger re-embedding when changed."""

    payload = json.dumps(
        {
            "title": document.title,
            "content": document.content,
            "allowed_roles": sorted(document.allowed_roles),
            "confidentiality": document.confidentiality,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ManifestEntry(BaseModel):
    content_hash: str
    chunk_ids: list[str]
    last_indexed: datetime


class IndexManifest(BaseModel):
    entries: dict[str, ManifestEntry] = Field(default_factory=dict)


class IndexSyncResult(BaseModel):
    upserted_sources: list[str]
    deleted_sources: list[str]
    unchanged_sources: int
    last_indexed: datetime


class SemanticIndex:
    """A persistent Chroma collection plus the manifest that drives its sync."""

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = "company_documents",
        embeddings: HuggingFaceEmbeddings | None = None,
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.manifest_path = persist_dir / "manifest.json"
        self.embeddings = embeddings or HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    def _load_manifest(self) -> IndexManifest:
        if not self.manifest_path.exists():
            return IndexManifest()
        return IndexManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: IndexManifest) -> None:
        self.manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def _chunk_metadata(self, chunk: DocumentChunk, document: CompanyDocument) -> dict[str, bool | str | int]:
        metadata: dict[str, bool | str | int] = {
            "source_id": document.source_id,
            "chunk_index": chunk.chunk_index,
        }
        for role, key in ROLE_METADATA_KEYS.items():
            metadata[key] = role in document.allowed_roles
        return metadata

    def sync(self, documents: list[CompanyDocument], chunker: Chunker) -> IndexSyncResult:
        """Upsert changed/new documents, delete removed ones, skip the rest."""

        manifest = self._load_manifest()
        documents_by_id = {document.source_id: document for document in documents}
        now = datetime.now(UTC)

        upserted: list[str] = []
        unchanged = 0
        new_entries: dict[str, ManifestEntry] = {}

        ids_to_delete: list[str] = []
        ids_to_add: list[str] = []
        texts_to_add: list[str] = []
        metadatas_to_add: list[dict[str, bool | str | int]] = []

        for source_id, document in documents_by_id.items():
            fingerprint = _document_fingerprint(document)
            prior = manifest.entries.get(source_id)
            if prior is not None and prior.content_hash == fingerprint:
                new_entries[source_id] = prior
                unchanged += 1
                continue

            if prior is not None:
                ids_to_delete.extend(prior.chunk_ids)

            chunks = chunker(document)
            for chunk in chunks:
                ids_to_add.append(chunk.chunk_id)
                texts_to_add.append(chunk.text)
                metadatas_to_add.append(self._chunk_metadata(chunk, document))

            new_entries[source_id] = ManifestEntry(
                content_hash=fingerprint,
                chunk_ids=[chunk.chunk_id for chunk in chunks],
                last_indexed=now,
            )
            upserted.append(source_id)

        deleted: list[str] = []
        for source_id, entry in manifest.entries.items():
            if source_id not in documents_by_id:
                ids_to_delete.extend(entry.chunk_ids)
                deleted.append(source_id)

        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        if ids_to_add:
            embeddings = self.embeddings.embed_documents(texts_to_add)
            self._collection.upsert(
                ids=ids_to_add,
                documents=texts_to_add,
                embeddings=embeddings,
                metadatas=metadatas_to_add,
            )

        self._save_manifest(IndexManifest(entries=new_entries))
        return IndexSyncResult(
            upserted_sources=upserted,
            deleted_sources=deleted,
            unchanged_sources=unchanged,
            last_indexed=now,
        )

    def rebuild(self, documents: list[CompanyDocument], chunker: Chunker) -> IndexSyncResult:
        """Full local rebuild: clear the collection and manifest, then sync from empty."""

        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine"}
        )
        if self.manifest_path.exists():
            self.manifest_path.unlink()
        return self.sync(documents, chunker)

    def last_indexed(self) -> datetime | None:
        manifest = self._load_manifest()
        if not manifest.entries:
            return None
        return max(entry.last_indexed for entry in manifest.entries.values())

    def query(
        self, query_text: str, employee_role: str, limit: int = 4
    ) -> list[tuple[str, float]]:
        """Return up to `limit` (source_id, score) pairs, best chunk per source.

        The `where` filter excludes chunks the employee's role can't see
        before the ANN search runs, so denied documents never become
        candidates. Score is 1 - cosine distance, informational only (rank
        order, not the raw value, is what hybrid_search relies on).
        """

        role_key = ROLE_METADATA_KEYS.get(employee_role)
        if role_key is None or not query_text.strip():
            return []

        fetch_k = max(limit * 4, 10)
        query_embedding = self.embeddings.embed_query(query_text)
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k,
            where={role_key: True},
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        best_by_source: dict[str, float] = {}
        for distance, metadata in zip(distances, metadatas, strict=True):
            source_id = str(metadata["source_id"])
            if source_id not in best_by_source or distance < best_by_source[source_id]:
                best_by_source[source_id] = distance

        ranked = sorted(best_by_source.items(), key=lambda item: item[1])[:limit]
        return [(source_id, max(0.0, 1.0 - distance)) for source_id, distance in ranked]


def delete_index(persist_dir: Path) -> None:
    """Remove a semantic index directory entirely (used to reset between comparisons)."""

    shutil.rmtree(persist_dir, ignore_errors=True)


# Paragraph chunking was chosen over whole-document chunking based on
# evidence in deliverables/EVALUATION_REPORT.md's Phase 5 section: 12/15 vs
# 9/15 expected sources found on the same pinned corpus, comparable latency.
DEFAULT_SEMANTIC_INDEX_DIR = Path("data/index/semantic")

_index_cache: dict[str, SemanticIndex] = {}


def get_shared_index(index_dir: Path = DEFAULT_SEMANTIC_INDEX_DIR) -> SemanticIndex:
    """Reuse one SemanticIndex (and its loaded embedding model) per directory.

    Shared by service.py and agent.py so both pay the embedding-model load
    cost only once per process, against the same on-disk collection.
    """

    key = str(index_dir)
    if key not in _index_cache:
        _index_cache[key] = SemanticIndex(index_dir)
    return _index_cache[key]
