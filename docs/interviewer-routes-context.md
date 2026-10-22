# Live interviewer routes

Context for the two public candidate join pages this repo ships and that are deployed on Render. Both are **in this repository** (not deploy-only). They are variants of the **v2 LiveKit interview**, not the older OpenAI Realtime browser session.

| | ElevenLabs interviewer | GPT-Live interviewer |
| --- | --- | --- |
| Deployed URL | https://interviewai-418h.onrender.com/elevenlabs-interviewer | https://interviewai-418h.onrender.com/gpt-live-interviewer |
| Local path | `/elevenlabs-interviewer` (Vite dev server, default `http://localhost:5173`) | `/gpt-live-interviewer` |
| Who it is for | Candidate self-join. No login, no invite token. | Same |
| React mount | `<V2TestPage ttsProvider="elevenlabs" />` | `<V2TestPage voiceProvider="gpt_live" />` |
| Voice path | v2 **cascade**: STT → Director/LLM → TTS, with TTS locked to ElevenLabs | v2 **full-duplex**: OpenAI GPT-Live owns speech in and speech out; Director steers by commentary |

The deployed HTML shell for both URLs is the same SPA (`title` InterviewAI, same `/assets/index-*.js`, `#root`). The rendered join screen matches `V2TestPage` when either prop is set: heading “Join your interview”, Staff Nurse screening copy, name, language, editable sample nurse resume, microphone preflight, DPDP consent, and “Join interview”.

TA users do **not** run these URLs. TA login, roles, and scorecards live on `/login`, `/dashboard`, `/roles/:roleId`, and `/candidates/:candidateId/scorecard`.

---

## Shared candidate flow

`client/src/App.tsx` registers both paths. `client/src/v2/V2TestPage.tsx` treats `ttsProvider === "elevenlabs"` and `voiceProvider === "gpt_live"` as the same **candidate join** UI (`candidateJoin`). The internal test page `/v2/test` (no provider prop) is a different screen: role dropdown, health JSON, and “Start v2 interview”.

Join sequence:

1. `GET /api/roles` — first role id is stored. The join form does **not** show a role picker. The heading uses that role’s title, or “Staff Nurse” until roles load.
2. Candidate sets name (required), language (default `hi-IN`), resume (prefilled sample nurse text, editable), microphone, and recording consent.
3. `POST /api/v2/interview/start` with `roleId`, `language`, `recordingConsent`, `candidateContext`, and either `ttsProvider: "elevenlabs"` or `voiceProvider: "gpt_live"`.
4. Server builds a v2 plan, stores the interview, creates a LiveKit room, and dispatches the agent named by `V2_AGENT_NAME` (default `interview-v2`). Room and token metadata carry `ttsProvider` / `voiceProvider`.
5. `LiveInterview` plus `useLiveKitInterview` joins the room with the returned LiveKit URL and token.
6. On end, the page calls `POST /api/v2/interview/:id/summary` and `GET /api/v2/interview/:id/transcript`, then shows `ScorecardView` and a transcript download. That scorecard stays in the browser. It is not written into the TA dashboard unless the separate invite route `/v2/i/:token` is used.

API prefix: `server/index.ts` mounts `server/v2/routes/interviewV2.ts` at `/api/v2/interview`. The agent reads the plan from the internal v2 API (`server/v2/routes/internalV2.ts`), which echoes `ttsProvider` and `voiceProvider`.

---

## `/elevenlabs-interviewer`

**Purpose.** Candidate A/B of the v2 cascade with ElevenLabs as the speaking voice. Clinical control stays in the Python Director and `InterviewFlow` (same nurse-screening blueprint as other v2 calls: screening facts, clinical probes, gates, scorecard).

**Stack.**

