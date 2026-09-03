"""Runtime application state: action proposals and conversation history.

Kept in a separate database from company.db: that file is a reproducible
teaching fixture that initialize_database() fully drops and recreates,
while this one holds live, generated state (drafted proposals, chat
history) that must survive across runs and must never be wiped by a
fixture regeneration.
"""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from company_assistant.models import ActionProposal, ActionStatus, EmployeeContext

APP_STATE_PATH = Path("data/database/app_state.db")

ApprovalDecision = Literal["approve", "reject", "edit"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_proposals (
    proposal_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    destination TEXT NOT NULL,
    payload TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,
    history TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id
    ON conversation_messages (conversation_id);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(_SCHEMA)
    return connection


def _row_to_proposal(row: sqlite3.Row) -> ActionProposal:
    return ActionProposal(
        proposal_id=row["proposal_id"],
        action_type=row["action_type"],
        destination=row["destination"],
        payload=json.loads(row["payload"]),
        requested_by=row["requested_by"],
        status=row["status"],
    )


def save_action_proposal(
    proposal: ActionProposal, actor: EmployeeContext, path: Path = APP_STATE_PATH
) -> None:
    """Persist a freshly drafted proposal. The proposal_id must be new."""

    now = datetime.now(UTC).isoformat()
    history = [
        {
            "event": "drafted",
            "status": proposal.status,
            "actor": actor.employee_id,
            "detail": f"{proposal.action_type} -> {proposal.destination}",
            "timestamp": now,
        }
    ]
    with closing(_connect(path)) as connection:
        connection.execute(
            """
            INSERT INTO action_proposals
                (proposal_id, action_type, destination, payload, requested_by,
                 status, history, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.proposal_id,
                proposal.action_type,
                proposal.destination,
                json.dumps(proposal.payload),
                proposal.requested_by,
                proposal.status,
                json.dumps(history),
                now,
                now,
            ),
        )
        connection.commit()


def get_action_proposal(proposal_id: str, path: Path = APP_STATE_PATH) -> ActionProposal | None:
    with closing(_connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM action_proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
    return _row_to_proposal(row) if row is not None else None


def get_action_proposal_history(
    proposal_id: str, path: Path = APP_STATE_PATH
) -> list[dict[str, str]]:
    with closing(_connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT history FROM action_proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
    return json.loads(row["history"]) if row is not None else []


def update_action_proposal(
    proposal_id: str,
    actor: EmployeeContext,
    *,
    new_status: ActionStatus,
    event: str,
    detail: str,
    payload: dict[str, str | int | float | bool | None] | None = None,
    path: Path = APP_STATE_PATH,
) -> ActionProposal | None:
    """Append one audit event and update status (and optionally the payload).

    Returns None if the proposal_id doesn't exist, so callers can distinguish
    "not found" from a successful transition.
    """

    with closing(_connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM action_proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None

        history = json.loads(row["history"])
        now = datetime.now(UTC).isoformat()
        history.append(
            {
                "event": event,
                "status": new_status,
                "actor": actor.employee_id,
                "detail": detail,
                "timestamp": now,
            }
        )
        new_payload = json.dumps(payload) if payload is not None else row["payload"]

        connection.execute(
            """
            UPDATE action_proposals
            SET status = ?, history = ?, payload = ?, updated_at = ?
            WHERE proposal_id = ?
            """,
            (new_status, json.dumps(history), new_payload, now, proposal_id),
        )
        connection.commit()

    return get_action_proposal(proposal_id, path)


def append_conversation_message(
    conversation_id: str,
    role: Literal["user", "assistant"],
    content: str,
    employee: EmployeeContext,
    path: Path = APP_STATE_PATH,
) -> None:
    with closing(_connect(path)) as connection:
        connection.execute(
            """
            INSERT INTO conversation_messages
                (conversation_id, role, content, employee_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                employee.employee_id,
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()


def get_conversation_history(
    conversation_id: str, limit: int = 10, path: Path = APP_STATE_PATH
) -> list[dict[str, str]]:
    """Return up to `limit` most recent messages for a conversation, oldest first."""

    with closing(_connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT role, content FROM conversation_messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
