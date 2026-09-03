# Northstar Internal Assistant — k3s packaging experiment (NiceGUI + FastAPI,
# single process, single port). Fully separate from the root Dockerfile,
# which still packages the Streamlit + FastAPI two-process app.
#
# Build from the REPO ROOT (not from inside k3s-exp/), so this can COPY the
# shared src/ package and fixture data without duplicating them on disk:
#   docker buildx build --platform linux/amd64 -f k3s-exp/Dockerfile \
#     -t northstar-assistant-k3s-exp:latest --load .
# See k8s/README.md for the full build -> transfer -> import -> deploy flow.

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
# copied here — they are runtime/local state, mounted as PVCs by the k8s
# manifests instead (see k8s/deployment.yaml).
COPY src/ src/
COPY k3s-exp/app.py ./app.py
COPY material/ material/
COPY data/raw/ data/raw/
COPY data/database/company.db data/database/company.db
COPY data/evaluation/cases.json data/evaluation/cases.json

RUN uv sync --frozen

# Pre-download the local embedding model at build time so a fresh container
# never depends on runtime Hugging Face Hub reachability — matters for the
# k8s startup probe's timing budget (see k8s/deployment.yaml).
RUN uv run python -c "\
from langchain_huggingface import HuggingFaceEmbeddings; \
HuggingFaceEmbeddings(model_name='sentence-transformers/all-MiniLM-L6-v2')"

# Force fully offline Hugging Face usage from here on — the model above is
# already cached in this image, so nothing at runtime needs to reach
# huggingface.co. Set only after the download step (which needs the
# network) and applies to every way this image gets run (docker compose,
# k3s), not just one of them. Without this, huggingface_hub still makes an
# unauthenticated metadata request on every pod start (harmless, but a real
# network dependency this image is supposed to not have — see comment
# above — and it logs a rate-limit warning every time).
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8100

CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
