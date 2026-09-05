FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY config/freyja-channels.yaml ./config/freyja-channels.yaml
COPY certification ./certification
COPY connectors ./connectors
COPY src ./src
COPY scripts/run-freyja-channels-telegram-pilot.py ./scripts/run-freyja-channels-telegram-pilot.py
COPY scripts/run-freyja-channels-signal-pilot.py ./scripts/run-freyja-channels-signal-pilot.py

RUN python -m pip install --no-cache-dir .

USER 65532:65532

CMD ["python", "scripts/run-freyja-channels-telegram-pilot.py", "--dry-run"]