- Browser: React + LiveKit client (`client/src/v2/hooks/useLiveKitInterview.ts`, `client/src/v2/components/LiveInterview.tsx`).
- Server: Express start/summary/transcript. LiveKit room + agent dispatch in `server/v2/lib/livekit.ts`.
- Agent: `agent/main.py` `entrypoint`. Because `voiceProvider` is not `gpt_live`, it builds cascade STT, LLM, and TTS.
- TTS override: `_tts_provider_override` accepts `elevenlabs` (also `google`, `openai`, `sarvam`, `mock`). `build_tts(..., provider="elevenlabs")` in `agent/providers/factory.py` uses the LiveKit ElevenLabs plugin.
- Voice: `agent/providers/elevenlabs_voices.py`. Default in `agent/config.py` is one voice id for English and Indic (comments call it Sujata) so the speaker does not change mid-call. Model default `ELEVENLABS_MODEL` / `eleven_v4_turbo`.
- Expressiveness: when TTS is ElevenLabs, the agent locks that provider for the call (`_tts_locked_el`) and can run the expressiveness engine (`VOICE_EXPRESSIVENESS`) so tags are for TTS while scoring text stays clean. See `docs/voice-refactor.md`.
- STT is **not** chosen by this route. It follows the agent process: `STT_PROVIDER`, else `PROVIDER_MODE`. The checked-in agent env file sets `STT_PROVIDER=elevenlabs_scribe` (Scribe v2 realtime, word timestamps, medical keyterms, fallback `STT_SCRIBE_FALLBACK`, default `openai` / `gpt-live-transcribe`). `agent/.env.example` defaults `STT_PROVIDER=openai`. A worker started from the example file will speak with ElevenLabs on this URL and transcribe with OpenAI unless Scribe is turned on.
- LLM for spoken lines: `LLM_PROVIDER` / `LLM_MODEL` (example: OpenAI `gpt-4o-mini`). Turn analysis: `DIRECTOR_MODEL` and `CLINICAL_DIRECTOR_MODEL` (example: `gpt-4o`).
- Noise: `NOISE_PROVIDER` (`none`, `krisp`, `aicoustics`) on the cascade room input. Example file uses `krisp`.

If `ELEVENLABS_API_KEY` / `ELEVEN_API_KEY` is missing, `build_tts` logs a warning and falls back to OpenAI TTS. The route flag does not by itself guarantee an ElevenLabs voice.

---

## `/gpt-live-interviewer`

**Purpose.** Candidate A/B of full-duplex speech-to-speech. The same interview plan, blueprint, and Director still decide the next clinical move. The model speaks and listens; the agent does not run the cascade STT/TTS chain.

**Stack.**

- Same React join page and same `POST /api/v2/interview/start`, with `voiceProvider: "gpt_live"`.
- `agent/main.py` `entrypoint` calls `_run_gpt_live_session` when metadata `voiceProvider` is `gpt_live` (only that value is accepted).
- Model: LiveKit `livekit.plugins.openai.realtime.GPTLiveModel`, `delegation="client"`. Defaults in `agent/config.py`: `GPT_LIVE_MODEL=gpt-live-1`, `GPT_LIVE_VOICE=marin`. Optional `GPT_LIVE_VOICE_BY_LANG` and `GPT_LIVE_CUSTOM_VOICE_ID` (custom voice needs project access; empty means the stock voice name).
- Client delegation: `InterviewAgent._wire_gpt_live_delegation` listens for delegation and input transcripts, then `_gpt_live_append` sends Director commentary (`_gpt_live_commentary`) so the voice model follows Flow (including gates) instead of free-running.
- Session config event records `stt_provider` / `tts_provider` as `gpt_live_builtin` and `voice_expressiveness` as `gpt_live_native`. Cascade fillers and the ElevenLabs tag engine are not used on this path.
- Silero VAD is intentionally not attached; GPT-Live owns turn detection. Noise cancellation from `NOISE_PROVIDER` can still wrap room audio input.
- Needs `OPENAI_API_KEY` with GPT-Live access. This path does **not** use `REALTIME_MODEL` or the browser WebRTC client in `client/src/lib/realtime.ts`.

`/gpt-live-interviewer` does not pass `avatar`. Tavus is a separate route, `/avatar-interviewer`.

---

## How the two routes differ

| | ElevenLabs route | GPT-Live route |
| --- | --- | --- |
| Start flag | `ttsProvider: "elevenlabs"` | `voiceProvider: "gpt_live"` |
| Agent branch | Cascade `AgentSession` (STT + LLM + TTS) | `_run_gpt_live_session` / `GPTLiveModel` |
| Ears | Process-wide STT (`elevenlabs_scribe`, `openai`, `sarvam`, or `mock`) | Built into GPT-Live |
| Mouth | ElevenLabs TTS for this interview only | Built into GPT-Live (`marin` unless overridden) |
| Brain | Dialogue LLM plus Director JSON each turn | Same Director/Flow, injected as client-delegation commentary |
| Prosody | Expressiveness engine when TTS is ElevenLabs | Native model timing; cascade tags off |
| Join UI | Identical candidate form | Identical candidate form |

Both still share LiveKit, the v2 plan/blueprint, transcript storage, summary scorecard, language list, and the nurse-screening interview package under `agent/interview/`.

