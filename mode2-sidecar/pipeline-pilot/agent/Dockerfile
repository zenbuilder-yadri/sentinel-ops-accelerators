# ───────────────────────────────────────────────────────────────────────
# PipelinePilot agent — vanilla LangGraph image. ZERO governance awareness.
#
# Steering comes from a single env-var (HTTP_PROXY) set by docker-compose,
# which routes all outbound httpx traffic through a separate sidecar.
# ───────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy agent source.
COPY pilot.py run.py scenarios.py /app/

EXPOSE 8090

CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8090"]
