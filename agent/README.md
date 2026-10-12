# InterviewAI agent v2

Python LiveKit agent for the Indic interview pipeline.

## Setup

```bash
cd agent
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -e ".[dev]"
```

Copy env from `../server/.env` or set:

```
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
BACKEND_URL=http://127.0.0.1:3001
V2_INTERNAL_SECRET=dev-v2-internal-secret-change-me
PROVIDER_MODE=openai
OPENAI_API_KEY=...
# SARVAM_API_KEY=...   # when PROVIDER_MODE=sarvam
# NOISE_PROVIDER=none|krisp|aicoustics
```

## Run (dev)

Terminal A — LiveKit server (optional local):

```bash
# Docker:
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev
```

Terminal B — agent:

```bash
python main.py dev
```

## Tests

```bash
pytest
```
