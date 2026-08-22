FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git \
    && ln -sf /usr/local/bin/python /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY certification ./certification
COPY connectors ./connectors
COPY src ./src
COPY config ./config

RUN python -m pip install --no-cache-dir . pytest

USER 65532:65532

CMD ["uvicorn", "freyja.main:app", "--host", "0.0.0.0", "--port", "8000"]
