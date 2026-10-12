# LiveKit Cloud deploy (ap-south / Mumbai)

1. Create a LiveKit Cloud project and note URL, API key, secret.
2. Set secrets in your host / Cloud agent env (see `agent/.env.example`).
3. From `agent/`:

```bash
lk cloud auth
lk agent create --region ap-south
lk agent deploy
```

Or build the Docker image:

```bash
docker build -t interviewai-agent-v2 ./agent
docker run --env-file ./agent/.env interviewai-agent-v2
```

Pin agent compute near India users (`ap-south`). Use `PROVIDER_MODE=sarvam` with `SARVAM_API_KEY` for production Indic accuracy.
