"""Connectors that normalize local company exports."""

from company_assistant.connectors.documents import load_documents
from company_assistant.connectors.email import load_emails
from company_assistant.connectors.github import load_github_issues
from company_assistant.connectors.registry import (
    load_all_documents,
    load_all_documents_with_github_status,
)
from company_assistant.connectors.slack import load_slack_messages

__all__ = [
    "load_all_documents",
    "load_all_documents_with_github_status",
    "load_documents",
    "load_emails",
    "load_github_issues",
    "load_slack_messages",
]
