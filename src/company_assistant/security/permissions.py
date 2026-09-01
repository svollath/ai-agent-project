"""Deterministic access checks applied before retrieval."""

from collections.abc import Iterable

from company_assistant.models import CompanyDocument, EmployeeContext


def filter_permitted(
    documents: Iterable[CompanyDocument], employee: EmployeeContext
) -> list[CompanyDocument]:
    """Return only records explicitly allowed for the employee's role.

    Missing or empty role metadata is denied by the model validation and this
    membership check. The function deliberately has no model dependency.
    """

    return [
        document for document in documents if employee.role in document.allowed_roles
    ]
