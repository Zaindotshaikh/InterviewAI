# Voice layer refactor (InterviewAI v2)

**Status:** Phases 1–7 implemented for combined testing. Agent `.env` defaults to `STT_PROVIDER=elevenlabs_scribe` + `VOICE_EXPRESSIVENESS=engine`. Restart worker before testing.  
**Scope:** Human-sounding, fast voice on the **ElevenLabs TTS path**, without changing interview policy.  
**Order (Path X):** `0 → 1 (instrument + wire Scribe behind flag + baselines) → 4+6 → 3 → 2 (Scribe A/B polish) → 5 → 7`  
**Commits:** One commit per phase after approval.

---

## Decisions locked (product)

| # | Decision |
|---|----------|
| 1 | **Tone owner = A + empathy override.** Deterministic `move.kind → tone` outside Flow. Director empathy override = **optional schema field, default off**; timeout → kind default. |
| 2 | Expressiveness/tags/tone whitelist = **EL TTS only**. Chirp unchanged. Transcript hygiene both paths. Scribe STT shared when enabled. |
| 3 | Path X; **Phase 1 wires** `STT_PROVIDER=elevenlabs_scribe` (default `openai`) + OpenAI fallback + baselines for both STTs. |
| 4 | You run scripted baseline calls; we provide scripts/steps. |
| 5 | Tag whitelist start: six tags below; harness may drop/replace. Sighs/hmm/umm separate. Opening pause via `...`. |
| 6 | Ack fillers **cannot** use Director sentiment (filler runs before Director). Heuristics on STT text + previous-turn state, or **neutral-only**; empathy from LLM wording. |
| 7 | Headline metric = **TTFA from VAD end of speech**; also persist **confirm-to-first-audio**. |
| 8 | Transcript `text` = post-processed string **sent to TTS**; barge-in → spoken portion + `interrupted=true`; scoring reads `text`. |
| 9 | Native-speaker review required for per-language umm/sigh/filler forms before Phase 4 merge; unreviewed langs fall back to hi/en. |

**Non-negotiables:** Do not change `InterviewFlow` stages, gates, retry/persuasion, close conditions, or Move **kinds**. Voice LLM = wording only; Flow = what to ask; Director = analysis (+ optional empathy tone field). Env flags; old = default/fallback. Male-candidate grammar = one config point (unchanged).

---

## Phase 0 — Confirm / correct current facts

| Claim | Verdict | Notes |
|---|---|---|
| Tags are LLM-generated via `ELEVENLABS_EXPRESSIVE_RULES` | **Confirmed** (EL) | Also opening seed tags. |
| `Disfluency` on EL only normalizes um/umm | **Confirmed** | No Chirp `[pause]` on EL. |
| Tags stored in transcripts | **Confirmed** | No strip today; Phase 6 fixes. |
| Fillers = fixed pre-rendered PCM | **Confirmed** | Before Director. |
| `preemptive_generation` off | **Confirmed** | |
| Hook injects directive + runs Director | **Confirmed** | Order: filler → `director.decide` → CONTROLLER DIRECTIVE. |
| STT `gpt-live-transcribe` | **Confirmed** default | Phase 1 adds opt-in Scribe. |
| Adaptive interruption + no OpenAI alignment | **Confirmed** | Scribe `include_timestamps` to be measured. |
| LiveKit Cloud | **Confirmed** | |

**Scribe (Phase 1 — verified in code):** Plugin 1.8.5 `elevenlabs.STT(model=scribe_v2_realtime, include_timestamps=True)` builds successfully. Capabilities: `streaming=True`, **`aligned_transcript="word"`**. No custom websocket needed. Whether Agents adaptive interruption **consumes** those alignments at runtime must be confirmed from `voice.session_config` / live logs during your Scribe baseline (`stt_aligned_transcript` + barge-in behavior). OpenAI STT remains default; set `STT_PROVIDER=elevenlabs_scribe` for A/B.

---

## Architecture after refactor (target)

```
Candidate audio
    → STT (openai | elevenlabs_scribe)
    → [Phase 3 opt] early filler on VAD silence + interim (cancel if speech resumes)
    → on_user_turn_completed
         → ack filler (neutral / STT+prior-state heuristics — NOT Director)
         → Director.decide (+ optional empathyTone field, default off)
         → Flow.apply → Move(kind, directive)  [UNCHANGED]
         → tone = kind_map[kind] or empathyTone if enabled
         → CONTROLLER DIRECTIVE
    → Voice LLM → plain text
    → tts_node engine [EL, flag] → ≤1 tag, pauses, triggers
    → TTS
    → persist text (= TTS input) + llmText; interrupted=true on barge-in
```

---

## Phase plan

### Phase 1 — Instrument + wire Scribe (this commit)

