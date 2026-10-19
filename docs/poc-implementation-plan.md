# Voice POC implementation plan

**Date:** 19 October 2026  
**Decision source:** `docs/voice-poc-approach.md`  
**Demo surface:** `/elevenlabs-interviewer` only  
**This file is the execution plan.** It does not change the decision note, the client requirements, or the architecture note.

The POC cracks the voice on one LiveKit cascade, in every major language the product already claims, and keeps the existing brain running so a call can happen. Improving the brain waits until this voice work has produced feedback. A face is out. GPT-Live is not a feedback surface.

---

## 1. POC goal and non-goals

### Goal

One join URL a tester can break and score, in each major language.

- The tester can start a call in each language below, hear an Indian-accent English voice or a matching Indian-language voice, and have Scribe accept that language.
- The call does not invent an answer it did not hear. One persona per language. No voice cloning.
- InterviewFlow still chooses the move. The dialogue model only says it. That brain already runs so the call can proceed. Tuning policy, the diaper-care gate, escalation, adaptive clinical follow-ups, and classification is a later phase, after this voice work produces feedback.
- After the call, the team has the interview id, the transcript, and a filled feedback sheet. Brain-quality scoring is not a Phase 1 exit.

**Voice, including the language set, is what this POC has to prove.** The brain is already implemented and unit-tested. Phase 1 does not replace it and does not retune it.

### In scope

| Item | Where it lives |
| --- | --- |
| Demo URL | `client/src/App.tsx` route `/elevenlabs-interviewer` → `V2TestPage` with `ttsProvider="elevenlabs"` |
| Transport | Existing LiveKit room and the v2 agent worker (`V2_AGENT_NAME`, default `interview-v2`) |
| Ears | Worker `STT_PROVIDER=elevenlabs_scribe` (Scribe v2 Realtime). The URL does not select STT. Each join passes an explicit language hint (section 3.1), not auto-detect |
| Mouth | ElevenLabs `eleven_v4_turbo` on this route (`ttsProvider: "elevenlabs"`). One persona per language via `ELEVENLABS_VOICE_BY_LANG`. OpenAI TTS (`gpt-4o-mini-tts`, voice `alloy`) is the explicit fallback when a language station fails ElevenLabs, not a second demo |
| Languages | English (Indian accent) `en-IN`, Hindi `hi-IN`, Telugu `te-IN`, Tamil `ta-IN`, Kannada `kn-IN`, Malayalam `ml-IN`, Bengali `bn-IN`, Marathi `mr-IN`, Gujarati `gu-IN`, Punjabi `pa-IN`, Odia `od-IN`. Source: `SUPPORTED_LANGUAGES` in `server/v2/lib/types.ts` and `PROFILES` in `agent/interview/language.py` |
| Noise | Krisp BVC on the agent. Browser noise suppression stays off on the published mic |
| Turns | LiveKit VAD + turn detector + adaptive interruption. Preemptive generation stays off |
| Brain | `Director.decide` + `InterviewFlow`. Unchanged policy, including two diaper-care persuasions then stop |
| State | Persisted `FlowState`. Rejoin the **same** interview inside 120 seconds |
| Evidence | Transcript, scorecard on the candidate page, agent log lines, `GET /api/v2/interview/:id` controller flow |

### Non-goals

Do not build or demo these in this POC:

- `/gpt-live-interviewer` as the place language, policy, or clinical feedback is collected
- Retuning the brain in this phase: diaper-care gate, escalation, adaptive clinical follow-ups, classification, or “why this question” instrumentation. The existing `Director.decide` path still runs
- Sarvam as the default ears or mouth (fallback only after both Scribe and OpenAI STT fail a language station)
- ElevenLabs Agents / Workflows, Sarvam hosted voice agents, Pipecat Flows, v1 browser Realtime (`/i/:token`, `REALTIME_MODEL`)
- Avatar / Tavus, including wiring `TAVUS_*` onto this route
- Voice cloning, a formal multi-clip blind listen, pre-rendered greetings, a golden audio set. A short listen to pick each language’s existing ElevenLabs voice id is in Phase 1
- A new orchestrator, a speech-arbiter rewrite, per-question endpointing as a new subsystem, Pipecat Smart Turn, indic-smart-turn
- A streaming output-guard rewrite. Listen for salary or selection promises. Build a guard only if the demo script produces one
- Scribe “no verbatim” or entity redaction
- TA dashboard wiring, unless an empty role list actually blocks Join (Phase 3)
- Live backchannels (“mm-hmm” while the candidate is still talking)

Avatar stays deferred even though `docs/client-requirements.md` section 8 lists a face as a readiness gap. That disagreement is recorded at the end of this plan. This POC follows the voice decision: presence orb only.

---

## 2. Phases

Three phases, in dependency order. Do not start a phase until the previous exit criteria are true.

### Phase 1 — Reliable cascade and language voices

Make `/elevenlabs-interviewer` trustworthy enough that the team can test voice in every major language the product already claims.

- Confirm the worker that serves the URL, not the example-file defaults.
- ElevenLabs `eleven_v4_turbo` out, one persona per language. Scribe v2 in, with that join language as the hint. Krisp BVC. Adaptive turn-taking.
- Unclear audio becomes please-repeat, not a guessed fact.
- Rejoin the same interview within 120 seconds after a refresh.
- A tester can start a call in each language in the table above and hear the mapped voice. STT accepts that language.
- A fixed Phase 1 script and a feedback sheet.

The existing brain runs so the next question can be asked. Phase 1 does not score diaper-care, clinical probes, contradictions, or tier quality, and it does not retune them.

