# InterviewAI: Kreeda Labs TA Demo

Real-time voice AI interviewer with a Talent Acquisition portal.

## Quick start

```bash
cd server && bun install && bun run dev
cd client && bun install && bun run dev
```

- TA Portal: http://localhost:5173/login  
- Candidate invite links look like: http://localhost:5173/i/{token}
- **Indic v2 test page:** http://localhost:5173/v2/test

Set `COMPANY_NAME=Kreeda Labs` in `server/.env` (client brand constant in `client/src/config/brand.ts`).

## Routes

| Path | Audience |
|------|----------|
| `/login` | TA mock sign-in |
| `/dashboard` | TA overview |
| `/roles/:roleId` | Pipeline + invite / scorecard |
| `/candidates/:id/scorecard` | TA scorecard + shortlist/reject |
| `/i/:token` | Candidate invite landing (v1 OpenAI Realtime) |
| `/i/:token/setup` | Resume + mic + live interview (v1) |
| `/i/:token/thanks` | Candidate thank-you (no scorecard) |
| `/v2/test` | Indic pipeline test harness (LiveKit + Sarvam/OpenAI) |
| `/v2/i/:token` | Invite flow on Indic pipeline |
| `/v2/i/:token/thanks` | v2 thank-you |

## Architecture

- Mock TA state in React context (`TAStore`). Live completions update the pipeline in-memory
- `POST /api/session`: ephemeral Realtime key (v1)
- `POST /api/resume/parse` + `/api/interview/generate-questions` + `/api/interview/start` (v1)
- WebRTC Realtime interview room with amplitude-driven presence orb (v1)

### Indic voice interview v2 (parallel)

Does **not** replace v1. New stack:

- Browser ↔ LiveKit WebRTC
- Python agent (`agent/`) with pluggable STT/LLM/TTS (`PROVIDER_MODE=openai|sarvam|mock`)
- Sarvam Saaras (STT) + Bulbul (TTS) + optional Sarvam LLM when keys are set
- Agent-side noise isolation (`NOISE_PROVIDER=none|krisp|aicoustics`)
- Control plane: `POST /api/v2/interview/start`, agent callbacks under `/api/v2/internal/*`

#### Run v2 locally

1. Copy env vars from `.env.example` into `server/.env` and `agent/.env`.
2. Start LiveKit (dev):

```bash
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev
```

3. Server + client as usual.
4. Agent:

```bash
cd agent
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
python main.py dev
```

5. Open http://localhost:5173/v2/test

See `agent/README.md` for Sarvam / noise / deploy notes.
