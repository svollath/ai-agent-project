"""Normalize local RFC 5322 email fixtures."""

from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from company_assistant.connectors.common import parse_confidentiality, parse_roles
from company_assistant.models import CompanyDocument


def _plain_text(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("plain",))
    if body is None:
        raise ValueError("Email fixture has no plain-text body")
    return body.get_content().strip()


def load_emails(folder: Path) -> list[CompanyDocument]:
    """Load emails using explicit teaching metadata stored in X- headers."""

    documents: list[CompanyDocument] = []
    parser = BytesParser(policy=policy.default)
    for path in sorted(folder.glob("*.eml")):
        message = parser.parsebytes(path.read_bytes())
        source_id = message.get("X-Source-ID")
        roles = message.get("X-Access-Roles")
        if not source_id or not roles:
            raise ValueError(f"{path} is missing X-Source-ID or X-Access-Roles")
        documents.append(
            CompanyDocument(
                source_id=source_id,
                source_type="email",
                title=str(message.get("Subject", "Untitled email")),
                content=_plain_text(message),
                source_path=str(path),
                allowed_roles=parse_roles(roles),
                confidentiality=parse_confidentiality(
                    message.get("X-Confidentiality", "internal")
                ),
                author=str(message.get("From", "Unknown")),
                occurred_at=datetime.fromisoformat(str(message.get("X-Occurred-At"))),
                metadata={
                    "from": str(message.get("From", "")),
                    "to": str(message.get("To", "")),
                    # Same "current" default and vocabulary as the documents
                    # connector's `status` field (see document.py), so
                    # compare_sources treats a superseded email the same way
                    # it already treats an archived document.
                    "status": str(message.get("X-Status", "current")),
                },
            )
        )
    return documents