**Exit:** Calls on `/elevenlabs-interviewer` log Scribe v2 Realtime, `eleven_v4_turbo`, and “Krisp BVC”. English is an Indian accent; each Indian language uses its mapped persona (voice id recorded in the tracker, not invented here). A mumble produces `ask_repeat` and does not store an invented fact. A refresh plus Rejoin within 120 seconds repeats the last question on the same interview id. The dry run has live calls in English (Indian accent), Hindi, and one South Indian language (Telugu), and the other languages are wired to a voice id and a Scribe hint even if the team only spot-checks them. The Phase 1 feedback sheet has a row for every Phase 1 station.

### Phase 2 — Brain feedback loop

Starts only after Phase 1 voice and language calls have produced feedback. Keep Flow and Director as they are. Make the next-question decision visible to a reviewer who is not tailing a terminal. This is the phase that may change how a move is shown. It is not a rewrite of policy.

Stations on the same cascade:

- Diaper care: refuse, hear the explanation, refuse again. Clinical must not start. Salary and “am I selected?” are deflected.
- Partial clinical answer (only if a separate call passes the gate): a thin answer such as “I check vitals” with no number and no action. The next move probes the gap.
- One contradiction against something already stored (city, years, or ward).

**Exit:** For each station, a reviewer can point at the move (`persuade`, `gate_failed`, `probe`, `probe_contradiction`) and the transcript line that caused it, without inferring from tone of voice. Refuse-twice ends before any clinical question.

### Phase 3 — POC hardening

Still demo scope. Starts after the brain loop can be scored.

- Drop and stay away longer than 120 seconds: that interview ends incomplete. A later join is a new id, not a silent resume.
- Scorecard tier cites what was said. Accent and grammar are not the reason for a lower tier.
- Invite token and role picker only if Join is actually blocked (empty `roleId` after `GET /api/roles` fails).

**Stays out, even if a station was ugly:** GPT-Live as the demo, avatar, ElevenLabs hosted agents, Sarvam hosted agents, v1 Realtime, output-guard rewrite (unless Phase 2 produced a salary or selection promise — then a minimal blocklist is the fix, not a new brain), voice cloning, Sarvam as the default.

**Exit:** A drop past 120 seconds ends that interview incomplete on the same id; the scorecard evidence quotes match the transcript; the out-of-scope list above was not built.

---

## 3. Approaches: what to try, how to check, what to do on failure

Each approach the POC relies on is fixed here. “Investigate” is not a next step.

### 3.1 Scribe v2 Realtime

**What to try**

- Worker `STT_PROVIDER=elevenlabs_scribe`.
- `STT_SCRIBE_FALLBACK=openai` may stay in the file, but a fallback during the demo is a **stop**, not a successful call.
- Leave Scribe as `build_elevenlabs_scribe_stt` already builds it (`agent/providers/factory.py`): model `scribe_v2_realtime`, `include_timestamps=True`, `server_vad` silence `1.0` seconds, primary language plus secondary `en` (and `hi` when primary is another Indic language), at most 50 keyterms of 20 characters.
- Do not enable no-verbatim or entity redaction.
- Do not leave language on auto. `build_elevenlabs_scribe_stt` always sets `language_code` and `secondary_languages` from `_scribe_language_hints` (`agent/providers/factory.py`). The hint is the first subtag of the join code (`en-IN` → `en`, `hi-IN` → `hi`, and the same for `ta`, `te`, `kn`, `ml`, `mr`, `bn`, `gu`, `pa`). Secondary is `en`, plus `hi` when the primary is another Indic language. English’s secondary list is empty because `en` is removed as a duplicate of the primary.
- Odia is the exception. The product code is `od-IN`, so the helper currently sends `od`. ElevenLabs TTS documents Odia as `or`. Scribe’s published language list uses `ori`. Phase 1 maps Odia before that station counts (section 3.2).
- The form default in `V2TestPage` is still `hi-IN`. That is the stack-gate call. It is not the only Phase 1 language.

**How to check**

On the agent log for that interview, all of these in one startup:

- `ElevenLabs Scribe STT model=scribe_v2_realtime lang=hi secondary=['en']` (wording is `lang=%s secondary=%s`), `commit=server_vad silence=1.0s`, and `aligned=` not false.
- `STT ready provider=elevenlabs_scribe` and `aligned_transcript=True`.
- No line `elevenlabs_scribe STT failed`.
- Event `voice.session_config` posted by `agent/main.py` has `stt_provider` `elevenlabs_scribe` and `stt_aligned_transcript` true. The candidate page does not show this event. Read the agent log, or the stored extras once Phase 2 exposes events.

A screening answer that names a city appears in `GET /api/v2/interview/:id/transcript` as the candidate’s words, in the language they spoke, not as a paraphrase of the question. For English the city is Latin. For Hindi, a Hinglish line such as “main Delhi mein rehti hoon” stays mixed. For the other languages, native-script words stay in that script and an English word such as ICU stays in Latin.

**On failure**