---

## Other interview pipelines

**v1 — OpenAI Realtime in the browser.** Candidate invite `/i/:token` → `CandidateInterviewFlow` → `SetupScreen` / `InterviewScreen` → `useRealtimeSession` → `POST /api/session` mints an ephemeral key (`REALTIME_MODEL`, default `gpt-realtime`, voice `REALTIME_VOICE`). Audio is browser WebRTC to OpenAI, not LiveKit. Scoring uses `/api/interview/:id/summary`. These two live routes do not call that stack.

**v2 — Indic / LiveKit cascade (default).** `/v2/test` and invite `/v2/i/:token` → `/v2/i/:token/thanks`. Same agent worker. Providers come from env (`PROVIDER_MODE`, `STT_PROVIDER`, `TTS_PROVIDER`, `LLM_PROVIDER`), including **Sarvam** when those are set to `sarvam` (`agent/providers/factory.py`, `agent/providers/sarvam_stt_custom.py`). The ElevenLabs URL only overrides TTS. The GPT-Live URL replaces the cascade entirely, so Sarvam STT/TTS/LLM are not on that call.

**Avatar.** `/avatar-interviewer` is `<V2TestPage avatar />` (Tavus). It is not either of these two URLs.

**Demo.** `/demo` is a separate scripted demo flow.

---

## Configuration (names only)

The server loads **`server/.env`** (`dotenv` in `server/index.ts`). The agent loads **`agent/.env`** via pydantic (`agent/config.py`). The repo-root `.env` is not what the v2 server or agent read. Do not commit secret values. Examples: `server/.env.example`, `agent/.env.example`, `.env.example`.

**Repo-root `.env` (v1-oriented names present):** `OPENAI_API_KEY`, `REALTIME_MODEL`, `CHAT_MODEL`, `PORT`, `COMPANY_NAME`, `TARGET_MINUTES`. No LiveKit or ElevenLabs names in that file. Client brand on the join page is hardcoded in `client/src/config/brand.ts` (`COMPANY_NAME` = Kreeda Labs), not this file.

**`server/.env` names present:** `OPENAI_API_KEY`, `REALTIME_MODEL`, `CHAT_MODEL`, `PORT`, `COMPANY_NAME`, `TARGET_MINUTES`, `REALTIME_VOICE`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `V2_AGENT_NAME`, `V2_INTERNAL_SECRET`, `V2_MAX_MINUTES`, `PROVIDER_MODE`, `SARVAM_API_KEY`, `STT_PROVIDER`, `TTS_PROVIDER`, `LLM_PROVIDER`, `LLM_MODEL`, `TAVUS_API_KEY`, `ELEVENLABS_API_KEY`.

Server uses LiveKit and OpenAI for start, plan, and summary. `STT_PROVIDER` / `TTS_PROVIDER` / `LLM_PROVIDER` on the server do not select the worker’s plugins; the **agent** process does. `SARVAM_API_KEY` and `TAVUS_API_KEY` on the server are for health/avatar-related checks, not the speech path of these two routes.

**`agent/.env` names present:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `BACKEND_URL`, `V2_INTERNAL_SECRET`, `V2_AGENT_NAME`, `V2_MAX_MINUTES`, `PROVIDER_MODE`, `STT_PROVIDER`, `STT_SCRIBE_FALLBACK`, `TTS_PROVIDER`, `TTS_FALLBACK_ON_ERROR`, `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `OPENAI_STT_MODEL`, `GPT_LIVE_MODEL`, `GPT_LIVE_VOICE`, `ELEVENLABS_API_KEY`, `ELEVEN_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_VOICE_ID_LOCAL`, `ELEVENLABS_MODEL`, `DIRECTOR_MODEL`, `CLINICAL_DIRECTOR_MODEL`, `NOISE_PROVIDER`, `VOICE_EXPRESSIVENESS`.

`STT_PROVIDER` in that agent file is `elevenlabs_scribe`. `SARVAM_API_KEY` is **not** set there.

**Needed for these two routes to actually speak**

- Both: matching `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `V2_AGENT_NAME` on server and agent; `BACKEND_URL` and `V2_INTERNAL_SECRET` so the worker can fetch the plan; a running agent worker.
- ElevenLabs route: `ELEVENLABS_API_KEY` or `ELEVEN_API_KEY`, plus `ELEVENLABS_VOICE_ID`, `ELEVENLABS_VOICE_ID_LOCAL`, `ELEVENLABS_MODEL`. STT/LLM keys for whatever `STT_PROVIDER` and `LLM_PROVIDER` are (`OPENAI_API_KEY` when those are OpenAI or when Scribe falls back).
- GPT-Live route: `OPENAI_API_KEY`, `GPT_LIVE_MODEL`, `GPT_LIVE_VOICE` (optional `GPT_LIVE_VOICE_BY_LANG`, `GPT_LIVE_CUSTOM_VOICE_ID`). Director still uses `OPENAI_API_KEY` with `DIRECTOR_MODEL` / `CLINICAL_DIRECTOR_MODEL`.

