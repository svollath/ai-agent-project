# Northstar Internal Assistant — single image shared by both interfaces.
# docker-compose.yml runs this image as two services (api, ui) with
# different commands; see that file for how each port is actually exposed.

FROM ghcr.io/astral-sh/uv:0.12.7 AS uv
FROM python:3.13-slim

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependencies first, cached separately from application code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Application code and the committed fixtures the app reads at import/call
# time. data/index, data/feedback, and data/generated are intentionally not
# copied here — they are runtime/local state (see .dockerignore) and are
# mounted as named volumes by docker-compose.yml instead.
COPY src/ src/
COPY app.py ./
COPY pages/ pages/
COPY material/ material/
COPY data/raw/ data/raw/
COPY data/database/company.db data/database/company.db
COPY data/evaluation/cases.json data/evaluation/cases.json

RUN uv sync --frozen

EXPOSE 8000 8501

# Overridden per-service by docker-compose.yml; kept as a sane default so
# `docker run` against this image alone still does something sensible.
CMD ["uv", "run", "uvicorn", "company_assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]