| What you see | Next action |
| --- | --- |
| `STT ready provider=openai` or the example-file default | Stop the demo. Set `STT_PROVIDER=elevenlabs_scribe` on the **agent** process and restart that worker. `server/.env.example` does not select ears. |
| `elevenlabs_scribe STT failed` then `fallback=openai` | Stop. Fix `ELEVENLABS_API_KEY` or `ELEVEN_API_KEY` on the agent (name only; do not paste the value into docs or tickets). Do not score the call. |
| `aligned_transcript` false | Stop the barge-in station. Adaptive interruption needs word timestamps. Fix the Scribe build before tuning `INTERRUPTION_MIN_WORDS`. |
| Turns feel both late and chopped | The double endpoint is Scribe `vad_silence_threshold_secs` (1.0s in `factory.py`) plus LiveKit `ENDPOINTING_MAX_DELAY` (2.3). Shorten the Scribe silence toward 0.6s **or** raise the LiveKit cap, one change per call. Do not add another turn detector. |
| Garbled speech, or the transcript is the wrong language | That language station fails. Do not flip the demo worker off Scribe. Next action is section 3.2 for the voice, then section 3.7: one OpenAI STT comparison for that language, and Sarvam only if OpenAI STT also fails. |

### 3.2 ElevenLabs TTS per language (`eleven_v4_turbo`)

**What to try**

- Route flag only: `POST /api/v2/interview/start` with `ttsProvider: "elevenlabs"` (what `V2TestPage` sends when `App.tsx` mounts `/elevenlabs-interviewer`). The agent reads that flag in `agent/main.py` and passes it to `build_tts`. This URL does not speak Sarvam, Google, or OpenAI unless ElevenLabs fails to build.
- Agent `ELEVENLABS_MODEL=eleven_v4_turbo`. That model name is the default in `agent/config.py`. ElevenLabs’ models doc lists the v4 family, including this turbo model, as supporting the languages below: English, Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, and Odia (`or`). Stay on `eleven_v4_turbo`. The config comment also names `eleven_v4` as a slower quality model. Do not switch the demo to it.
- One persona per language. `elevenlabs_voice_for` (`agent/providers/elevenlabs_voices.py`) reads `ELEVENLABS_VOICE_BY_LANG` as a comma list of `code:voiceId`. A key may be the full code (`te-IN`) or the short code (`te`). If the key is missing, it falls back to `ELEVENLABS_VOICE_ID_LOCAL`, then `ELEVENLABS_VOICE_ID`.
- The only voice id in the repo is `4mCfn38CsM9hGLvDrPxv`, set as both defaults in `agent/config.py`. The comment there calls it Sujata and uses it for every language so the speaker does not change. That shared id is the starting point to listen to. It is not a finished per-language map. After each listen, record the id you keep in the tracker and in `ELEVENLABS_VOICE_BY_LANG`. If a language sounds wrong, write “TBD id” until a real id is chosen. Do not invent an id in docs. Do not clone a voice.
- `ishita`, `priya`, `pooja`, `roopa`, and `ritu` in `agent/interview/language.py` are Sarvam Bulbul speaker names (`tts_speaker`). They are not ElevenLabs voice ids. Do not copy them into `ELEVENLABS_VOICE_BY_LANG`.
- TTS language argument is `elevenlabs_language()`: the short code (`en`, `hi`, `ta`, `te`, `kn`, `ml`, `mr`, `bn`, `gu`, `pa`). English Indian accent is the voice, not a locale. The plugin is called with `language="en"` for `en-IN`. `native_script_reminder` already says “Respond in clear Indian English.” If the voice is American or British, change the voice id. Do not expect `en-IN` to select the accent by itself.
- Odia: map `od-IN` to ElevenLabs `or` before `build_tts` and before Scribe. Today both helpers send `od`, which is not the code in the ElevenLabs models doc (`or`) and not the Scribe list code (`ori`).
- Inside one call that stays in one language, the voice id does not change. A later join in another language uses that language’s id. A mid-call `switch_language` updates `voice_id` through `elevenlabs_voice_for`, so the persona may change. That is expected. One persona per language is the POC. Same-speaker-across-languages is not.
- `VOICE_EXPRESSIVENESS=engine` so tags stay on the TTS path and the stored transcript stays plain (`VOICE_TRANSCRIPT_SPLIT=true`).
- `TTS_PROVIDER` in `agent/.env.example` is `google`. That value is not what this URL should speak. The route override must win, and the key must be present. If the key is missing, `build_tts` today logs a warning and speaks OpenAI. Phase 1 task P1-03 makes a missing key a hard failure. OpenAI TTS is only the deliberate fallback in the failure table below, on `/v2/test`, not a silent substitute on the demo URL.
- OpenAI TTS, when that fallback is run, is the existing `build_tts` branch: model `gpt-4o-mini-tts`, voice `alloy`. The factory does not take a language or an Indian voice for that branch. `alloy` is not the Indian-accent demo voice.

**Voice map (fill ids in the tracker as they are heard)**

| Join code | Persona | ElevenLabs TTS language | Scribe hint | Voice id |
| --- | --- | --- | --- | --- |
| `en-IN` | Indian-accent English | `en` | primary `en`, secondary none | TBD id. Listen to `4mCfn38CsM9hGLvDrPxv` first |
| `hi-IN` | Hindi | `hi` | primary `hi`, secondary `en` | TBD id. Same starting id until a Hindi listen replaces it |
| `te-IN` | Telugu | `te` | primary `te`, secondary `en`, `hi` | TBD id |
| `ta-IN` | Tamil | `ta` | primary `ta`, secondary `en`, `hi` | TBD id |
| `kn-IN` | Kannada | `kn` | primary `kn`, secondary `en`, `hi` | TBD id |
| `ml-IN` | Malayalam | `ml` | primary `ml`, secondary `en`, `hi` | TBD id |
| `bn-IN` | Bengali | `bn` | primary `bn`, secondary `en`, `hi` | TBD id |
| `mr-IN` | Marathi | `mr` | primary `mr`, secondary `en`, `hi` | TBD id |
| `gu-IN` | Gujarati | `gu` | primary `gu`, secondary `en`, `hi` | TBD id |
| `pa-IN` | Punjabi | `pa` | primary `pa`, secondary `en`, `hi` | TBD id |
| `od-IN` | Odia | `or` (after the map; code sends `od` today) | try `or`, then `ori` if Scribe rejects `or` or transcribes another language | TBD id |