Optional, not set in the three env files above: `V2_RECORDING_ENABLED` and S3-style `AWS_*` names from `.env.example` (recording runs only when the candidate consents **and** recording is configured). `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CLOUD_PROJECT` matter if cascade TTS falls back to Google (`TTS_FALLBACK_ON_ERROR`).

Local API: Vite proxies `/api` to `http://localhost:3001` (`client/vite.config.ts`).

---

## Implemented vs missing (for these two routes)

**Implemented**

- Both React routes and the shared join → live → scorecard UI.
- Start API persists `ttsProvider` / `voiceProvider` and puts them on the LiveKit job.
- Agent branches: ElevenLabs TTS override on the cascade; GPT-Live session with client delegation.
- Scribe STT, expressiveness, Director, Flow, languages, transcript, and summary exist for the v2 pipeline.
- Deployed site serves both paths as the same client bundle.

**Gaps / limits**

- No invite token, no auth, and no TA “send link” that targets these two paths. Invite v2 is `/v2/i/:token` and does not set `ttsProvider` or `voiceProvider`, so an invite uses the agent’s default cascade.
- Role is not selectable. Join uses the first `/api/roles` entry. If that request fails, `roleId` stays empty and Join stays disabled.
- Resume on the form is a hardcoded sample nurse document, not a file upload.
- The ElevenLabs URL does not force Scribe. STT is worker-wide. The GPT-Live URL ignores `TTS_PROVIDER` and Sarvam.
- Missing ElevenLabs key silently falls back to OpenAI TTS. GPT-Live fails if the key or plugin cannot start `GPTLiveModel` (access to `gpt-live-1` is an account capability, not something the route can stub).
- Post-call scorecard is on the candidate page only. It does not appear on `/dashboard` for these anonymous starts.
- Health diagnostics (`GET /api/v2/interview/health`) are hidden on these two screens.
- Repo-root `.env` does not configure LiveKit, ElevenLabs, or GPT-Live. Running the server against only that file will not start these rooms.
- Recording, Google TTS fallback, and Sarvam are optional extras. They are not what distinguishes the two URLs.

---

## Key files

| Area | Path |
| --- | --- |
| Routes | `client/src/App.tsx` |
| Join / live / scorecard page | `client/src/v2/V2TestPage.tsx` |
| LiveKit browser session | `client/src/v2/hooks/useLiveKitInterview.ts`, `client/src/v2/components/LiveInterview.tsx` |
| Languages | `client/src/v2/components/LanguagePicker.tsx`, `server/v2/lib/types.ts` |
| Start / summary API | `server/v2/routes/interviewV2.ts` |
| Agent fetch of plan | `server/v2/routes/internalV2.ts` |
| LiveKit dispatch | `server/v2/lib/livekit.ts` |
| Agent entry + GPT-Live | `agent/main.py` (`entrypoint`, `_run_gpt_live_session`) |
| STT/TTS/LLM factory | `agent/providers/factory.py` |
| ElevenLabs voice pick | `agent/providers/elevenlabs_voices.py` |
| Settings | `agent/config.py` |
| Interview control | `agent/interview/flow.py`, `agent/interview/director.py`, `agent/interview/prompts.py` (`gpt_live_voice_instructions`) |
| v1 Realtime (other pipeline) | `client/src/hooks/useRealtimeSession.ts`, `client/src/lib/realtime.ts`, `server/routes/session.ts`, `client/src/screens/CandidateInterviewFlow.tsx` |
| v2 invite (other pipeline) | `client/src/v2/V2InviteFlow.tsx` |
| Related write-ups | `docs/apollo_nurse_screening_implementation.md`, `docs/voice-refactor.md` |

`docs/apollo_nurse_screening_implementation.md` describes the same two URLs with latency and voice-product claims. Where it disagrees with code, trust the route flags above: this URL pair shares one page, ElevenLabs is a **TTS override**, and Scribe is an **agent env** choice (`STT_PROVIDER`), not a second React route.
