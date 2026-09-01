"""FastAPI boundary for the internal assistant application layer."""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from company_assistant.models import Answer, EmployeeContext, EmployeeRole
from company_assistant.service import answer_with_baseline

app = FastAPI(title="Northstar Internal Assistant", version="0.1.0")

EMPLOYEES = {
    "maya": EmployeeContext(
        employee_id="maya", display_name="Maya Chen", role="customer_success"
    ),
    "leo": EmployeeContext(
        employee_id="leo", display_name="Leo Martins", role="engineering"
    ),
    "priya": EmployeeContext(
        employee_id="priya", display_name="Priya Shah", role="people_operations"
    ),
    "omar": EmployeeContext(
        employee_id="omar", display_name="Omar Haddad", role="finance"
    ),
}


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    employee_id: str
    conversation_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    employee_roles: list[EmployeeRole]


@app.get("/health")
def health() -> HealthResponse:
    """Return a small readiness response without calling a model."""

    return HealthResponse(
        status="ok",
        employee_roles=[
            "customer_success",
            "engineering",
            "people_operations",
            "finance",
        ],
    )


@app.post("/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    """Run the baseline for one known fictional employee."""

    employee = EMPLOYEES.get(request.employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown employee profile.",
        )
    return answer_with_baseline(request.question, employee)