`LanguagePicker.tsx` fallback lists only English, Hindi, Tamil, Telugu, Kannada, and Malayalam. Marathi, Bengali, Gujarati, Punjabi, and Odia appear after `GET /api/v2/interview/languages` returns `SUPPORTED_LANGUAGES`. Confirm that response before those five stations. They are claimed by the product. A fallback-only picker is an API failure, not a missing language.

**How to check (each language)**

- Server log: `[v2] start interview=<id> avatar=false tts=elevenlabs voice=cascade`.
- Agent log: `job <id> avatar=False tts=elevenlabs voice=cascade`.
- `ElevenLabs TTS voice=<id for this language> lang=<short code> model=eleven_v4_turbo`.
- `ElevenLabs Scribe STT model=scribe_v2_realtime lang=<primary> secondary=<list>`.
- `TTS ready provider=elevenlabs` and the same `voice=` id. `STT ready provider=elevenlabs_scribe`.
- No line `falling back to OpenAI TTS` on the demo call.
- You hear that language (Indian accent for English). One screening answer comes back in that language. Native-script words stay in script. An English word such as ICU stays Latin.
- Transcript download has no raw `[friendly]` / `[pause]` tags in the assistant text the reviewer reads.

**On failure**

| What you see | Next action |
| --- | --- |
| `falling back to OpenAI TTS` or `TTS ready provider=openai` on the demo URL | Stop. Put a real key on the agent and restart. Do not collect voice feedback on that call. P1-03 makes this a hard failure instead of a silent fallback. |
| Voice id changes during a call that stayed in one language | Stop. The `ELEVENLABS_VOICE_BY_LANG` entry for that code is missing or duplicated, so a later update picked the default. Set one id for that code and restart. |
| `model=` is `eleven_v4` or a Google voice name | Stop. Set `ELEVENLABS_MODEL=eleven_v4_turbo` and confirm the route override. Do not A/B Google on this URL. |
| English sounds American or British | Keep Scribe. Replace the `en` / `en-IN` voice id. Record the new id in the tracker. Do not clone. Do not open `/gpt-live-interviewer`. |
| An Indian language is silent, or the agent speaks a different language | Confirm `lang=` is the short code in the map. For Odia, `lang=od` is the bug: map to `or` and rerun. If `lang=` is already right, select a different ElevenLabs voice id, record it, restart, and rerun that language only. |
| ElevenLabs speaks but the voice is the wrong language after one id change | One comparison on `/v2/test` with no `ttsProvider`, on a worker whose `TTS_PROVIDER=openai`, so `build_tts` uses `gpt-4o-mini-tts` and voice `alloy`. That call is not the demo. If `alloy` also cannot carry the language, one Sarvam comparison (section 3.7) using that language’s Bulbul speaker. Then put the demo worker back on ElevenLabs. |
| Tags spoken aloud | Set `VOICE_EXPRESSIVENESS=engine` and `VOICE_TRANSCRIPT_SPLIT=true`. If tags are still spoken, turn the engine off for the demo rather than letting the LLM write free-form tags. |
| Transcript language does not match what was spoken | The mouth can still pass. The ear failed. Section 3.7. Do not change the voice id to hide a bad transcript. |

### 3.3 LiveKit turn-taking

**What to try**

Keep the values already in `agent/.env.example` and `agent/interview/turns.py`. Do not apply the architecture note’s different numbers (those are listed under disagreements).

- `TURN_DETECTOR_ENABLED=true`
- `ENDPOINTING_MODE=dynamic`
- `ENDPOINTING_MIN_DELAY=0.25` for English and Hindi; `ENDPOINTING_MIN_DELAY_UNCOVERED=0.55` for every other language this product speaks
- `ENDPOINTING_MAX_DELAY=2.3`
- `INTERRUPTION_MODE=adaptive`
- `INTERRUPTION_MIN_WORDS=2` when Scribe alignment is on; `INTERRUPTION_MIN_WORDS_NO_ALIGN=3` otherwise
- `FALSE_INTERRUPTION_TIMEOUT=1.8` and `resume_false_interruption` (hardcoded true in `build_turn_handling`)
- `PREEMPTIVE_GENERATION=false`
- `OPENING_BLOCK_INTERRUPTIONS=true`
- Do not attach a second turn-taker. Silero VAD stays on this cascade (it is intentionally absent only on GPT-Live).

**How to check**

Startup line:

`turn handling: detector=<not the string vad> endpointing={'mode': 'dynamic', ... 'max_delay': 2.3} interruption=adaptive preemptive=False`

Manual script on a Hindi call, after the greeting:

1. While the agent is mid-sentence, say only “haan”. It should keep talking. Log: `false interruption (resumed=True) — interviewer should continue`.
2. While it is mid-sentence, say “no, not Delhi, Noida” (or correct whatever city you gave). It should stop and use the correction. The next transcript user line contains the correction. The next `move=` is not a brand-new topic that ignores it.
3. Pause about two seconds inside a sentence, then finish the city. It should not take the pause as the end of the turn.

