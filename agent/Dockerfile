FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY config.py backend.py main.py ./
COPY interview ./interview
COPY providers ./providers
COPY eval ./eval
COPY tests ./tests

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV PROVIDER_MODE=openai
ENV V2_AGENT_NAME=interview-v2

CMD ["python", "main.py", "start"]
