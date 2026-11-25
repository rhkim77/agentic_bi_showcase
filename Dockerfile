FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_VERTEXAI=TRUE \
    GOOGLE_CLOUD_LOCATION=us-central1 \
    CYMBAL_STATE_DIR=/tmp/cymbal_agentic_bi_state

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "google-adk>=1.0.0" \
    "google-genai>=1.0.0" \
    "google-auth>=2.35.0" \
    "requests>=2.32.0" \
    "truststore>=0.10.0" \
    "certifi>=2024.8.30" \
    "pydantic>=2.9.0"

COPY agents/ ./agents/
COPY backend/ ./backend/
COPY benchmarks/ ./benchmarks/
COPY docs/ ./docs/

RUN useradd --create-home --uid 10001 archportal && \
    mkdir -p /tmp/cymbal_agentic_bi_state && \
    chown -R archportal:archportal /app /tmp/cymbal_agentic_bi_state

USER archportal
EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