UI: a short network blip on the same page shows header **Linking** (`reconnecting`), then **Live**. That is not the Rejoin station.

**On failure**

| What you see | Next action |
| --- | --- |
| `Turn detector unavailable; using VAD turn detection` on a Hindi call | Restart with a worker that can import `livekit.agents.inference.TurnDetector`. Do not switch to GPT-Live. |
| Real answers get cut off, “haan” does not | One change: raise `ENDPOINTING_MAX_DELAY` (try 3.0, then 3.5). Re-run the three checks. Do not enable preemptive generation in the same change. |
| “haan” or a cough cuts the agent off | Confirm `interruption=adaptive` and `aligned_transcript=True`. If alignment is false, stop and fix Scribe (section 3.1). If alignment is true and “haan” still barges, raise `INTERRUPTION_MIN_WORDS` from 2 to 3 and re-test. Do not stack browser noise suppression. |
| Both late and chopped | Section 3.1 double-endpoint rule. One knob per call. |
| Agent talks twice | Do not start a speech-arbiter rewrite in Phase 1. Note the two `move=` lines and the two assistant transcript rows. If it happens on more than one turn in the dry run, stop Phase 1 exit and disable fillers for the next call (`THINKING_FILLER_PROBABILITY=0`, `VOICE_EARLY_FILLER=false`) before any refactor. |

### 3.4 Krisp BVC

**What to try**

- Agent `NOISE_PROVIDER=krisp`.
- `build_noise_cancellation` must take the BVC branch, not NC.
- Published mic in `useLiveKitInterview.ts`: `echoCancellation: true`, `noiseSuppression: false`, `autoGainControl: true`.
- The candidate preflight (`PreflightCheck` with `simple`) asks for `noiseSuppression: true` and then **stops those tracks**. That probe must not be the stream that joins the room. Do not “fix” the live call by turning browser suppression on.
- Do not set Scribe `filter_background_audio`. Do not set `NOISE_PROVIDER=aicoustics` for this demo.

**How to check**

Agent log, in order:

1. `noise cancellation: Krisp BVC (background voice + noise)`
2. `inbound audio noise_cancellation=on provider=krisp`

These are failures if they appear instead:

- `Krisp NC only (no BVC in plugin — env noise, not other voices)`
- `Krisp noise cancellation unavailable`
- `noise cancellation disabled (NOISE_PROVIDER=none)`

Noise station (Phase 1 matrix): television or a second person talking while you answer a screening question, then one mumble. Pass is section 3.5 plus the transcript field matching what you said on the clear repeat, not the television.

**On failure**

| What you see | Next action |
| --- | --- |
| NC only | Stop the noise station. Upgrade or reinstall the LiveKit noise-cancellation plugin so `BVC` exists, restart the worker, confirm the BVC line. Do not continue on NC. |
| Unavailable / none | Stop. Fix the plugin import. Do not switch to ai-coustics for a speakerphone. |
| BVC line is present and the television is still transcribed as the answer | The brain must `ask_repeat` (section 3.5). If it stores the television as the city or the phone, stop and treat that as a Flow bug, not a reason to add a second denoiser. |

### 3.5 Director and InterviewFlow

**What to try**

Leave the policy code alone in Phase 1. Phase 2 may surface moves. It does not retune the gate, probe caps, escalation, or classification.

- `Director.decide` returns a `Move`. It does not call TTS.
- Each cascade turn appends one `CONTROLLER DIRECTIVE` (`agent/main.py`).
- Clinical turns keep `CLINICAL_DIRECTOR_MODEL`. Phase 1 does not need a clinical pass.
- Unclear audio: `noise_move` → `_unclear`. First failures are `ask_repeat` (event `audio.unclear`). After `max_unclear_streak` (3 in `nursing.json`) the move is `noise_help` (event `audio.noise_help`). The same focus soft-skips after `MAX_FOCUS_RETRIES` (3) via `focus.soft_skip`. It must not loop please-repeat forever and must not invent the slot.
- Diaper gate, used in Phase 2, stays at `max_persuasions: 2`, events `care.persuasion` then `gate.failed`, move `gate_failed`, outcome stop before clinical. Do not change this to the architecture note’s single re-ask. Do not pull that station into Phase 1.
- Log line already present: `move=<kind> stage=<stage>` and `analysis source=... intent=... clarity=...`.

**How to check**

Phase 1 (please-repeat), one screening question:

1. Mumble. Agent asks you to repeat. Log `move=ask_repeat`. It does not say your city for you.
2. Clear repeat with a real city. Later `GET /api/v2/interview/:id` → `controller.flow` contains that city, not text from the mumble.
3. If you mumble until it suggests a quieter spot, log `move=noise_help` once, then it continues. It does not stay on `ask_repeat` for the rest of the call.

Phase 2 (brain), after the move is visible in the log today and on a reviewer-facing surface (expose `extras.events` — they are stored in `server/v2/lib/v2Store.ts` and are **not** on `GET /api/v2/interview/:id` or the transcript route today):

- Second diaper refusal: `move=gate_failed` and event `gate.failed`. Transcript has no clinical question after that. Salary or “am I selected?” does not produce a number or a yes.
- Thin clinical answer: `move=probe` (or `clarify` / `probe_simpler`), not the next blueprint topic.
- Contradiction: `move=probe_contradiction`.

**On failure**

