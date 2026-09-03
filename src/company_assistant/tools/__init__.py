"""Narrow, typed tools for the Phase 6 agent.

`build_tools(employee)` is the one entry point the agent runtime should use —
it captures the caller's verified identity once and returns the five
model-callable tools, each with `employee` fixed by closure so the model can
never supply or override it. `tools.actions` additionally exposes
`approve_action`/`reject_action`/`edit_action`/`execute_action`, which are
deliberately not part of this list — see `tools/actions.py`.
"""

from pathlib import Path
from typing import Callable

from company_assistant.models import EmployeeContext, RetrievalMode
from company_assistant.tools.actions import build_propose_action_tool
from company_assistant.tools.knowledge import (
    build_open_source_tool,
    build_search_company_knowledge_tool,
    build_search_work_items_tool,
)
from company_assistant.tools.structured_data import (
    build_get_support_case_tool,
    build_list_project_status_tool,
)


def build_tools(
    employee: EmployeeContext,
    data_root: Path = Path("data/raw"),
    retrieval_mode: RetrievalMode = "lexical",
) -> list[Callable]:
    """Return the agent's six tools, bound to one employee's identity.

    `retrieval_mode` fixes which retrieval `search_company_knowledge` uses
    for this agent build (not model-chosen) — see that tool's docstring.
    """

    return [
        build_search_company_knowledge_tool(employee, data_root, retrieval_mode),
        build_search_work_items_tool(employee, data_root),
        build_get_support_case_tool(employee),
        build_list_project_status_tool(employee),
        build_open_source_tool(employee, data_root),
        build_propose_action_tool(employee),
    ]
