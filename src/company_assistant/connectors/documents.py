"""Normalize Markdown document exports with YAML front matter."""

from datetime import datetime
from pathlib import Path
from typing import Literal

import frontmatter
from pydantic import BaseModel

from company_assistant.connectors.common import parse_roles
from company_assistant.models import CompanyDocument


class DocumentMetadata(BaseModel):
    source_id: str
    title: str
    owner: str = "Unknown"
    effective_at: datetime
    status: str = "current"
    confidentiality: Literal["internal", "restricted"] = "internal"
    allowed_roles: list[str]


def load_documents(folder: Path) -> list[CompanyDocument]:
    """Load document exports and validate their governance metadata."""

    documents: list[CompanyDocument] = []
    for path in sorted(folder.glob("*.md")):
        post = frontmatter.load(path)
        metadata = DocumentMetadata.model_validate(post.metadata)
        documents.append(
            CompanyDocument(
                source_id=metadata.source_id,
                source_type="document",
                title=metadata.title,
                content=post.content.strip(),
                source_path=str(path),
                allowed_roles=parse_roles(metadata.allowed_roles),
                confidentiality=metadata.confidentiality,
                author=metadata.owner,
                occurred_at=metadata.effective_at,
                metadata={"status": metadata.status},
            )
        )
    return documents