| What you see | Next action |
| --- | --- |
| Please-repeat loop past `noise_help` / soft-skip | Stop. Fix the streak counters in `flow.py`. Do not raise the cap to hide the loop. |
| Invented slot after a mumble | Stop. The analysis path treated noise as a fact. Do not tune TTS to cover it. |
| Clinical starts after two diaper refusals | Stop Phase 2. The gate regressed. Restore `max_persuasions: 2` and `gate_failed` before any voice work. |
| Salary or selection is promised | The first fix is a small blocklist before TTS for that phrase class. Do not start the architecture note’s full streaming guard, and do not move the brain to a hosted agent. |
| Reviewer cannot see the move without a terminal | Phase 2 is not done. Add the events (or `move` kind) next to the transcript. Do not declare the brain “watched” from audio alone. |

### 3.6 Rejoin within 120 seconds

**What to try**

Agent behaviour already exists. Do not build a new session store.

- `close_on_disconnect` is false (`agent/main.py`).
- `ConnectionGuard` waits `RECONNECT_GRACE_SECONDS` (120), logs `candidate disconnected; waiting 120s for them to return`, and on `participant_connected` calls `flow.resume()` which repeats the last question (event `flow.resumed`, move `resume`).
- If they do not return: `candidate did not return; ending interview as incomplete` and `force_complete("incomplete_disconnect")` with nobody to speak to.
- Room name is `interview-v2-<interviewId>` (`roomNameForInterview`). Room `emptyTimeout` is 10 minutes, which is longer than the grace window. Token TTL on first join is 2 hours.
- The hole is the browser. `useLiveKitInterview.ts` sets phase `ended` on `ConnectionState.Disconnected`. A refresh drops React state, so the next Join is `POST /api/v2/interview/start` and a **new** id. There is no Rejoin control.

Phase 1 adds Rejoin on `/elevenlabs-interviewer` only:

- Remember the current interview in `sessionStorage` (id, display fields, room). The 120-second clock starts at **disconnect**, not at interview start.
- Refresh shows Rejoin for that id. Rejoin must not call `POST /start`.
- Same LiveKit identity the start route already uses: `candidate-<first 8 chars of the interview id>`.
- Rejoin token must **not** include `RoomAgentDispatch`. `createCandidateToken` always embeds a dispatch. A second dispatch can put two interviewers in one room. `ensureRoomAndDispatch` already skips when that agent name is already dispatched; the JWT path does not.
- Explicit End still runs summary. A drop must not call `POST /:id/summary`.
- After 120 seconds, hide Rejoin. The agent has ended the interview incomplete.

A brief `reconnecting` → `live` on the same page stays as it is. Do not show Rejoin during Linking.

**How to check**

1. Join, answer one screening question, write down the interview id shown on the page.
2. Refresh once.
3. Within 120 seconds, press Rejoin. You land in the same room. You hear the last question again. You do not hear a second greeting from a second agent.
4. Agent log contains `waiting 120s` and then the resume speak. `GET /api/v2/interview/:id` is the same id, and `controller.flow` still has the answer from step 1.
5. Header returns to **Live**. Scorecard does not appear until you press End.
6. Separate call: refresh and wait past 120 seconds. Log: `candidate did not return; ending interview as incomplete`. Rejoin is gone. `POST /start` is the only way forward, and it is a new id.

**On failure**

| What you see | Next action |
| --- | --- |
| Refresh opens a blank Join form and Start creates a new id | The Rejoin task is not done. Do not score the disconnect station. |
| Two voices after Rejoin | Stop. Issue the rejoin token without `roomConfig` agents. Confirm `listDispatch` still shows one `interview-v2` job. |
| Resume talks but the city or phone is gone | Stop. Persistence failed (`persisting flow state failed` in the agent log). Fix `_persist` / `update_controller` before any more voice tests. Do not add a new store. |
| Rejoin works after three minutes | The UI clock is wrong. Gate the button on disconnect time and on `controller.completed`. The agent grace is the authority. |
| Only Linking recovers, refresh dead-ends | Expected until P1-09 ships. Do not file that as a brain failure. |

### 3.7 OpenAI STT, then Sarvam (only after a language station fails)

**What to try**

The demo ear stays Scribe. A fallback during a scored demo call is still a stop: do not leave `STT ready provider=openai` on the demo worker and score it as the ElevenLabs station.

When one language’s transcript is garbled or in the wrong language:

1. Leave the failed Scribe transcript and interview id in the feedback sheet. Fix the voice first if the failure was the mouth (section 3.2). This section is the ear.
2. OpenAI STT is the next ear, not a second demo route, and not `/gpt-live-interviewer`. On a **different** worker (or a quiet window): `STT_PROVIDER=openai`. `build_openai_stt` uses `OPENAI_STT_MODEL`. The config default is `gpt-live-transcribe`, which is a transcription model name in `agent/config.py`, not the GPT-Live session. For that model the language argument is `openai_stt_languages`: the short code, plus `en` when the primary is not English. Other OpenAI STT models get the short code only. The prompt names the profile label and asks for native script plus Latin English. Join the same language, same utterance, through `/v2/test` with no `ttsProvider` and no `voiceProvider`.
3. If that OpenAI transcript is also wrong or empty, then one Sarvam comparison on that same non-demo worker: `STT_PROVIDER=sarvam`, `TTS_PROVIDER=sarvam`, `SARVAM_API_KEY` set. Factory already asks for `saaras:v4` and `bulbul:v3`, and Indic profiles use `stt_mode` `codemix` (`en-IN` is `transcribe`). Stay on Bulbul v3 so Malayalam and Odia exist. Speaker names are the `tts_speaker` values in `language.py` (`ishita`, `priya`, `pooja`, `roopa`, `ritu`). Do not send romanised Indic text as the TTS source of truth. The ElevenLabs URL would still force ElevenLabs TTS, so a Sarvam mouth test on `/elevenlabs-interviewer` is invalid.
4. One comparison per failed station per fallback. Then put the demo worker back to `STT_PROVIDER=elevenlabs_scribe` and ElevenLabs TTS before any further scored call.

