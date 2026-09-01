"""Load every supplied unstructured source through its connector."""

from pathlib import Path

from company_assistant.connectors.documents import load_documents
from company_assistant.connectors.email import load_emails
from company_assistant.connectors.github import load_github_issues
from company_assistant.connectors.slack import load_slack_messages
from company_assistant.models import CompanyDocument


def load_all_documents(data_root: Path = Path("data/raw")) -> list[CompanyDocument]:
    """Return normalized documents from all local source families."""

    return [
        *load_slack_messages(data_root / "slack"),
        *load_emails(data_root / "email"),
        *load_documents(data_root / "documents"),
        *load_github_issues(data_root / "github"),
    ]
