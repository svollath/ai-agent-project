"""Normalize GitHub issues from the local export or the live REST API."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from company_assistant.connectors.common import parse_roles
from company_assistant.models import CompanyDocument, EmployeeRole

# deliverables/DECISIONS.md: "Record the live GitHub repository as committed
# project config, not a per-developer .env value". GITHUB_REPOSITORY/TOKEN
# env vars, when set, override this default rather than being required.
DEFAULT_LIVE_REPOSITORY = "AlexDeWilde/ai-agent-project-test-repo"
GITHUB_API_BASE = "https://api.github.com"

# deliverables/ACCESS_MATRIX.md: "Live GitHub work items" row. The live demo
# repo carries genuine connector-engineering issues, not the fictional Atlas
# story, so there is no natural label taxonomy mapping to Northstar's roles.
# Every live issue defaults to engineering; these two labels were created
# specifically to exercise per-issue role scoping end to end.
ROLE_LABEL_POLICY: dict[str, EmployeeRole] = {
    "finance-review": "finance",
    "customer-impact": "customer_success",
}
DEFAULT_LIVE_ROLES = frozenset({"engineering"})


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


class LiveFetchError(Exception):
    """Raised when the live GitHub API cannot be used for this request.

    Callers treat this as a signal to fall back to the local export, never
    as a reason to fabricate or guess at issue content.
    """


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
                    metadata={
                        "number": issue.number,
                        "state": issue.state,
                        "labels": ",".join(issue.labels),
                    },
                )
            )
    return documents


def _allowed_roles_for_labels(labels: list[str]) -> frozenset[EmployeeRole]:
    roles = set(DEFAULT_LIVE_ROLES)
    for label in labels:
        role = ROLE_LABEL_POLICY.get(label)
        if role is not None:
            roles.add(role)
    return parse_roles(roles)


def _normalize_live_issue(raw: dict[str, Any], repository: str) -> CompanyDocument:
    """Pure mapping from one raw GitHub API issue to a CompanyDocument.

    Kept free of any HTTP concerns so it is directly testable against a
    hand-written fixture dict without a network call.
    """

    labels = [label["name"] for label in raw.get("labels", [])]
    assignees = [assignee["login"] for assignee in raw.get("assignees", [])]
    details = (
        f"State: {raw['state']}\nLabels: {', '.join(labels)}\n"
        f"Assignees: {', '.join(assignees) or 'Unassigned'}\n\n{raw.get('body') or ''}"
    )
    return CompanyDocument(
        source_id=f"GH-{repository}-{raw['number']}",
        source_type="github",
        title=f"Issue #{raw['number']}: {raw['title']}",
        content=details,
        source_path=raw["html_url"],
        allowed_roles=_allowed_roles_for_labels(labels),
        author=raw["user"]["login"],
        occurred_at=datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00")),
        metadata={
            "number": raw["number"],
            "state": raw["state"],
            "labels": ",".join(labels),
        },
    )


def _fetch_live_issues_raw(
    repository: str, token: str | None, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Fetch every issue page from the GitHub REST API.

    Excludes pull requests, which the issues endpoint also returns. Raises
    LiveFetchError on any network error, non-200 response, or malformed
    payload so the caller can fall back instead of inventing evidence.
    """

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        issues: list[dict[str, Any]] = []
        url: str | None = f"{GITHUB_API_BASE}/repos/{repository}/issues"
        params: dict[str, Any] | None = {"state": "all", "per_page": 100}
        while url:
            try:
                response = client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise LiveFetchError(
                    f"network error contacting GitHub API: {exc}"
                ) from exc
            if response.status_code != 200:
                raise LiveFetchError(
                    f"GitHub API returned {response.status_code} for {repository}: "
                    f"{response.text[:200]}"
                )
            try:
                page_issues = response.json()
            except ValueError as exc:
                raise LiveFetchError(
                    f"GitHub API returned a non-JSON response: {exc}"
                ) from exc
            issues.extend(item for item in page_issues if "pull_request" not in item)
            url = response.links.get("next", {}).get("url")
            params = None
        return issues
    finally:
        if owns_client:
            client.close()


def load_live_github_issues(
    repository: str, token: str | None = None, *, client: httpx.Client | None = None
) -> list[CompanyDocument]:
    """Fetch and normalize live issues. Raises LiveFetchError on any failure."""

    raw_issues = _fetch_live_issues_raw(repository, token, client=client)
    try:
        return [_normalize_live_issue(raw, repository) for raw in raw_issues]
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveFetchError(f"malformed issue payload from {repository}: {exc}") from exc


def load_github_issues_connected(
    local_folder: Path,
    repository: str | None = None,
    token: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[CompanyDocument], str]:
    """Try the live GitHub source, falling back to the local export.

    Returns the documents plus one human-readable note disclosing which
    source was used, so the caller can surface it (e.g. in Answer.trace)
    instead of leaving live-vs-fallback state invisible.
    """

    repository = repository or os.environ.get("GITHUB_REPOSITORY") or DEFAULT_LIVE_REPOSITORY
    token = token or os.environ.get("GITHUB_TOKEN") or None

    try:
        documents = load_live_github_issues(repository, token, client=client)
    except LiveFetchError as exc:
        local_documents = load_github_issues(local_folder)
        note = (
            f"GitHub: live fetch from {repository} failed ({exc}); "
            f"used local fallback ({local_folder})"
        )
        return local_documents, note

    note = f"GitHub: used live source {repository} ({len(documents)} issues)"
    return documents, note
