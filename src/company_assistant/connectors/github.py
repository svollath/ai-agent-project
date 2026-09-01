"""Normalize the supplied GitHub Issues export."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from company_assistant.connectors.common import parse_roles
from company_assistant.models import CompanyDocument


class GitHubIssue(BaseModel):
    source_id: str
    number: int
    title: str
    body: str
    state: str
    author: str
    assignees: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    updated_at: datetime
    allowed_roles: list[str]


def load_github_issues(folder: Path) -> list[CompanyDocument]:
    """Load exported issues while preserving work-item metadata."""

    documents: list[CompanyDocument] = []
    for path in sorted(folder.glob("*.json")):
        raw_issues = json.loads(path.read_text(encoding="utf-8"))
        for raw_issue in raw_issues:
            issue = GitHubIssue.model_validate(raw_issue)
            details = (
                f"State: {issue.state}\nLabels: {', '.join(issue.labels)}\n"
                f"Assignees: {', '.join(issue.assignees) or 'Unassigned'}\n\n{issue.body}"
            )
            documents.append(
                CompanyDocument(
                    source_id=issue.source_id,
                    source_type="github",
                    title=f"Issue #{issue.number}: {issue.title}",
                    content=details,
                    source_path=str(path),
                    allowed_roles=parse_roles(issue.allowed_roles),
                    author=issue.author,
                    occurred_at=issue.updated_at,
                    metadata={"number": issue.number, "state": issue.state},
                )
            )
    return documents
