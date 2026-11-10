FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data/snapshot ./data/snapshot
COPY data/contracts ./data/contracts

RUN pip install --no-cache-dir duckdb pyarrow pandas pyyaml
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "hbp.pipeline", "--light"]
