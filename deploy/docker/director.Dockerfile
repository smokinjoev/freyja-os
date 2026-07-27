FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN python -m pip install --no-cache-dir .

USER 65532:65532

CMD ["uvicorn", "freyja.main:app", "--host", "0.0.0.0", "--port", "8000"]
