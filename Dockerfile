FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api,dev]"

# O repositório a ser analisado entra por volume em /repo; o índice fica em /data.
ENV LEGACYLENS_DB=/data/index.db LEGACYLENS_LOG=/data/telemetry.jsonl
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "legacylens.api:app", "--host", "0.0.0.0", "--port", "8000"]
