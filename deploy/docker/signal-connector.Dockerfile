FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY connectors ./connectors
COPY scripts/run-signal-connector.py ./scripts/run-signal-connector.py

RUN python -m pip install --no-cache-dir .

USER 65532:65532

CMD ["python", "scripts/run-signal-connector.py"]
