"""Read-only live GitHub Issues connector.

Normalizes live issues into the same `CompanyDocument` contract as the local
connector (`connectors/github.py`) and applies the same kind of by-label
access policy. See ACCESS_MATRIX.md's "Live GitHub work items" row and Source
Governance table for the policy this implements.
"""

from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from company_assistant.models import CompanyDocument, EmployeeRole

GITHUB_API_BASE = "https://api.github.com"
ISSUES_PER_PAGE = 100
REQUEST_TIMEOUT_SECONDS = 10.0

BASE_ROLES: frozenset[EmployeeRole] = frozenset({"engineering"})
LABEL_ROLE_POLICY: dict[str, EmployeeRole] = {
    "customer-impact": "customer_success",
    "support": "customer_success",
    "finance-review": "finance",
    "billing": "finance",
    "release-blocker": "finance",
}

GitHubSourceState = Literal["live", "local_fallback"]


class GitHubConnectorError(Exception):
    """Raised when the live GitHub source cannot be trusted for an answer.

    Callers must treat this as a controlled failure, never fabricate issue
    data, and either surface the error or fall back to the local export.
    """


class _LiveGitHubIssue(BaseModel):
    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    updated_at: datetime
    user: dict[str, object] | None = None
    assignees: list[dict[str, object]] = Field(default_factory=list)
    labels: list[dict[str, object] | str] = Field(default_factory=list)
    pull_request: dict[str, object] | None = None


def _infer_allowed_roles(label_names: list[str]) -> frozenset[EmployeeRole]:
    """Assign roles by label, mirroring the local export's documented policy.

    Engineering owns every live issue. A label additionally grants access to
    the role it names in `LABEL_ROLE_POLICY`; an unmapped label grants
    nothing beyond the engineering baseline. `people_operations` is never
    granted, matching ACCESS_MATRIX.md.
    """

    roles = set(BASE_ROLES)
    for label in label_names:
        role = LABEL_ROLE_POLICY.get(label)
        if role:
            roles.add(role)
    return frozenset(roles)


def _label_names(raw_labels: list[dict[str, str] | str]) -> list[str]:
    return [label if isinstance(label, str) else label["name"] for label in raw_labels]


def fetch_live_issues(
    repository: str, token: str | None = None
) -> list[CompanyDocument]:
    """Fetch every issue from `owner/repo` and normalize it.

    Raises `GitHubConnectorError` on any HTTP, network, or malformed-response
    failure instead of returning an empty or partial result silently.
    """

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repository_slug = repository.strip("/").replace("/", "-")
    documents: list[CompanyDocument] = []
    page = 1
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            while True:
                response = client.get(
                    f"{GITHUB_API_BASE}/repos/{repository}/issues",
                    headers=headers,
                    params={
                        "state": "all",
                        "per_page": ISSUES_PER_PAGE,
                        "page": page,
                    },
                )
                if response.status_code != 200:
                    raise GitHubConnectorError(
                        f"GitHub API returned {response.status_code} for "
                        f"{repository} (page {page}): {response.text[:200]}"
                    )
                raw_issues = response.json()
                if not raw_issues:
                    break
                for raw_issue in raw_issues:
                    issue = _LiveGitHubIssue.model_validate(raw_issue)
                    if issue.pull_request is not None:
                        continue  # The issues endpoint also returns pull requests.
                    label_names = _label_names(issue.labels)
                    author = (issue.user or {}).get("login", "Unknown")
                    assignee_logins = [a["login"] for a in issue.assignees]
                    details = (
                        f"State: {issue.state}\nLabels: {', '.join(label_names)}\n"
                        f"Assignees: {', '.join(assignee_logins) or 'Unassigned'}\n\n"
                        f"{issue.body or ''}"
                    )
                    documents.append(
                        CompanyDocument(
                            source_id=f"GH-{repository_slug}-{issue.number}",
                            source_type="github",
                            title=f"Issue #{issue.number}: {issue.title}",
                            content=details,
                            source_path=issue.html_url,
                            allowed_roles=_infer_allowed_roles(label_names),
                            author=author,
                            occurred_at=issue.updated_at,
                            metadata={
                                "number": issue.number,
                                "state": issue.state,
                                "repository": repository,
                            },
                        )
                    )
                if len(raw_issues) < ISSUES_PER_PAGE:
                    break
                page += 1
    except httpx.HTTPError as error:
        raise GitHubConnectorError(
            f"Network error contacting GitHub for {repository}: {error}"
        ) from error
    except (KeyError, ValueError) as error:
        raise GitHubConnectorError(
            f"Malformed GitHub API response for {repository}: {error}"
        ) from error

    return documents


def load_live_github_issues(
    repository: str | None,
    token: str | None,
) -> tuple[list[CompanyDocument], GitHubSourceState]:
    """Fetch live issues when a repository is configured, else report the gap.

    Returns `[]` with state `local_fallback` when no repository is configured
    or the live fetch fails. The caller is expected to keep serving its own,
    always-loaded local GitHub export in that case — this function never
    substitutes local content as if it were live, so a genuinely different
    local export (e.g. this project's fictional Atlas fixture) can never be
    mistaken for a live repository's real issues.
    """

    if not repository:
        return [], "local_fallback"

    try:
        return fetch_live_issues(repository, token), "live"
    except GitHubConnectorError:
        return [], "local_fallback"