- Per-turn latency events; headline **ttfa_vad_ms** (VAD end → first audio); also **ttfa_confirm_ms** (turn confirmed → first audio).
- `python -m eval.latency_report --interview <id>`
- `STT_PROVIDER=elevenlabs_scribe|openai` (default openai); OpenAI fallback on Scribe connect failure.
- Log whether word timestamps / aligned transcripts reach the session; log configured interruption mode.
- Baseline steps: OpenAI STT × (hi + mr noise); Scribe STT × same scripts.

### Phase 2 — Scribe A/B polish

Quality tuning, keyterm limits, promote default only after A/B. (Wiring already in Phase 1.)

### Phase 3 — Latency

Targets: TTFA-from-VAD p50 ≤ 1.2s, p95 ≤ 2.0s; filler start ≤ 300–500ms when played.

Options to measure:

1. Faster/smaller director + shorter timeout → heuristic earlier.  
2. Director on interim transcripts (invalidate if final differs).  
3. Keep filler-first; overlap director under filler.  
4. **Early filler on VAD silence + interim transcript; cancel if candidate resumes; measure false-start rate.**  
5. Preemptive generation only if directive injection can coexist.

### Phase 4 — Expressiveness (EL) + Phase 6 transcript hygiene

**Ack fillers:** 4–6 variants/language; **neutral vs empathetic buckets chosen from STT-text heuristics + previous-turn state** (or neutral-only). **Not** Director sentiment. Empathy in LLM wording / optional `empathyTone` for **TTS tone tag only** when that schema field is on.

**Native-speaker review:** mark languages reviewed in config/docs; unreviewed → fall back to hi/en forms. Block Phase 4 merge until hi + mr + en reviewed (minimum).

**Listening harness:** 20 lines/tone → `agent/eval/audio_ab/`; check tags **not read aloud**; compare EL voice_settings after verifying which fields `eleven_v4_turbo` supports.

**Transcript (Phase 6 detail):** `text` = post-processed string actually sent to TTS (store per turn). `llmText` = raw LLM. Barge-in: persist spoken portion + `interrupted=true`. Server scoring/summary reads `text`. Strip tags from chat history fed back to the LLM.

### Phase 5 — Turns / interruptions

Raise `min_words` if adaptive not truly active; tune endpointing; cough/backchannel tests.

### Phase 7 — Robustness

EL TTS → Chirp fallback; Scribe → OpenAI; male grammar single touchpoint.

---

## Env flags and rollback

| Flag | Phase | Default | Rollback |
|---|---|---|---|
| `VOICE_LATENCY_LOG` | 1 | `true` (additive) | `false` |
| `STT_PROVIDER` | 1 | `openai` | keep `openai` |
| `STT_SCRIBE_FALLBACK` | 1 | `openai` | n/a |
| `DIRECTOR_EMPATHY_TONE` | 4 | `false` | `false` |
| `VOICE_EXPRESSIVENESS` | 4 | `legacy` | `legacy` |
| `VOICE_TRANSCRIPT_SPLIT` | 6 | `false` until ready | `false` |
| … | | | see prior table for TTFA targets, rates, etc. |

**Restart worker after every `.env` / agent code change.**

---

## Baseline steps (you run)

### OpenAI STT baseline (default)

1. `STT_PROVIDER=openai`, `VOICE_LATENCY_LOG=true`, restart agent.  
2. `/elevenlabs-interviewer` — Hindi ≥10 turns, quiet, scripted answers → note `interviewId`.  
3. Same script — Marathi ≥10 turns with background noise → note id.  
4. `cd agent && .\.venv\Scripts\python.exe -m eval.latency_report --interview <id> --data ../server/data`

### Scribe baseline (compare same answers)

5. `STT_PROVIDER=elevenlabs_scribe`, restart agent.  
6. Repeat the same two scripted calls.  
7. Run latency_report on both Scribe ids.  
8. Compare STT quality + TTFA + whether `voice.session_config` / agent logs show `stt_aligned_transcript` as `"word"` (Scribe) vs false (OpenAI).

---

## Phase 1 deliverables checklist

- [x] Doc amendments  
- [x] Latency tracker + persist `turn.latency` / `turn.latency_summary`  
- [x] `python -m eval.latency_report --interview <id>`  
- [x] `elevenlabs_scribe` STT + OpenAI fallback  
- [x] `voice.session_config` logs `stt_aligned_transcript` + interruption mode  
- [x] Commit Phase 1  

### Phase 1 files

- `agent/interview/latency.py`, `agent/eval/latency_report.py`, `agent/tests/test_latency.py`
- `agent/main.py`, `agent/config.py`, `agent/providers/__init__.py`, `agent/.env.example`
- `docs/voice-refactor.md`

---

## Assumptions still open

1. Whether Scribe word alignments are actually used by adaptive interruption at runtime (capability is `"word"`; live confirm during baseline).  
2. Whether `first_audio` via `agent_state_changed→speaking` matches perceived playout (vs TTS TTFB).  
3. Which `VoiceSettings` fields `eleven_v4_turbo` dialogue API accepts (harness Phase 4).  
4. Native-speaker review status per language (Phase 4 gate).
