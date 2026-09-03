"""NiceGUI interface for the Northstar internal assistant — k3s packaging experiment.

Fully separate from the Streamlit app (`app.py` at the repo root) and the
plain FastAPI service (`company_assistant.api`): its own FastAPI instance, its
own port, its own container. See `k3s-exp/k8s/README.md` for the deployment
story. Business logic is imported directly from the shared `company_assistant`
package — nothing here duplicates it.
"""

import json
import queue
from contextlib import asynccontextmanager
from pathlib import Path
from typing import get_args

import pandas as pd
from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import run, ui

from company_assistant.agent import answer_with_agent
from company_assistant.api import EMPLOYEES
from company_assistant.connectors.registry import load_all_documents_with_github_status
from company_assistant.feedback import list_feedback, record_feedback
from company_assistant.indexing import last_indexed_status, sync_index
from company_assistant.models import Answer, Feedback, FeedbackReason
from company_assistant.tools.actions import (
    approve_action,
    edit_action,
    execute_action,
    list_pending_proposals,
    reject_action,
)

ROLE_BADGE_CLASSES = {
    "engineering": "bg-blue-500 text-white",
    "customer_success": "bg-emerald-500 text-black",
    "finance": "bg-amber-500 text-black",
    "people_operations": "bg-purple-500 text-white",
}
STATUS_COLORS = {
    "answered": "green",
    "evidence_found": "green",
    "insufficient_evidence": "amber",
    "forbidden": "red",
    "error": "red",
}

# Only guards per-tab UI state (conversation history, feedback-already-submitted
# markers) — never authentication or anything sensitive — so a fixed local value
# is fine for this experiment. Required by NiceGUI's `app.storage.tab`.
STORAGE_SECRET = "northstar-k3s-exp-local-dev"

# Quasar ships its own default button fill in a `quasar_importants` CSS layer
# that outranks plain Tailwind utility classes (`bg-emerald-800` etc. are
# silently ignored) — `!important` inline styles are the only thing that
# reliably wins, so buttons that need a real, always-visible (not just
# on-hover) color use these instead of `.classes(...)`.
POSITIVE_BUTTON_STYLE = "background-color: #065f46 !important; color: #ffffff !important;"
NEGATIVE_BUTTON_STYLE = "background-color: #9f1239 !important; color: #ffffff !important;"
NEUTRAL_BUTTON_STYLE = "background-color: #334155 !important; color: #ffffff !important;"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        sync_index()
    except Exception as error:  # never crash-loop the whole app over a transient sync failure
        print(f"Startup index sync failed, continuing without it: {error}")
    yield


