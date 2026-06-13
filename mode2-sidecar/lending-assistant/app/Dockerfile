# ───────────────────────────────────────────────────────────────────────────
# LendingAssistant agent — vanilla LangGraph image. ZERO governance awareness.
# BYO-image: this is exactly the Dockerfile a customer already ships. The deploy
# tooling does not modify it — the proxy is added alongside at deploy time.
# ───────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY tools.py agent_core.py server.py /app/

EXPOSE 8090
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
