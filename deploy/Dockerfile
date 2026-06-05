FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    MOCK_MODE=true \
    GROUNDING_PDQ=1 \
    GOOGLE_GENAI_USE_VERTEXAI=true \
    GOOGLE_CLOUD_PROJECT=gen-lang-client-0384080704 \
    GOOGLE_CLOUD_LOCATION=global

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r requirements.txt

COPY agents ./agents
COPY eval/cases ./eval/cases
COPY grounding ./grounding
COPY mcp_server ./mcp_server
COPY prompts ./prompts
COPY service ./service
COPY tools ./tools
COPY vertex_check ./vertex_check
COPY run_demo.py ./run_demo.py
COPY README.md ./README.md

USER appuser

CMD ["sh", "-c", "uvicorn service.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
