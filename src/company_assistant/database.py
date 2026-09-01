"""Create and query the reproducible Northstar business database."""

import sqlite3
from contextlib import closing
from pathlib import Path

from company_assistant.models import EmployeeContext

DATABASE_PATH = Path("data/database/company.db")

# Mirrors deliverables/ACCESS_MATRIX.md. The schema itself carries no role or
# confidentiality metadata, so narrow lookups must enforce it themselves.
SUPPORT_CASE_ALLOWED_ROLES = frozenset({"customer_success", "finance"})
PROJECT_ALLOWED_ROLES = frozenset({"customer_success", "engineering", "finance"})


def initialize_database(path: Path = DATABASE_PATH) -> None:
    """Recreate the small fictional business database from fixed records."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS support_cases;
            DROP TABLE IF EXISTS projects;
            DROP TABLE IF EXISTS customers;

            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT NOT NULL,
                region TEXT NOT NULL,
                annual_value_eur INTEGER NOT NULL
            );

            CREATE TABLE projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                status TEXT NOT NULL,
                target_date TEXT NOT NULL
            );

            CREATE TABLE support_cases (
                case_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                severity TEXT NOT NULL,
                owner TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            );
            """
        )
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
            [
                ("C-104", "Acme Freight", "Enterprise", "EU", 180000),
                ("C-205", "Blue Yonder Logistics", "Growth", "EU", 72000),
                ("C-309", "Cedar Retail", "Enterprise", "US", 145000),
            ],
        )
        connection.executemany(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "P-ATLAS",
                    "Atlas billing migration",
                    "Nora Kim",
                    "at risk",
                    "2026-09-18",
                ),
                ("P-ORBIT", "Orbit analytics", "Sofia Rossi", "on track", "2026-10-30"),
            ],
        )
        connection.executemany(
            "INSERT INTO support_cases VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "CASE-481",
                    "C-104",
                    "Duplicate invoice",
                    "open",
                    "high",
                    "Maya Chen",
                    "2026-08-24",
                ),
                (
                    "CASE-512",
                    "C-205",
                    "Export delay",
                    "monitoring",
                    "medium",
                    "Maya Chen",
                    "2026-08-21",
                ),
                (
                    "CASE-530",
                    "C-309",
                    "SSO configuration",
                    "resolved",
                    "low",
                    "Ibrahim Noor",
                    "2026-08-12",
                ),
            ],
        )
        connection.commit()


def get_support_case(
    case_id: str, employee: EmployeeContext, path: Path = DATABASE_PATH
) -> dict[str, str] | None:
    """Return one support case through a parameterized read-only query.

    Returns None both when the case does not exist and when the employee's
    role is not permitted, so a denied role cannot infer whether a case
    exists from the response shape alone.
    """

    if employee.role not in SUPPORT_CASE_ALLOWED_ROLES:
        return None

    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT case_id, customer_id, subject, status, severity, owner, updated_at
            FROM support_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["source_id"] = f"DB-{case_id}"
    return result


def list_project_status(
    employee: EmployeeContext, path: Path = DATABASE_PATH
) -> list[dict[str, str]]:
    """Return structured project facts through a parameterized read-only query.

    Returns an empty list when the employee's role is not permitted, matching
    the deny-by-default filtering used for unstructured sources.
    """

    if employee.role not in PROJECT_ALLOWED_ROLES:
        return []

    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT project_id, name, owner, status, target_date FROM projects"
        ).fetchall()

    results = []
    for row in rows:
        result = dict(row)
        result["source_id"] = f"DB-{result['project_id']}"
        results.append(result)
    return results


if __name__ == "__main__":
    initialize_database()
    print(f"Created {DATABASE_PATH}")
