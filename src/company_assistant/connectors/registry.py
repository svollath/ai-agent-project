"""Load every supplied unstructured source through its connector."""

from pathlib import Path

from company_assistant.connectors.documents import load_documents
from company_assistant.connectors.email import load_emails
from company_assistant.connectors.github import load_github_issues_connected
from company_assistant.connectors.slack import load_slack_messages
from company_assistant.models import CompanyDocument


def load_all_documents(
    data_root: Path = Path("data/raw"),
) -> tuple[list[CompanyDocument], list[str]]:
    """Return normalized documents from all source families, plus source notes.

    Source notes disclose connector state that isn't visible from the
    documents alone, such as whether GitHub issues came from the live API
    or the local fallback (see connectors/github.py).
    """

    github_documents, github_note = load_github_issues_connected(data_root / "github")
    documents = [
        *load_slack_messages(data_root / "slack"),
        *load_emails(data_root / "email"),
        *load_documents(data_root / "documents"),
        *github_documents,
    ]
    return documents, [github_note]
