"""Narrow, typed wrappers around the read-only SQLite lookups in `database.py`.

`database.get_support_case()`/`list_project_status()` already take an
`employee` argument and are deny-by-default. These builders only add the
closure that supplies `employee` from verified identity instead of the model,
and translate the raw dict/list results into the tool schemas.
"""

from pathlib import Path

from company_assistant.database import DATABASE_PATH, get_support_case, list_project_status
from company_assistant.models import EmployeeContext
from company_assistant.tools.schemas import ListProjectStatusResult, ProjectStatusItem, SupportCaseResult


def build_get_support_case_tool(employee: EmployeeContext, path: Path = DATABASE_PATH):
    def get_support_case_tool(case_id: str) -> dict:
        """Look up one customer support case by its case ID.

        Returns `found=False` for both an unknown case ID and a case the
        employee's role isn't permitted to see — the two are indistinguishable
        by design, so a denied role can't infer a case exists.
        """

        result = get_support_case(case_id, employee, path=path)
        if result is None:
            return SupportCaseResult(found=False, case_id=case_id).model_dump(mode="json")
        return SupportCaseResult(
            found=True,
            case_id=result["case_id"],
            subject=result["subject"],
            status=result["status"],
            severity=result["severity"],
            owner=result["owner"],
            updated_at=result["updated_at"],
            source_id=result["source_id"],
        ).model_dump(mode="json")

    return get_support_case_tool


def build_list_project_status_tool(employee: EmployeeContext, path: Path = DATABASE_PATH):
    def list_project_status_tool() -> dict:
        """List operational status and target date for every tracked project.

        Returns an empty list if the employee's role isn't permitted, the
        same shape as "no projects exist" — no distinction is made.
        """

        results = list_project_status(employee, path=path)
        return ListProjectStatusResult(
            results=[
                ProjectStatusItem(
                    source_id=result["source_id"],
                    project_id=result["project_id"],
                    name=result["name"],
                    owner=result["owner"],
                    status=result["status"],
                    target_date=result["target_date"],
                )
                for result in results
            ]
        ).model_dump(mode="json")

    return list_project_status_tool