app = FastAPI(title="Northstar Internal Assistant (k3s-exp)", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    """Cheap readiness/liveness signal — no model or disk call."""

    return {"status": "ok"}


def render_nav(active: str) -> None:
    """Left-drawer navigation shared by both pages."""

    with ui.column().classes("w-full gap-1 mb-3"):
        ui.label("Menu").classes(
            "text-xs font-semibold uppercase tracking-wide text-slate-500"
        )
        for label, path in (("Assistant", "/"), ("Evaluation", "/evaluation")):
            is_active = label == active
            ui.link(label, path).classes(
                "text-base font-medium no-underline px-3 py-2 rounded "
                + ("bg-slate-700 text-white" if is_active else "text-slate-300 hover:bg-slate-800")
            )
    ui.separator()


def _history_messages(messages: list[dict]) -> list[dict]:
    history = []
    for message in messages:
        if message["role"] == "user":
            history.append({"role": "user", "content": message["content"]})
        else:
            history.append(
                {"role": "assistant", "content": Answer.model_validate(message["answer"]).text}
            )
    return history


@ui.page("/")
async def chat_page() -> None:
    # app.storage.tab is only available once the client's websocket has
    # actually connected — accessing it any earlier raises RuntimeError.
    await ui.context.client.connected()

    ui.dark_mode(True)
    ui.page_title("Northstar Assistant")

    # Tab storage (not a plain local list) so the conversation and feedback
    # markers survive navigating to /evaluation and back — a local variable
    # would be recreated empty on every page load, unlike Streamlit's
    # session_state, which is shared across a multi-page app's pages.
    messages: list[dict] = nicegui_app.storage.tab.setdefault("messages", [])
    feedback_submitted: list[str] = nicegui_app.storage.tab.setdefault(
        "feedback_submitted", []
    )
    edit_open: set[str] = set()
    placeholder: ui.label | None = None

    def current_employee():
        return EMPLOYEES[employee_select.value]

    with ui.header().classes("items-center bg-slate-950 border-b border-slate-800 px-6 py-4"):
        with ui.row().classes("items-center gap-5"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                "flat round color=white size=lg"
            )
            ui.image("material/northstar-logo-256.png").classes(
                "w-20 h-20 sm:w-24 sm:h-24 rounded-2xl"
            )
            with ui.column().classes("gap-0"):
                ui.label("Northstar Internal Assistant").classes(
                    "text-3xl sm:text-4xl font-bold text-white leading-tight"
                )
                ui.label("Permission-aware company knowledge prototype").classes(
                    "text-base sm:text-lg text-slate-400 leading-tight"
                )

    with ui.left_drawer(value=True).classes("bg-slate-900 text-slate-200 gap-2 p-3") as drawer:
        render_nav("Assistant")
        ui.label("System status").classes("text-lg font-semibold")
        index_status = last_indexed_status()
        if index_status is None:
            ui.label("Semantic index: not yet built").classes("text-base text-slate-400")
        else:
            ui.label(
                f"Semantic index: {index_status['indexed_sources']} sources, "
                f"last synced {index_status['last_synced_at']}"
            ).classes("text-base text-slate-400")
        _, github_state = load_all_documents_with_github_status()
        ui.label(
            "GitHub source: local export + live repository"
            if github_state == "live"
            else "GitHub source: local export only (live unavailable or not configured)"
        ).classes("text-base text-slate-400")

        def do_resync() -> None:
            try:
                result = sync_index()
                ui.notify(
                    f"Synced: +{result['added']} added, ~{result['updated']} updated, "
                    f"-{result['removed']} removed ({result['total_indexed']} total)",
                    type="positive",
                )
            except Exception as error:  # surfaced to the user, never silently swallowed
                ui.notify(f"Sync failed: {error}", type="negative")

        ui.button("Resync index", on_click=do_resync).props("unelevated").classes(
            "w-fit text-lg mt-1"
        ).style(NEUTRAL_BUTTON_STYLE)

    with ui.column().classes("w-full max-w-4xl gap-4 px-6 py-4 text-lg"):
        with ui.card().classes("w-full bg-slate-800"):
            employee_select = ui.select(
                {key: emp.display_name for key, emp in EMPLOYEES.items()},
                label="Fictional employee profile",
                value=next(iter(EMPLOYEES)),
                on_change=lambda _: on_employee_change(),
            ).classes("w-full text-xl").props("label-color=slate-300 input-class=text-xl")

        pending_container = ui.column().classes("w-full gap-2")

        with ui.card().classes("w-full bg-slate-800 min-h-[240px]"):
            messages_container = ui.column().classes("w-full gap-3")
            # Populated further down, once render_answer/render_user_bubble
            # exist — either the persisted conversation (if resuming a tab
            # that already asked something) or the empty-state placeholder.

        with ui.row().classes("w-full items-center gap-3"):
            question_input = ui.input(
                placeholder="Ask about projects, customers, policies, or work items"
            ).classes("flex-grow text-xl").props("input-class=text-xl")
            question_input.on("keydown.enter", lambda: send())
            ui.button(icon="send", on_click=lambda: send()).props(
                "round color=primary size=lg"
            )
            role_badge = ui.label("").classes("px-3 py-1.5 rounded text-base font-semibold")

    def update_role_badge() -> None:
        role = current_employee().role
        role_badge.set_text(role)
        role_badge.classes(
            replace="px-3 py-1.5 rounded text-base font-semibold "
            + ROLE_BADGE_CLASSES.get(role, "bg-slate-500 text-white")
        )

    def on_employee_change() -> None:
        nonlocal placeholder
        messages.clear()
        feedback_submitted.clear()
        messages_container.clear()
        with messages_container:
            placeholder = ui.label(
                "No messages yet — ask a question below to get started."
            ).classes("text-lg text-slate-500 italic")
        update_role_badge()

    def refresh_pending() -> None:
        pending_container.clear()
        proposals = list_pending_proposals()
        with pending_container:
            with ui.expansion(f"Pending actions ({len(proposals)})", value=bool(proposals)).classes(
                "w-full bg-slate-800 rounded"
            ).props("header-class=text-lg"):
                if not proposals:
                    ui.label("No actions awaiting approval.").classes(
                        "text-base text-slate-500 italic"
                    )
                for proposal in proposals:
                    with ui.card().classes("w-full bg-slate-900 border border-slate-700 gap-1"):
                        ui.label(f"{proposal.action_type} → {proposal.destination}").classes(
                            "text-lg font-medium"
                        )
                        ui.label(
                            f"Requested by {proposal.requested_by} · {proposal.proposal_id}"
                        ).classes("text-base text-slate-500")
                        ui.code(json.dumps(proposal.payload, indent=2)).classes(
                            "text-sm w-full"
                        )
                        with ui.row().classes("gap-2"):
                            ui.button(
                                "Approve", on_click=lambda p=proposal: do_approve(p)
                            ).props("unelevated").style(POSITIVE_BUTTON_STYLE)
                            ui.button(
                                "Reject", on_click=lambda p=proposal: do_reject(p)
                            ).props("unelevated").style(NEGATIVE_BUTTON_STYLE)
                            ui.button(
                                "Edit", on_click=lambda p=proposal: toggle_edit(p)
                            ).props("unelevated").style(NEUTRAL_BUTTON_STYLE)
                        if proposal.proposal_id in edit_open:
                            payload_input = ui.textarea(
                                value=json.dumps(proposal.payload, indent=2)
                            ).classes("w-full font-mono text-sm")

                            def save_edit(pid=proposal.proposal_id, field=payload_input) -> None:
                                try:
                                    new_payload = json.loads(field.value)
                                    edit_action(pid, new_payload, current_employee())
                                    ui.notify("Proposal updated.", type="positive")
                                except (json.JSONDecodeError, ValueError) as error:
                                    ui.notify(str(error), type="negative")
                                finally:
                                    edit_open.discard(pid)
                                    refresh_pending()

                            ui.button("Save edit", on_click=save_edit).props(
                                "unelevated"
                            ).style(NEUTRAL_BUTTON_STYLE)

    def do_approve(proposal) -> None:
        try:
            approve_action(proposal.proposal_id, current_employee())
            execute_action(proposal.proposal_id, current_employee())
            ui.notify("Action approved and executed.", type="positive")
        except ValueError as error:
            ui.notify(str(error), type="negative")
        refresh_pending()

    def do_reject(proposal) -> None:
        try:
            reject_action(proposal.proposal_id, current_employee())
            ui.notify("Action rejected.", type="warning")
        except ValueError as error:
            ui.notify(str(error), type="negative")
        refresh_pending()

    def toggle_edit(proposal) -> None:
        if proposal.proposal_id in edit_open:
            edit_open.discard(proposal.proposal_id)
        else:
            edit_open.add(proposal.proposal_id)
        refresh_pending()

    def render_user_bubble(text: str) -> None:
        with messages_container:
            with ui.row().classes("w-full justify-end"):
                ui.label(text).classes(
                    "text-lg bg-blue-900/40 text-blue-100 rounded-lg px-3 py-2 max-w-[80%]"
                )

    def render_feedback(container, answer: Answer) -> None:
        if answer.answer_id in feedback_submitted:
            with container:
                ui.label("Feedback recorded — thank you.").classes(
                    "text-base text-slate-500 italic"
                )
            return

        def submit(rating: str, reason: str | None = None) -> None:
            record_feedback(
                Feedback(
                    answer_id=answer.answer_id,
                    rating=rating,
                    reason=reason,
                    retrieval_mode=answer.retrieval_mode,
                )
            )
            if answer.answer_id not in feedback_submitted:
                feedback_submitted.append(answer.answer_id)
            button_row.clear()
            reason_row.clear()
            with button_row:
                ui.label("Feedback recorded — thank you.").classes(
                    "text-base text-slate-500 italic"
                )

        with container:
            button_row = ui.row().classes("items-center gap-2")
            reason_row = ui.row().classes("items-center gap-2")
            reason_row.set_visibility(False)
        with button_row:
            ui.button("Useful", on_click=lambda: submit("useful")).props(
                "unelevated"
            ).style(POSITIVE_BUTTON_STYLE)
            ui.button(
                "Not useful", on_click=lambda: reason_row.set_visibility(True)
            ).props("unelevated").style(NEGATIVE_BUTTON_STYLE)
        with reason_row:
            reason_select = ui.select(
                {r: r.replace("_", " ") for r in get_args(FeedbackReason)},
                label="Reason (optional)",
            ).classes("w-48")
            ui.button(
                "Submit feedback",
                on_click=lambda: submit("not_useful", reason_select.value),
            ).props("unelevated").style(NEUTRAL_BUTTON_STYLE)

    def render_answer(container, answer: Answer) -> None:
        with container:
            color = STATUS_COLORS.get(answer.status, "slate")
            ui.label(f"Status: {answer.status} · Retrieval: {answer.retrieval_mode}").classes(
                f"text-base font-semibold text-{color}-300 bg-{color}-900/30 px-3 py-1.5 rounded w-fit"
            )
            ui.markdown(answer.text).classes("text-lg leading-relaxed")

            if answer.citations:
                with ui.expansion("Sources", icon="description").classes(
                    "w-full"
                ).props("header-class=text-lg"):
                    for citation in answer.citations:
                        date = (
                            citation.occurred_at.date().isoformat()
                            if citation.occurred_at
                            else "No date"
                        )
                        if citation.source_path.startswith("http"):
                            ui.markdown(
                                f"- **{citation.source_id}** — "
                                f"[{citation.title}]({citation.source_path}) "
                                f"(`{citation.source_type}`, {date})"
                            ).classes("text-lg")
                        else:
                            ui.markdown(
                                f"- **{citation.source_id}** — {citation.title} "
                                f"(`{citation.source_type}`, {date})"
                            ).classes("text-lg")
                            ui.label(citation.source_path).classes(
                                "text-base text-slate-500 pl-4"
                            )

            with ui.expansion("Tool trace", icon="terminal").classes(
                "w-full"
            ).props("header-class=text-lg"):
                if answer.trace:
                    for step in answer.trace:
                        ui.label(f"• {step}").classes("text-base text-slate-400")
                else:
                    ui.label("No tool activity recorded.").classes(
                        "text-base text-slate-500 italic"
                    )

            if answer.action_proposal:
                with ui.card().classes("w-full bg-amber-900/20 border border-amber-700"):
                    ui.label(
                        f"Action {answer.action_proposal.action_type} drafted for "
                        f"{answer.action_proposal.destination} — see \"Pending actions\" "
                        "above to approve or reject it. The agent cannot approve or "
                        "execute it itself."
                    ).classes("text-lg text-amber-200")
                    ui.code(json.dumps(answer.action_proposal.payload, indent=2)).classes(
                        "text-sm"
                    )
                refresh_pending()

            feedback_holder = ui.column().classes("w-full")
            render_feedback(feedback_holder, answer)

    async def send() -> None:
        nonlocal placeholder
        question = question_input.value.strip()
        if not question:
            return
        question_input.value = ""
        employee = current_employee()
        history = _history_messages(messages)
        messages.append({"role": "user", "content": question})

        if placeholder is not None:
            placeholder.delete()
            placeholder = None

        render_user_bubble(question)
        with messages_container:
            status_label = ui.label("Thinking...").classes(
                "text-lg text-slate-400 italic"
            )
            answer_slot = ui.column().classes("w-full gap-2")

        step_queue: queue.Queue[str] = queue.Queue()

        def poll_steps() -> None:
            try:
                while True:
                    status_label.set_text(step_queue.get_nowait())
            except queue.Empty:
                pass

        timer = ui.timer(0.2, poll_steps)
        try:
            answer = await run.io_bound(
                answer_with_agent,
                question,
                employee,
                conversation_history=history,
                on_step=step_queue.put_nowait,
            )
        finally:
            timer.cancel()
        status_label.delete()

        render_answer(answer_slot, answer)
        messages.append({"role": "assistant", "answer": answer.model_dump(mode="json")})

    update_role_badge()
    refresh_pending()

    if messages:
        for message in messages:
            if message["role"] == "user":
                render_user_bubble(message["content"])
            else:
                with messages_container:
                    answer_slot = ui.column().classes("w-full gap-2")
                render_answer(answer_slot, Answer.model_validate(message["answer"]))
    else:
        with messages_container:
            placeholder = ui.label(
                "No messages yet — ask a question below to get started."
            ).classes("text-lg text-slate-500 italic")


@ui.page("/evaluation")
def evaluation_page() -> None:
    ui.dark_mode(True)
    ui.page_title("Evaluation — Northstar Assistant")

    with ui.header().classes("items-center bg-slate-950 border-b border-slate-800 px-6 py-4"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
            "flat round color=white size=lg"
        )
        ui.label("Evaluation results").classes("text-2xl sm:text-3xl font-bold text-white ml-2")
        ui.link("← Back to assistant", "/").classes("text-base text-slate-400 ml-auto")

    with ui.left_drawer(value=True).classes("bg-slate-900 text-slate-200 gap-2 p-3") as drawer:
        render_nav("Evaluation")

    results_path = Path("data/generated/evaluation_results.json")
    with ui.column().classes("w-full max-w-5xl gap-4 px-6 py-4 text-lg"):
        if not results_path.exists():
            ui.label(
                "No results yet — run `uv run python -m company_assistant.evaluation.run` first."
            ).classes("text-lg text-amber-300")
            return

        data = json.loads(results_path.read_text(encoding="utf-8"))
        results = pd.DataFrame(data["results"])
        ui.label(
            f"Generated {data['generated_at']} — {data['cases_run']} cases, "
            f"{len(results)} result rows"
        ).classes("text-lg text-slate-400")

        ui.label("Pass / Partial / Fail / N/A by category").classes(
            "text-2xl font-semibold text-slate-100"
        )
        by_category = results.groupby(["category", "verdict"]).size().unstack(fill_value=0)
        for column in ("Pass", "Partial", "Fail", "N/A"):
            if column not in by_category.columns:
                by_category[column] = 0
        by_category = by_category[["Pass", "Partial", "Fail", "N/A"]].reset_index()
        ui.table(
            columns=[{"name": c, "label": c, "field": c} for c in by_category.columns],
            rows=by_category.to_dict("records"),
        ).classes("w-full")

        with ui.row().classes("w-full gap-4"):
            with ui.column().classes("flex-1"):
                ui.label("Expected-evidence coverage by variant").classes(
                    "text-2xl font-semibold text-slate-100"
                )
                with_expected = results[results["expected_source_ids"].map(len) > 0].copy()
                with_expected["coverage"] = with_expected["expected_found"].map(len) / (
                    with_expected["expected_source_ids"].map(len)
                )
                coverage = with_expected.groupby("variant")["coverage"].mean()
                ui.echart(
                    {
                        "xAxis": {"type": "category", "data": list(coverage.index)},
                        "yAxis": {"type": "value"},
                        "series": [
                            {"type": "bar", "data": [round(v, 3) for v in coverage.values]}
                        ],
                    }
                ).classes("w-full h-64")

            with ui.column().classes("flex-1"):
                ui.label("Mean latency by variant (ms)").classes(
                    "text-2xl font-semibold text-slate-100"
                )
                latency = results.groupby("variant")["latency_ms"].mean()
                ui.echart(
                    {
                        "xAxis": {"type": "category", "data": list(latency.index)},
                        "yAxis": {"type": "value"},
                        "series": [
                            {"type": "bar", "data": [round(v, 1) for v in latency.values]}
                        ],
                    }
                ).classes("w-full h-64")

        ui.label("Feedback").classes("text-2xl font-semibold text-slate-100")
        feedback_entries = list_feedback()
        if feedback_entries:
            useful = sum(1 for entry in feedback_entries if entry.rating == "useful")
            not_useful = len(feedback_entries) - useful
            with ui.row().classes("gap-8"):
                ui.label(f"Useful: {useful}").classes("text-lg")
                ui.label(f"Not useful: {not_useful}").classes("text-lg")
            feedback_df = pd.DataFrame(
                [entry.model_dump(mode="json") for entry in feedback_entries]
            )
            ui.table(
                columns=[{"name": c, "label": c, "field": c} for c in feedback_df.columns],
                rows=feedback_df.to_dict("records"),
            ).classes("w-full")
        else:
            ui.label(
                "No feedback recorded yet — use the chat page's Useful / Not useful buttons."
            ).classes("text-lg text-slate-500 italic")

        ui.label("Unresolved failures").classes("text-2xl font-semibold text-slate-100")
        unresolved = results[results["verdict"].isin(["Fail", "Partial"])][
            ["case_id", "variant", "verdict", "note"]
        ].sort_values(["case_id", "variant"])
        ui.table(
            columns=[{"name": c, "label": c, "field": c} for c in unresolved.columns],
            rows=unresolved.to_dict("records"),
        ).classes("w-full")


ui.run_with(app, mount_path="/", storage_secret=STORAGE_SECRET)
