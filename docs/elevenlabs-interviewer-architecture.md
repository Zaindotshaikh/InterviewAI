# ElevenLabs interviewer — implementation brief

**Route:** `/elevenlabs-interviewer`  
**Deployed:** `https://interviewai-418h.onrender.com/elevenlabs-interviewer`  
**Purpose of this doc:** Short architecture + flow for external validation (e.g. Claude). Reflects current code, not aspirational design.

**POC rules baked into this path**

- Demo / scorecard feedback lives on this route (not on `/gpt-live-interviewer` or v1 `/i/*`).
- **Director + InterviewFlow** choose the next move. Scribe, the chat LLM, and ElevenLabs only speak — they do not invent screening policy.
- **Language** is chosen on the join screen (`LanguagePicker`). No spoken language question; no “detect language from hello” in Phase 1.

---

## 1. Architecture (one picture)

```text
Browser (V2TestPage)
    │  POST /api/v2/interview/start  { language, ttsProvider: "elevenlabs", … }
    ▼
Render web (Bun API + SPA)
    │  room + AgentDispatch + candidate LiveKit token
    │  plan + nursing blueprint stored; agent fetches via HMAC internal API
    ▼
LiveKit Cloud room (ap-south)
    │
    ▼
Python agent worker (interview-v2)  ── CASCADE path ──
    STT: ElevenLabs Scribe (realtime)
    VAD / turn: Silero + LiveKit turn handling (+ listen floor)
    Noise: Krisp BVC (required when configured)
    Brain: TurnAnalyzer → InterviewFlow → Director glue
    Reply LLM: paraphrases CONTROLLER DIRECTIVE only
    TTS: ElevenLabs (locked; no Chirp fallback on this route)
```

**Not this route:** `/gpt-live-interviewer` uses `voiceProvider: "gpt_live"` (full-duplex model, no cascade STT/TTS). Same Flow/Director brain, different voice pipe.

---

## 2. End-to-end flow

1. **Join** — Candidate picks language, name, optional resume; mic preflight; consent.
2. **Start** — Server builds interview id, `roomName = interview-v2-{id}`, loads `nursing.json` blueprint, `buildInterviewPlan()`, stores session, creates LiveKit room, **dispatches** agent `interview-v2` with metadata `{ interviewId, ttsProvider: "elevenlabs" }`, returns `{ url, token }`.
3. **Connect** — Client `useLiveKitInterview` joins room; mic: echo cancel on, browser noise suppression off (agent Krisp owns NC), AGC on.
4. **Agent boot** — Worker loads plan via `GET /api/v2/internal/interviews/:id/plan` (HMAC). Builds cascade session: Scribe + LLM + ElevenLabs TTS. Fail-closed if Scribe/EL/Krisp cannot start.
5. **Opening** — Mic gated until greeting finishes; then listen floor arms.
6. **Each turn (cascade)**  
   - Scribe final transcript → Director  
   - TurnAnalyzer → structured `TurnAnalysis` (slots, yes/no, care, intent)  
   - `InterviewFlow.apply` → `Move` (`directive`, optional `verbatim`)  
   - Chat LLM sees **CONTROLLER DIRECTIVE** and speaks 1–2 short sentences  
   - Expressiveness / TTS node → ElevenLabs audio  
7. **Screening then clinical then close** — Flow owns stage; blueprint limits time and probes. Care items (e.g. diaper) can gate.
8. **End** — Client fetches summary + transcript → `ScorecardView` (server-side classification; not live voice policy).
9. **Rejoin** — Same interview token with `dispatchAgent: false` so a second agent is not summoned.

---

## 3. Brain vs voice (responsibility split)

| Layer | Owns | Must not |
|-------|------|----------|
| **InterviewFlow** (`agent/interview/flow.py`) | Stages, focus, slots, confirmations, care gates, time/attempt limits, next `Move` | Speak audio |
| **TurnAnalyzer** (`analysis.py`) | Parse one utterance into slots / confirm / care / intent | Advance stage alone |
| **Director** (`director.py`) | Wire transcript → analyze → `flow.apply`; optional tone overlay | LiveKit / TTS |
| **Cascade voice** (`main.py` + providers) | STT in, directive-conditioned LLM out, TTS | Invent next screening question or skip gates |