**How to check**

- OpenAI comparison log shows `STT ready provider=openai`, not `elevenlabs_scribe`, and not `voice=gpt_live`.
- Sarvam comparison log shows Sarvam STT and `bulbul:v3` (not an ElevenLabs `TTS ready` line).
- Pass for a comparison: the same utterance is intelligible, English words such as ICU stay in Latin script, and the interview does not restart.
- The feedback sheet has both interview ids. The comparison does not replace the Scribe pass. The language is still failed on the demo until Scribe passes.

**On failure**

| What you see | Next action |
| --- | --- |
| Station passed on Scribe | Do not run OpenAI STT. Do not run Sarvam. Do not change the default. |
| OpenAI STT comparison is clearly better | Record that. A default change is a separate decision after the sheet is written. Do not flip the demo worker mid-test. |
| OpenAI STT is also garbled | One Sarvam comparison, then stop that language if Sarvam is also garbled or `SARVAM_API_KEY` is missing. Do not try GPT-Live, hosted agents, or v1 Realtime. |
| Someone tests Sarvam or OpenAI TTS on `/elevenlabs-interviewer` | Invalid. The route lock hides the mouth. Repeat on `/v2/test`. |

---

## 4. Phase exit criteria

| Phase | Next phase starts only when |
| --- | --- |
| 1. Cascade and language voices | Startup logs show Scribe v2, `eleven_v4_turbo`, the voice id mapped for that language, and Krisp BVC. English is an Indian accent. Each language in the voice map has a recorded id and a Scribe hint that matches the join. Live dry-run calls: English, Hindi, and Telugu. The other languages are wired even if only spot-checked. Please-repeat does not invent a fact. Rejoin within 120s repeats the last question on the same id. Phase 1 feedback sheet is filled. Brain stations are not required. |
| 2. Brain loop | Reviewer can show the move and the transcript line for refuse-twice (no clinical), a partial-answer probe, and a contradiction probe. |
| 3. Hardening | A drop past 120s ends that id incomplete; scorecard quotes match the transcript; GPT-Live, avatar, hosted agents, Sarvam-as-default, and an output-guard rewrite were not built. |

---

## 5. Demo script

Local: `http://localhost:5173/elevenlabs-interviewer`. Deployed: `https://interviewai-418h.onrender.com/elevenlabs-interviewer`. Do not open `/gpt-live-interviewer` for these scores.

**Record every station:** what you heard, the transcript line, the `move=` kind if you have the log. Accent and grammar are never the reason for a lower tier. Mark Pass or Fail. On Fail, write the next action from section 3, not “investigate”.

### Phase 1 — voice and languages

Name filled. Sample resume left as-is. Mic allowed. Consent checked. Write the interview id before you speak.

Live calls, in this order: English (`en-IN`), Hindi (`hi-IN`), Telugu (`te-IN`). On each, wait for the greeting, answer one screening sentence in that language, and keep one English word such as ICU in Latin script. English must sound Indian, not American or British. Hindi may be Hinglish (“main Delhi mein rehti hoon, BSc nursing 2019”). Telugu is the South Indian live station.

On the Hindi call only, also run noise, barge-in, please-repeat, and Rejoin (rows 2, 5, and 6). Optionally say you are more comfortable in Tamil or Telugu and answer the same question that way. Pass for that switch: `language.switched` fires, Scribe’s hint updates, and the voice id becomes the target language’s persona. It must not flip because of one English word (`language.detected` may log; it must not retarget by itself). A voice-id change on a real switch is expected. A voice-id change with no switch is a failure.

The other languages (Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia) need a recorded voice id and a startup log whose Scribe hint and TTS `lang=` match the map. A full live answer is a spot-check, not a second dry-run gate, except Tamil if you used it as the switch above.

| # | Do this | Pass | Fail |
| --- | --- | --- | --- |
| 1. Language join | Start in the language for this call. Hear the greeting. Answer one screening sentence in that language. | `model=eleven_v4_turbo`, voice id is the one recorded for this code, Scribe `lang=` is the hint in section 3.2, transcript matches what you said. English accent is Indian. | Silent, wrong language, wrong accent, or `TTS ready provider=openai` on this URL. Next action: section 3.2, then section 3.7 if the transcript language is wrong. |
| 2. Noise | On the Hindi call: television or a second person talking. Answer the next question. Then mumble once. | `move=ask_repeat`. It does not invent the fact. A clear repeat stores the right field. It does not loop please-repeat forever (`noise_help` or soft-skip). | Television is scored, or the loop never ends. Next action: confirm the BVC log first; if BVC was on, stop and fix Flow. |
| 5. Interruption | On the Hindi call: talk over the agent with “no, not Delhi, Noida”. Also say only “haan” while it speaks. On the English call, “okay” is the short backchannel. | The correction stops it and is used. “haan” or “okay” does not. `false interruption (resumed=True)` for the backchannel. | A cough or the backchannel cuts it off, or it talks over the correction and asks something new. Next action: section 3.3. One change, then rerun this row. |
| 6. Drop | On the Hindi call: refresh once mid-screening. Rejoin within two minutes. | Same interview id. Last question repeated. City still in `controller.flow`. One agent voice. | New id, dead-end page, or a second interviewer. Next action: Phase 1 Rejoin task. Until it ships, score only a short blip that stays on the page (Linking, then Live). A refresh dead-end is a known client gap, not a failed brain. |

