FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "pydantic>=2.6.0"
COPY mock_services.py /app/
EXPOSE 9000
CMD ["uvicorn", "mock_services:app", "--host", "0.0.0.0", "--port", "9000"]