**Design intent:** The voice model is a mouth. The Flow is the interviewer policy.

---

## 4. STT / TTS / turns (cascade on this route)

| Piece | Implementation |
|-------|----------------|
| **STT** | ElevenLabs Scribe realtime (`STT_PROVIDER=elevenlabs_scribe`); language hints from join language; plan keyterms; word timestamps; server VAD commits. |
| **TTS** | ElevenLabs via job `ttsProvider`; model from env (e.g. turbo). **`_tts_locked_el`:** no mid-call fallback to Google Chirp. |
| **Noise** | Krisp BVC on inbound when `NOISE_PROVIDER=krisp`; missing BVC → refuse session. |
| **Turns** | Silero VAD + LiveKit turn handling / interruption settings; `ListenFloor` commits when speech settles after greeting. |
| **Fillers** | Short thinking audio via `FillerPlayer` / early filler — not counted as the next policy question. |

---

## 5. Screening design (high signal)

Blueprint: `server/v2/lib/blueprints/nursing.json` (city → phone → qualification/year → height/weight → experience → care → clinical areas).

- **Phone** — Capture → **verbatim** digit read-back (`phone_confirm_line`) → yes/no. Stored digits via `store_phone` / normalize; **confirm only if** `valid_indian_mobile` (10 digits, starts 6–9). Deny / incorrect clears and **re-asks** (must not advance). Invalid “yes” → clear + invalid line; repeated false agrees → `unknown`.
- **Height / weight** — Either order; feet/inches or cm; joint **body confirm** in the unit they used for height when possible; slots stored as cm/kg.
- **Language** — Join picker only; drives Scribe hints, TTS voice map, and confirm-line locale strings.

Clinical depth (probe / clarify / challenge) is Flow-capped by blueprint limits, not an open questionnaire.

---

## 6. Guardrails (short list)

| Guard | Behavior |
|-------|----------|
| Fail-closed AV | No Scribe / no EL key / no Krisp when required → disconnect before greet |
| EL TTS lock | No Chirp fallback on this route |
| Phone confirm | Valid Indian mobile only; deny never auto-confirms |
| Verbatim moves | Phone ask/confirm lines are fixed speech, not free LLM invent |
| Slot normalize | Kind-based validation (phone, height, weight, year, city plausibility) |
| Unclear / junk | Noise filters, ask-repeat / attempt caps from blueprint |
| Directive contract | System prompt + controller directive; jailbreak / salary promises resisted in prompts |
| Rejoin | No second agent dispatch |

---

## 7. Key files

**Client:** `App.tsx`, `v2/V2TestPage.tsx`, `v2/hooks/useLiveKitInterview.ts`, `v2/components/{LanguagePicker,LiveInterview,PreflightCheck,ScorecardView}.tsx`, `v2/rejoin.ts`

**Server:** `v2/routes/interviewV2.ts`, `v2/routes/internalV2.ts`, `v2/lib/{livekit,planBuilder,blueprint,v2Store,classification}.ts`, `v2/lib/blueprints/nursing.json`

**Agent:** `main.py`, `backend.py`, `config.py`, `providers/factory.py`, `interview/{director,flow,analysis,phone_speech,normalize,prompts,listen,early_filler,expressiveness}.py`

**Tests (behavior locked):** `agent/tests/test_flow.py`, `test_phone_speech.py`, `test_normalize_blueprint.py`

---

## 8. What to validate externally

1. Is the **brain/voice split** sound for a controllable screening agent?  
2. Are **phone / body confirm** gates strong enough for voice STT noise?  
3. Is **fail-closed** on Scribe/EL/Krisp the right ops tradeoff for a demo?  
4. Anything missing for **multilingual** (picker-driven) that should stay out of the TTS model?

Related longer docs: `docs/voice-poc-approach.md`, `docs/poc-implementation-plan.md`, `docs/phase-1-tracker.md`, `docs/interviewer-routes-context.md`.
