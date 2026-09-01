"""Normalize the supplied Slack JSON export."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from company_assistant.connectors.common import parse_roles
from company_assistant.models import CompanyDocument


class SlackMessage(BaseModel):
    source_id: str
    channel: str
    author: str
    timestamp: datetime
    text: str
    allowed_roles: list[str]
    confidentiality: Literal["internal", "restricted"] = "internal"
    thread_title: str | None = None


def load_slack_messages(folder: Path) -> list[CompanyDocument]:
    """Load every Slack export file in a folder."""

    documents: list[CompanyDocument] = []
    for path in sorted(folder.glob("*.json")):
        raw_messages = json.loads(path.read_text(encoding="utf-8"))
        for raw_message in raw_messages:
            message = SlackMessage.model_validate(raw_message)
            documents.append(
                CompanyDocument(
                    source_id=message.source_id,
                    source_type="slack",
                    title=message.thread_title or f"#{message.channel} message",
                    content=message.text,
                    source_path=str(path),
                    allowed_roles=parse_roles(message.allowed_roles),
                    confidentiality=message.confidentiality,
                    author=message.author,
                    occurred_at=message.timestamp,
                    metadata={"channel": message.channel},
                )
            )
    return documents
