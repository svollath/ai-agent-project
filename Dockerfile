# syntax=docker/dockerfile:1
# Phase 9 packaging: two runtime processes (Streamlit + FastAPI) built from
# one image. See deliverables/DECISIONS.md ("Phase 9: Container packaging")
# for why the image looks like this.

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# Install dependencies first, from the lockfile alone, so this layer is
# cached independent of source changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Now install the project itself (respects .dockerignore: raw fixtures and
# the reproducible company.db come in, generated/gitignored data does not).
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Pre-download the embedding model so semantic/hybrid retrieval never needs
# network access at request time (decision 3 in DECISIONS.md).
RUN uv run python -c "from langchain_huggingface import HuggingFaceEmbeddings; HuggingFaceEmbeddings(model_name='sentence-transformers/all-MiniLM-L6-v2')" \
    && chmod -R a+rX /opt/hf-cache


FROM python:3.13-slim

RUN groupadd -r app --gid 1000 \
    && useradd -r -g app --uid 1000 --create-home appuser

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder --chown=appuser:app /opt/hf-cache /opt/hf-cache
COPY --from=builder --chown=appuser:app /app /app

USER appuser

EXPOSE 8501 8000

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
