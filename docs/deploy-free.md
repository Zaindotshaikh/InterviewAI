# Free teammate demo deploy

Goal: one shareable link that works like local, **$0/month** (free tiers only).

## Architecture (2 free pieces)

| Piece | Where | Cost |
|-------|--------|------|
| UI + API (root `Dockerfile`) | **Render** free Web Service | $0 (sleeps after ~15 min idle) |
| Voice agent (`agent/`) | **LiveKit Cloud** Build plan | $0 (cold start ~10–20s when idle) |
| LiveKit media | Your existing `*.livekit.cloud` project | already free Build |

Do **not** put the Python agent on Render free — background workers are paid there. LiveKit Cloud hosts the agent for free.

Teammate URL after deploy: `https://interviewai-web-xxxx.onrender.com/v2/test`  
(or `/v2/i/{token}` invite links)

## Limits to tell teammates

- First hit after idle: Render wake (~30–60s) + agent cold start (~10–20s). Open the link, wait, then start.
- LiveKit Build: ~1,000 agent minutes / month, max 5 concurrent sessions.
- Disk is ephemeral on free Render — old `server/data/*.json` sessions may vanish after sleep/redeploy. Fresh interviews still work.

## 1. Deploy web (Render)

1. Push this repo to GitHub (no `.env`, no secrets).
2. [Render](https://render.com) → New → Blueprint → select repo (`render.yaml`).
3. In the service **Environment**, paste values from your local `server/.env`:
   - `OPENAI_API_KEY`
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (same LiveKit Cloud project as local)
   - `V2_INTERNAL_SECRET` (must match agent)
   - `V2_AGENT_NAME=interview-v2`
   - `ELEVENLABS_API_KEY` / `SARVAM_API_KEY` / others you use locally
4. Set `CLIENT_ORIGIN` to the Render HTTPS URL once you know it, e.g.  
   `https://interviewai-web-xxxx.onrender.com`  
   (or leave unset — server allows all origins when unset).
5. Deploy. Check `https://YOUR-APP.onrender.com/api/health` → `{ "ok": true, ... }`.

## 2. Deploy agent (LiveKit Cloud)

Install CLI if needed: https://docs.livekit.io/home/cli/

```bash
cd agent
lk cloud auth          # link the same LiveKit project as local
lk agent create        # first time only — uses agent/Dockerfile
```

Set secrets to match local `agent/.env`, **except** backend URL:

| Secret | Value |
|--------|--------|
| `BACKEND_URL` | `https://YOUR-APP.onrender.com` (no trailing slash) |
| `V2_INTERNAL_SECRET` | **same** as Render |
| `V2_AGENT_NAME` | `interview-v2` |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | same project |
| `OPENAI_API_KEY` | same as local |
| Plus the rest you use locally | `TTS_PROVIDER`, `STT_PROVIDER`, `GPT_LIVE_*`, `ELEVENLABS_*`, `NOISE_PROVIDER`, Google TTS vars, etc. |

```bash
# Example — prefer LiveKit dashboard Secrets UI for bulk paste
lk agent update
lk agent deploy
```

If Google TTS needs a key file, upload the JSON contents as a LiveKit secret / file mount — ADC from your laptop will not exist in the cloud.

## 3. Smoke test

1. Open `https://YOUR-APP.onrender.com/v2/test` (wait for cold start).
2. Start a GPT-Live / default interview.
3. Confirm agent joins (LiveKit dashboard → rooms / agent logs: `lk agent logs`).

## Env parity checklist

Copy **names** from local; only change:

- Agent `BACKEND_URL` → public Render URL  
- Server `CLIENT_ORIGIN` → that same public URL (optional)  
- Never commit `.env`

## Updating

- Web: push to the connected branch → Render redeploys.
- Agent: `cd agent && lk agent deploy`

## If free tiers feel too sleepy

Next cheapest paid step is usually Render Starter (~$7) or LiveKit Ship (keeps agent warm) — not required for a small teammate test.
