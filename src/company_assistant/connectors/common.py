"""Shared connector validation helpers."""

from collections.abc import Iterable
from typing import Literal, cast

from company_assistant.models import EmployeeRole

VALID_ROLES: frozenset[EmployeeRole] = frozenset(
    {"customer_success", "engineering", "people_operations", "finance"}
)
Confidentiality = Literal["internal", "restricted"]


def parse_roles(raw_roles: str | Iterable[str]) -> frozenset[EmployeeRole]:
    """Parse and validate explicit source access roles."""

    values = raw_roles.split(",") if isinstance(raw_roles, str) else raw_roles
    roles = frozenset(str(value).strip() for value in values if str(value).strip())
    invalid = roles.difference(VALID_ROLES)
    if invalid:
        raise ValueError(f"Unknown employee roles: {sorted(invalid)}")
    if not roles:
        raise ValueError("Source access metadata must contain at least one role")
    return cast(frozenset[EmployeeRole], roles)


def parse_confidentiality(raw_value: object) -> Confidentiality:
    """Validate the two confidentiality levels used by the teaching fixtures."""

    value = str(raw_value)
    if value not in {"internal", "restricted"}:
        raise ValueError(f"Unknown confidentiality level: {value}")
    return value