Rows 3 and 4 (diaper refusal, partial clinical) are Phase 2. If they happen during a Phase 1 call, note them and do not score them here.

### Phase 2 — brain, after Phase 1 feedback exists

Run on the same URL, any language that already passed Phase 1. Hindi is fine.

| # | Do this | Pass | Fail |
| --- | --- | --- | --- |
| 3. Refusal | On diaper care, refuse. After the explanation, refuse again. Then ask “what salary will I get, and am I selected?” | Two persuasions, then `gate_failed`. No clinical question. Salary and selection are deflected, not promised. | Clinical starts, or a salary or an outcome is stated. Next action: restore the gate if clinical started. If a promise was spoken, add the small blocklist. Do not build the full output guard in this round unless the promise is still there after that. |
| 4. Partial clinical | Only on a **second** call where you accept diaper care. Answer “I check vitals” with no number and no action. | Next question asks for what was missing. It does not say “wrong” out loud and does not jump to a new topic. `move=probe` or `clarify`. | It reads the next blueprint question as if the answer were complete. Next action: stop and fix the clinical move. Do not retune TTS. |

**After End on a Phase 2 call.** Download the transcript. Read the scorecard. Note the tier and one evidence quote. If the quote is not in the transcript, that is a Phase 3 failure, not a voice failure.

**Sheet columns:** station, language, pass/fail, heard, transcript line, voice id, move or event, next action taken.

---

## 6. Where the docs and the code disagree

The plan follows `docs/voice-poc-approach.md` and the code. These are the mismatches a reader will hit.

| Topic | Other doc | Code / this plan |
| --- | --- | --- |
| Face on the demo | `docs/client-requirements.md` section 8 says a face must be true before moving ahead | Both live routes render `PresenceOrb`. `agent/.env.example` has no `TAVUS_*`. Avatar stays out. |
| Diaper re-ask | Architecture note: at most one re-ask, then move on | `nursing.json` `max_persuasions` is 2. `flow.py` then `gate_failed` and **stops before clinical**. Client requirement matches the code. Keep two beats. |
| Endpointing numbers | Architecture note: min 0.6, max 3.5, preemptive generation on, `min_words` 1 | `agent/.env.example`: min 0.25 (0.55 uncovered), max 2.3, `PREEMPTIVE_GENERATION=false`, `INTERRUPTION_MIN_WORDS=2`. Keep the example. Raise max delay only if station 5 cuts real answers. |
| Sarvam as a voice A/B | Architecture note recommends A/B Bulbul for Hindi/Marathi up front | OpenAI STT is the first fallback when a Phase 1 language station fails Scribe. Sarvam runs only if that also fails, on `/v2/test`, Bulbul v3. |
| Output guard | Architecture note: streaming guard before TTS is part of the control design | Deferred. Build a small blocklist only if the Phase 2 refusal station speaks a salary or an outcome. |
| STT default | `agent/.env.example` sets `STT_PROVIDER=openai`. Routes doc says the checked-in agent env uses `elevenlabs_scribe` | Demo worker must be Scribe. A worker started from the example file will speak ElevenLabs and hear with OpenAI. |
| TTS default | `agent/.env.example` sets `TTS_PROVIDER=google` | This URL overrides TTS to ElevenLabs. Missing key falls back to OpenAI TTS today (`factory.py` warning). Phase 1 must fail that call instead of scoring it. |
| Server provider names | `docs/interviewer-routes-context.md` lists `STT_PROVIDER`, `TTS_PROVIDER`, `ELEVENLABS_API_KEY`, `TAVUS_API_KEY` as names present on `server/.env` | `server/.env.example` does not list those. Server provider names do not select the worker. Configure the agent. |
| Browser noise suppression | Approach doc: browser suppression is off | True for the **published** mic. The candidate preflight probe (`simple`) requests suppression and then stops the tracks. Do not reuse that stream. |
| One shared voice | Approach note: one ElevenLabs voice id for the whole call so the speaker does not change | Phase 1 uses one persona per language (`ELEVENLABS_VOICE_BY_LANG`). The checked-in id `4mCfn38CsM9hGLvDrPxv` is only the starting listen. The approach note is not rewritten beyond the pointer at the top. |
| Language picker | Client list includes Marathi, Bengali, and “other relevant” languages. `SUPPORTED_LANGUAGES` also has Gujarati, Punjabi, Odia | All eleven codes are in Phase 1. `LanguagePicker.tsx` fallback omits Marathi, Bengali, Gujarati, Punjabi, and Odia until `GET /api/v2/interview/languages` succeeds. Confirm the API list, not the fallback. Odia must be sent to ElevenLabs as `or`, not `od`. |
| Why the next question happened | Approach: reviewers look at what was asked next | `move=` is an agent log. `extras.events` is stored and is not returned by `GET /api/v2/interview/:id` or `GET /:id/transcript`. Phase 2 surfaces it. |
| Both public URLs | Client requirements and the routes doc present GPT-Live and ElevenLabs as the two live surfaces | Feedback for this POC is collected on `/elevenlabs-interviewer` only. |

---

## 7. Working tracker

Phase 1 implementation detail, including one task per language, is in `docs/phase-1-tracker.md`. Phase 2 and Phase 3 get their own trackers when Phase 1 exits. Do not pull brain-loop or hardening tasks into the Phase 1 file.
