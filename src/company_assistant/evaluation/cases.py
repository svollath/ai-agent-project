"""Load behavior-oriented evaluation cases without calling a model."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """One existing message supplied before an evaluation question."""

    role: Literal["user", "assistant"]
    content: str


class EvaluationCase(BaseModel):
    """One product behavior that the finished assistant must demonstrate."""

    case_id: str
    category: Literal[
        "single_source_retrieval",
        "cross_source_synthesis",
        "conflicting_evidence",
        "structured_lookup",
        "forbidden_access",
        "indirect_prompt_injection",
        "insufficient_evidence",
        "tool_failure",
        "follow_up",
        "human_approval",
        "index_lifecycle",
        "live_connector_fallback",
        "live_source_evidence",
        "feedback_capture",
    ]
    employee_id: str
    question: str
    expected_source_ids: list[str]
    forbidden_source_ids: list[str]
    expected_behavior: str
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    setup_hint: str | None = None


def load_evaluation_cases(
    path: Path = Path("data/evaluation/cases.json"),
) -> list[EvaluationCase]:
    """Validate and return every supplied evaluation case."""

    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = [EvaluationCase.model_validate(raw_case) for raw_case in raw_cases]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Evaluation case IDs must be unique")
    return cases
