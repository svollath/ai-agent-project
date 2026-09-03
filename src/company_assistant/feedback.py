"""Minimal useful/not-useful feedback storage.

Appends one JSON line per record to a file under `data/feedback/`, which is
git-ignored (see `.gitignore`) — feedback is generated local state, not the
reproducible teaching fixture `AGENTS.md` allows to be committed.
"""

from pathlib import Path

from company_assistant.models import Feedback

FEEDBACK_PATH = Path("data/feedback/feedback.jsonl")


def record_feedback(feedback: Feedback, path: Path = FEEDBACK_PATH) -> None:
    """Append one feedback record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(feedback.model_dump_json() + "\n")


def list_feedback(path: Path = FEEDBACK_PATH) -> list[Feedback]:
    """Return every recorded feedback entry, oldest first."""

    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Feedback.model_validate_json(line) for line in lines if line.strip()]
