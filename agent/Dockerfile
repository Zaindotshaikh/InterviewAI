FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY config.py backend.py main.py ./
COPY interview ./interview
COPY providers ./providers

# pyproject declares README + eval package; both are omitted by .dockerignore
RUN printf '# interviewai-agent-v2\n' > README.md \
    && mkdir -p eval \
    && printf '' > eval/__init__.py \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV PROVIDER_MODE=openai
ENV V2_AGENT_NAME=interview-v2

CMD ["python", "main.py", "start"]
