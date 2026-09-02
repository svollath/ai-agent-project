"""Load every supplied source through its connector."""

import os
from pathlib import Path

from dotenv import load_dotenv

from company_assistant.connectors.documents import load_documents
from company_assistant.connectors.email import load_emails
from company_assistant.connectors.github import load_github_issues
from company_assistant.connectors.github_live import (
    GitHubSourceState,
    load_live_github_issues,
)
from company_assistant.connectors.slack import load_slack_messages
from company_assistant.models import CompanyDocument

load_dotenv()


def load_all_documents_with_github_status(
    data_root: Path = Path("data/raw"),
) -> tuple[list[CompanyDocument], GitHubSourceState]:
    """Return normalized documents plus whether a live GitHub repository fed them.

    The local GitHub export always loads (it is fixture product content, not a
    cache of any particular live repository, and other source families and
    evaluation cases depend on it). Reads `GITHUB_REPOSITORY`/`GITHUB_TOKEN`
    from the environment (`.env`); when configured and reachable, that live
    repository's issues are added on top and the state is reported as `live`.
    When no repository is configured or the live fetch fails, no live issues
    are added and the state is reported as `local_fallback` — meaning "no live
    add-on this turn", not "the local export stands in for the live repo".
    """

    live_documents, github_state = load_live_github_issues(
        repository=os.environ.get("GITHUB_REPOSITORY"),
        token=os.environ.get("GITHUB_TOKEN"),
    )
    documents = [
        *load_slack_messages(data_root / "slack"),
        *load_emails(data_root / "email"),
        *load_documents(data_root / "documents"),
        *load_github_issues(data_root / "github"),
        *live_documents,
    ]
    return documents, github_state


def load_all_documents(data_root: Path = Path("data/raw")) -> list[CompanyDocument]:
    """Return normalized documents from all source families.

    Prefer `load_all_documents_with_github_status` when the caller needs to
    disclose whether GitHub issues came from the live source or the fallback.
    """

    documents, _ = load_all_documents_with_github_status(data_root)
    return documents
