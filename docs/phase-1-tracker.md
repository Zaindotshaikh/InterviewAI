# Phase 1 tracker — cascade demo and language voices

**Plan:** `docs/poc-implementation-plan.md`  
**Phase goal:** `/elevenlabs-interviewer` is reliable enough to start a call in every major language the product already claims, with an Indian-accent English voice or a matching Indian-language voice, and Scribe accepting that language.  
**Status values:** `Not started` · `In progress` · `Blocked` · `Done`  
**Do not start Phase 2 (brain feedback)** until the exit line under the status table is true.

This file is the implementation guide for Phase 1. An engineer should not need to reread the whole plan to do these tasks. Brain-loop and hardening work stay in the plan.

---

## Status

| ID | Title | Critical path | Status |
| --- | --- | --- | --- |
| P1-01 | Pin the demo worker configuration | Yes | Not started |
| P1-02 | Startup log gate | Yes | Not started |
| P1-03 | Fail closed when ElevenLabs TTS cannot start | | Not started |
| P1-04 | Fail closed when Scribe falls back | | Not started |
| P1-05 | Require Krisp BVC, not NC-only | | Not started |
| P1-06 | Confirm the published mic leaves noise suppression off | | Not started |
| P1-07 | Barge-in and endpointing station | Yes | Not started |
| P1-08 | Please-repeat ladder | | Not started |
| P1-09 | Rejoin the same interview within 120 seconds | Yes | Not started |
| P1-10 | Show the interview id and do not score a drop | | Not started |
| P1-11 | One persona per language, stable inside that call | | Not started |
| P1-12 | Record the voice map and Odia language code | Yes | Not started |
| P1-13 | English, Indian accent (`en-IN`) | Yes | Not started |
| P1-14 | Hindi (`hi-IN`) | Yes | Not started |
| P1-15 | Telugu (`te-IN`) | Yes | Not started |
| P1-16 | Tamil (`ta-IN`) | | Not started |
| P1-17 | Kannada (`kn-IN`) | | Not started |
| P1-18 | Malayalam (`ml-IN`) | | Not started |
| P1-19 | Bengali (`bn-IN`) | | Not started |
| P1-20 | Marathi (`mr-IN`) | | Not started |
| P1-21 | Gujarati (`gu-IN`) | | Not started |
| P1-22 | Punjabi (`pa-IN`) | | Not started |
| P1-23 | Odia (`od-IN`) | | Not started |
| P1-24 | Dry-run the Phase 1 matrix and fill the sheet | Yes | Not started |

**Critical path (in order):** P1-01 → P1-02 → P1-07 and P1-09 (P1-09 can be coded beside P1-07, and must be tested on a worker that passed P1-02) → P1-12 → P1-13, P1-14, and P1-15 live → P1-16 through P1-23 wired (voice id plus Scribe hint; a full answer is a spot-check) → P1-24.  
P1-03, P1-04, and P1-05 are stop-conditions inside P1-02. P1-08 must be Pass before the noise row of P1-24. P1-06 and P1-11 are checks on the same startup call as P1-02. Rejoin (P1-09) stays in Phase 1.

**Phase 1 exit:** P1-24 is Done, and every critical-path row is Done. A Fail on the matrix with a written stop (section “Risks and stop conditions”) blocks the exit. “Investigate” is not a closed row. Brain-quality scoring does not block this exit.

---

## Goal, in scope, out of scope

### Goal

A tester opens one URL, picks any language in the Phase 1 set, hears that language’s ElevenLabs persona (Indian accent for English), is understood by Scribe in that language, gets cut off only by a real interruption, is asked to repeat when audio is garbage, and can refresh and rejoin the same interview within 120 seconds. They leave with an interview id and a filled sheet. The existing brain runs so the call can continue. This phase does not retune it.

### In scope

- Worker configuration for the process that actually joins rooms for this URL.
- Observable proof: agent log lines and one `voice.session_config` event.
- Fail-closed behaviour when TTS or STT silently substitutes OpenAI, and when Krisp is NC-only or missing.
- Browser Rejoin after a hard drop or refresh, same interview id, no second agent.
- Interview id visible on the live screen.
- Please-repeat, barge-in, Rejoin, and a Phase 1 feedback sheet.
- One ElevenLabs persona per language on `eleven_v4_turbo`, selected with `ELEVENLABS_VOICE_BY_LANG`. Scribe language hint from the join code.
- Languages: English (Indian accent), Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia.
- Manual test matrix below. Phase 1 stations only. Live dry run is English, Hindi, and Telugu. The other languages must be wired before exit.

### Out of scope

- `/gpt-live-interviewer` feedback, avatar, hosted agents, v1 Realtime.
- Sarvam as the demo default. No `STT_PROVIDER=sarvam` on the demo worker in this phase.
- Diaper-care scoring, partial-clinical scoring, contradiction scoring, escalation, and classification tuning. Those are Phase 2. If they happen during a Phase 1 call, do not “fix” Flow.
- Making `/gpt-live-interviewer` the language demo. OpenAI STT is a fallback ear for a failed language station, not that route.
- Output-guard rewrite, per-question endpointing subsystem, preemptive generation, voice cloning.
- TA dashboard, invite links, role picker, unless `GET /api/roles` fails and Join stays disabled (then see Risks).
- Editing `docs/voice-poc-approach.md`, `docs/client-requirements.md`, or the architecture note.

---

## Pre-flight checklist

Run this before P1-02. Names only. Never paste secret values into this file, a ticket, or a log excerpt that you commit.

### Which process

The **agent** worker reads `agent/.env` (pydantic in `agent/config.py`). The API reads `server/.env`. The repo-root `.env` does not configure this route. `STT_PROVIDER` on the server does not choose ears.

`agent/.env.example` defaults `STT_PROVIDER=openai` and `TTS_PROVIDER=google`. A worker started from that example will fail this demo even if the URL says ElevenLabs. The checked-in agent env is documented as `STT_PROVIDER=elevenlabs_scribe`. Confirm the **running** worker, not the example file.

### Agent env names that must be set this way

| Name | Required value for this demo |
| --- | --- |
| `STT_PROVIDER` | `elevenlabs_scribe` |
| `STT_SCRIBE_FALLBACK` | `openai` may remain, but a fallback during a scored call is a stop (P1-04) |
| `NOISE_PROVIDER` | `krisp` |
| `ELEVENLABS_MODEL` | `eleven_v4_turbo` |
| `ELEVENLABS_API_KEY` or `ELEVEN_API_KEY` | Present on the agent. Non-empty. Do not record the value |
| `ELEVENLABS_VOICE_ID` and `ELEVENLABS_VOICE_ID_LOCAL` | The same fallback id. Checked-in default is `4mCfn38CsM9hGLvDrPxv` (comment in `agent/config.py` calls it Sujata). Used only when a language key is missing |
| `ELEVENLABS_VOICE_BY_LANG` | Empty is allowed until P1-12. After P1-12, one id per language, comma list, short or full code (`en:ID,hi:ID,...`). Record ids in the voice map in P1-12. Do not paste API keys |
| `VOICE_EXPRESSIVENESS` | `engine` |
| `VOICE_TRANSCRIPT_SPLIT` | `true` |
| `TURN_DETECTOR_ENABLED` | `true` |
| `ENDPOINTING_MODE` | `dynamic` |
| `ENDPOINTING_MIN_DELAY` | `0.25` |
| `ENDPOINTING_MIN_DELAY_UNCOVERED` | `0.55` |
| `ENDPOINTING_MAX_DELAY` | `2.3` (raise only in P1-07 if real answers are cut off) |
| `INTERRUPTION_MODE` | `adaptive` |
| `INTERRUPTION_MIN_WORDS` | `2` |
| `PREEMPTIVE_GENERATION` | `false` |
| `RECONNECT_GRACE_SECONDS` | `120` |
| `V2_AGENT_NAME` | Same string as the server, default `interview-v2` |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Present, and the same project as the server |
| `BACKEND_URL` | The API the worker can reach (local example `http://127.0.0.1:3001`) |
| `V2_INTERNAL_SECRET` | Same value on agent and server |
| `OPENAI_API_KEY` | Present (dialogue model and Director). Not a substitute for the ElevenLabs key |
| `LLM_MODEL` | `gpt-4o-mini` (example). Do not point the dialogue model at the director model |
| `DIRECTOR_MODEL`, `CLINICAL_DIRECTOR_MODEL` | Example `gpt-4o`. Leave them |

Leave `SARVAM_API_KEY` unset on this worker. Leave `VOICE_EARLY_FILLER=false`. Do not set `NOISE_PROVIDER=aicoustics`.

### Server env names that must match the agent

From `server/.env.example`: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `V2_AGENT_NAME`, `V2_INTERNAL_SECRET`, `OPENAI_API_KEY`, `PORT` (example `3001`).

`PROVIDER_MODE` on the server does not select the cascade. Ignore server `STT_PROVIDER` / `TTS_PROVIDER` if they exist outside the example file.

### Krisp: BVC versus NC-only

`NOISE_PROVIDER=krisp` is not enough. `agent/providers/factory.py` prefers `noise_cancellation.BVC`. If the plugin has no `BVC` attribute it logs NC-only and still returns a filter. NC-only removes non-speech noise and still transcribes a television or a second person. **The demo requires the BVC log line.** If you see NC-only or `Krisp noise cancellation unavailable`, stop. Fix the plugin. Do not run the noise row.

### URL to open

- Local client: `http://localhost:5173/elevenlabs-interviewer` (Vite proxies `/api` to `http://localhost:3001`).
- Deployed: `https://interviewai-418h.onrender.com/elevenlabs-interviewer`.

Stack-gate join (P1-02) may stay Hindi (`hi-IN`), the form default in `V2TestPage`. Phase 1 is not done on that call alone. Language stations use the picker. Do not open `/gpt-live-interviewer`, `/avatar-interviewer`, or `/i/:token`.

`GET /api/v2/interview/languages` must return all eleven codes. The picker fallback in `client/src/v2/components/LanguagePicker.tsx` omits Marathi, Bengali, Gujarati, Punjabi, and Odia until that call succeeds. If those options are missing, fix the API before those stations. They are not unsupported languages.

### Processes that must be up

1. API (`server`, port from `PORT`).
2. The agent worker whose env passed the table above, registered as `V2_AGENT_NAME`.
3. Client dev server, or the deployed bundle.

`GET /api/roles` must return at least one role or the Join button stays disabled (`roleId` empty). That is the only role check in this phase.

---

## Ordered tasks

### P1-01 — Pin the demo worker configuration

**Critical path:** Yes  
**Status:** Not started  
**Why:** The URL forces ElevenLabs TTS only. Ears, noise, and turn settings come from the worker. The example file hears with OpenAI.

**Files likely touched**

- `agent/.env` (local only — do not commit)
- `agent/.env.example` (comments only if you add a “demo worker” pointer; do not change the example default to Scribe unless the team agrees the example should match the demo)
- No application logic

**Steps**

1. On the machine that runs the worker, set the agent names in the pre-flight table. Do not copy values into git.
2. Confirm server `V2_AGENT_NAME`, `V2_INTERNAL_SECRET`, and LiveKit names match.
3. Restart **that** worker. A second leftover worker with `STT_PROVIDER=openai` will steal jobs.
4. Confirm only one worker is connected for `interview-v2`.

**Approach check**

- Try: the pre-flight table.
- Check: next job’s first log lines match P1-02. Server line `[v2] start interview=<id> avatar=false tts=elevenlabs voice=cascade`.
- Failure: if you cannot restart the worker that LiveKit dispatches, stop. Do not test against a worker you cannot read logs for.

**Done when:** The running worker’s env matches the table and a new join is dispatched to it. Status stays Not started until a person has confirmed the running process, not the example file.

---

### P1-02 — Startup log gate

**Critical path:** Yes  
**Status:** Not started  
**Why:** Voice feedback on the wrong stack wastes the dry run. One short call proves ears, mouth, noise, and turns together.

**Files likely touched**

- None if logs already match. Read `agent/main.py` (`entrypoint` cascade branch), `agent/providers/factory.py`.

**Steps**

1. Complete P1-01. Open `/elevenlabs-interviewer`. Join in Hindi with any name. Wait until you hear a greeting.
2. End the call from the UI so the room does not sit in grace. This call is not the dry run.
3. Collect the log lines below for that interview id.

**Approach check — all of these must appear**

| Signal | Exact log to find |
| --- | --- |
| Job | `job <id> avatar=False tts=elevenlabs voice=cascade` |
| Scribe | `ElevenLabs Scribe STT model=scribe_v2_realtime lang=hi secondary=['en']` and `commit=server_vad silence=1.0s` and `aligned=` true |
| STT ready | `STT ready provider=elevenlabs_scribe` and `aligned_transcript=True` |
| Mouth | `ElevenLabs TTS voice=<one id> lang=hi model=eleven_v4_turbo` |
| TTS ready | `TTS ready provider=elevenlabs` and the same voice id |
| Noise plugin | `noise cancellation: Krisp BVC (background voice + noise)` |
| Noise applied | `inbound audio noise_cancellation=on provider=krisp` |
| Turns | `turn handling:` with `endpointing` mode `dynamic`, `max_delay` `2.3`, `interruption=adaptive`, `preemptive=False` |
| Detector | The `detector=` value is not the bare word `vad`. If you see `Turn detector unavailable; using VAD turn detection`, this row fails |
| Session event | `voice.session_config` payload: `stt_provider` `elevenlabs_scribe`, `tts_provider` `elevenlabs`, `interruption_mode` `adaptive`, `preemptive_generation` false, `voice_expressiveness` `engine` |

**Failure handling**

| Log | Action |
| --- | --- |
| `elevenlabs_scribe STT failed` or `STT ready provider=openai` | Stop. P1-04. Do not score. |
| `falling back to OpenAI TTS` or `TTS ready provider=openai` | Stop. P1-03. |
| `Krisp NC only` or `Krisp noise cancellation unavailable` or `NOISE_PROVIDER=none` | Stop. P1-05. |
| `avatar=True` | You opened the wrong route. Use `/elevenlabs-interviewer` with no avatar flag. |
| `voice=gpt_live` | Wrong URL. |
| Turn detector unavailable | Fix the LiveKit inference plugin on this worker. Do not switch URLs. |

**Done when:** One interview id has every row in the table, and none of the failure lines. Paste the interview id into the status notes at the top (id only).

---

### P1-03 — Fail closed when ElevenLabs TTS cannot start

**Status:** Not started  
**Why:** `build_tts` in `agent/providers/factory.py` logs `TTS_PROVIDER=elevenlabs but no ELEVENLABS_API_KEY; falling back to OpenAI TTS` and continues. The route flag does not guarantee an ElevenLabs voice. A scored demo must not do that.

**Files likely touched**

- `agent/providers/factory.py` (`build_tts`, the `provider == "elevenlabs"` branch)
- `agent/main.py` only if you prefer the cascade entry to refuse after `build_tts` returns a non-ElevenLabs class when `tts_override == "elevenlabs"`

**Steps**

1. When the override or resolved provider is `elevenlabs` and neither `ELEVENLABS_API_KEY` nor `ELEVEN_API_KEY` is set, raise or return a controlled session failure. Do not call OpenAI TTS.
2. Log a single error that includes the words `falling back` must **not** be the success path. Suggested line: `ElevenLabs TTS required but API key missing; refusing session`.
3. The candidate should see the existing connect error path (`useLiveKitInterview` phase `error`) or a spoken nothing and a dead room — not a different voice. Prefer failing in `entrypoint` before `session.start` so the UI does not sit in **Live** with the wrong mouth.
4. `TTS_FALLBACK_ON_ERROR=google` must not run for this locked route. `agent/main.py` already comments that `/elevenlabs-interviewer` never mid-call Chirp-falls-back (`_tts_locked_el`). Keep that. This task is the **missing key at startup**, which is a different branch.

**Approach check**

- Try: start a worker with the ElevenLabs key name empty and `ttsProvider: "elevenlabs"`.
- Check: log contains the refuse line. There is no `TTS ready provider=openai`. The room does not greet in an OpenAI voice.
- Failure: if you cannot distinguish “key missing” from a LiveKit outage, keep the refuse log unique and stop the session. Do not reintroduce the OpenAI fallback “just for local”.

**Done when:** A missing key refuses the session, and a present key still prints `TTS ready provider=elevenlabs` with `model=eleven_v4_turbo`.

---

### P1-04 — Fail closed when Scribe falls back

**Status:** Not started  
**Why:** `build_stt` catches Scribe build errors, logs `elevenlabs_scribe STT failed (...); fallback=openai`, and continues on OpenAI. The URL cannot tell.

**Files likely touched**

- `agent/providers/factory.py` (`build_stt`, `provider == "elevenlabs_scribe"`)
- `agent/main.py` cascade branch, after `build_stt`, if you check `settings.resolved_stt()` and the actual class

**Steps**

1. For the demo worker, if Scribe fails to build, do not call `build_openai_stt`. Log `Scribe STT required but failed; refusing session` and include the exception text (no secrets).
2. Leave `STT_SCRIBE_FALLBACK` in config for non-demo workers if you need a flag. The demo path (`resolved_stt() == "elevenlabs_scribe"`) refuses instead of falling back.
3. Restart and confirm P1-02 still shows `STT ready provider=elevenlabs_scribe`.

**Approach check**

- Try: temporarily point Scribe at a bad key in a throwaway shell (do not commit), join once.
- Check: refuse log, no `STT ready provider=openai`.
- Failure: if the plugin fails only after the websocket opens (first utterance), treat the first `elevenlabs_scribe STT failed` as the same stop. End the call and do not fill the feedback sheet.

**Done when:** A Scribe build failure refuses the session, and a good key still produces the P1-02 Scribe lines.

---

### P1-05 — Require Krisp BVC, not NC-only

**Status:** Not started  
**Why:** The factory falls through BVC → NC → None and still starts the interview. NC-only will transcribe the television. The noise station is invalid without BVC.

**Files likely touched**

- `agent/providers/factory.py` (`build_noise_cancellation`)
- `agent/main.py` where `noise = build_noise_cancellation(settings)` is applied to room input

**Steps**

1. When `NOISE_PROVIDER=krisp` and `BVC` is missing or throws, log `Krisp BVC required but unavailable; refusing session` and do not start the cascade. Do not substitute `NC()`.
2. Keep the success line exactly: `noise cancellation: Krisp BVC (background voice + noise)`.
3. Do not change browser constraints in this task (that is P1-06).
4. Do not set a second Scribe background filter.

**Approach check**

- Try: normal worker after the plugin is installed. Optional negative try: a venv without the BVC export, if you can do that without breaking the shared environment. If you cannot simulate NC-only safely, code-read the branch and rely on the positive log.
- Check: P1-02 noise rows. Negative try does not print `Krisp NC only` and then greet.
- Failure: plugin cannot build BVC on this machine. Stop. Fix the LiveKit Krisp plugin install. Do not set `NOISE_PROVIDER=aicoustics` or `none` to unblock the demo.

**Done when:** The demo worker either logs the BVC line and joins, or refuses before greeting. It never greets on NC-only.

---

### P1-06 — Confirm the published mic leaves noise suppression off

**Status:** Not started  
**Why:** LiveKit’s rule is one enhancer. The agent runs Krisp. Stacking browser suppression makes BVC worse.

**Files likely touched**

- `client/src/v2/hooks/useLiveKitInterview.ts` (the `setMicrophoneEnabled` constraints — already `noiseSuppression: false`)
- `client/src/v2/components/PreflightCheck.tsx` (simple mode uses `noiseSuppression: true` and then `track.stop()`)

**Steps**

1. Do not change the live constraints if they are still `echoCancellation: true`, `noiseSuppression: false`, `autoGainControl: true`.
2. Confirm the candidate join uses `<PreflightCheck simple />` and that `runSimple` stops every track before `onDone`. The probe must not be passed into `connect`.
3. In a live call, in the browser, inspect the published microphone track’s `getSettings()` or `getConstraints()`. `noiseSuppression` must be false. Echo cancellation stays true.
4. If a future change reuses the preflight stream, stop that change. The live room must call `setMicrophoneEnabled` itself.

**Approach check**

- Try: join `/elevenlabs-interviewer`, open the track settings.
- Check: `noiseSuppression === false` on the published track. Agent still logs BVC.
- Failure: if the published track has suppression on, set it false in `useLiveKitInterview.ts` only. Do not turn it on to “help” the noise station.

**Done when:** A live join shows browser noise suppression off on the published mic, and the preflight stream is stopped.

---

### P1-07 — Barge-in and endpointing station

**Critical path:** Yes  
**Status:** Not started  
**Why:** This is the voice-feel gate. Adaptive interruption is already wired. Phase 1 proves it on a Hindi call and changes at most one knob if it fails.

**Files likely touched**

- `agent/.env` only if a knob changes: `ENDPOINTING_MAX_DELAY` or `INTERRUPTION_MIN_WORDS`
- `agent/interview/turns.py` (read; do not add a second detector)
- `agent/providers/factory.py` only if P1-02 said turns are both late and chopped (`vad_silence_threshold_secs`, currently `1.0`)

**Steps**

1. Pass P1-02 first (`aligned_transcript=True`, `interruption=adaptive`, `preemptive=False`).
2. Join Hindi. After the greeting, during agent speech, say only “haan”. Then, on a later turn, interrupt with a real correction: “no, not Delhi, Noida” (use the city you actually said).
3. On a third turn, pause about two seconds mid-sentence and then finish the answer.
4. Apply **one** fix if needed, restart the worker, and rerun all three. Do not combine fixes.

**Approach check**

- Try: the three behaviours above. Leave `PREEMPTIVE_GENERATION=false`.
- Check:
  - “haan”: agent continues. Log `false interruption (resumed=True) — interviewer should continue` from `agent/interview/turns.py` (`TurnWatchdog._on_false_interruption`).
  - Correction: agent stops. Next user transcript line contains the correction. Next `move=` uses it (not a fresh topic).
  - Two-second pause: agent does not take the floor before you finish.
  - UI during a cable blip (optional): header text **Linking**, then **Live**. That is `reconnecting`. It is not this station’s failure.
- Failure:
  - Answers cut off, “haan” ignored correctly: set `ENDPOINTING_MAX_DELAY` to `3.0`, restart, rerun. If still cut off, `3.5`. Stop at `3.5`. Do not enable preemptive generation.
  - “haan” or a cough barges, alignment is true: set `INTERRUPTION_MIN_WORDS` to `3`, restart, rerun.
  - Alignment is false: stop. Return to P1-04 / P1-02. Do not tune min words.
  - Both late and chopped: change only Scribe `vad_silence_threshold_secs` from `1.0` to `0.6` in `build_elevenlabs_scribe_stt`, restart, rerun. Do not also change `ENDPOINTING_MAX_DELAY` in that same restart.
  - Double reply (two assistant lines, two `move=` for one user line): set `THINKING_FILLER_PROBABILITY=0` and confirm `VOICE_EARLY_FILLER=false`. If it still doubles, stop Phase 1 and do not start a speech-arbiter rewrite inside this task.

**Done when:** The three behaviours pass on one interview id after at most one knob change, and that knob is written in the sheet.

---

### P1-08 — Please-repeat ladder

**Status:** Not started  
**Why:** Unclear audio must not become a stored fact, and it must not loop forever. The ladder already exists in `InterviewFlow._unclear`.

**Files likely touched**

- `agent/interview/flow.py` (only if the live call fails the checks; do not retune caps preemptively)
- `server/v2/lib/blueprints/nursing.json` (`max_unclear_streak` is 3 — leave it)

**Steps**

1. On a Hindi call that passed P1-02, wait for a screening question (city or qualification).
2. Mumble once. Speak no city name.
3. Then say the city clearly.
4. On a later question, mumble enough times to hear a quieter-spot suggestion (streak reaches 3) **or** stop after you have seen `noise_help` once. You do not need to soft-skip every focus if `noise_help` already appeared and the next clear answer is stored.
5. Read `GET /api/v2/interview/:id` and the transcript.

**Approach check**

- Try: one mumble, one clear city, then a streak if the first mumble did not already move on.
- Check:
  - Log `move=ask_repeat` and the agent asks you to say it again. It does not guess the city.
  - After the clear repeat, `controller.flow` holds that city.
  - A longer streak logs `move=noise_help` (event `audio.noise_help` if you can see agent events) and then continues. `MAX_FOCUS_RETRIES` is 3 (`flow.py`); a stuck focus logs `focus.soft_skip` rather than infinite `ask_repeat`.
  - Transcript user line for the mumble is not copied into the slot as if it were the answer.
- Failure:
  - Invented city or phone: stop. Fix the noise path in `Director.decide` / `flow.noise_move`. Do not add a denoiser.
  - `ask_repeat` more than three times on the same question with no `noise_help` and no `focus.soft_skip`: stop. The streak or retry counter is not incrementing. Fix `_unclear` / `_bump_focus_retry`. Do not raise the cap.
  - BVC log was missing: this row is invalid. Return to P1-05.

**Done when:** One interview shows `ask_repeat` without an invented slot, and either `noise_help` or a clean recover-after-repeat. Note the id on the sheet.

---

### P1-09 — Rejoin the same interview within 120 seconds

**Critical path:** Yes  
**Status:** Not started  
**Why:** The agent already waits 120 seconds and repeats the last question. The browser treats a hard drop as ended and a refresh starts a new interview. The disconnect station cannot be scored until Rejoin exists.

**Files likely touched**

- `client/src/v2/hooks/useLiveKitInterview.ts`
- `client/src/v2/components/LiveInterview.tsx`
- `client/src/v2/V2TestPage.tsx`
- `server/v2/routes/interviewV2.ts`
- `server/v2/lib/livekit.ts`
- Read only: `agent/interview/liveness.py` (`ConnectionGuard`), `agent/interview/flow.py` (`resume`), `agent/main.py` (`close_on_disconnect: False`)

**Behaviour to build**

1. **Remember the live interview** in `sessionStorage` when `POST /api/v2/interview/start` succeeds on this page. Store interview id, candidate name, role title, language, LiveKit URL, and the first-join token only as a fallback. Store `droppedAt` as null while the call is up.
2. **Clock starts at disconnect, not at start.** A ten-minute call must still have 120 seconds after a refresh. On refresh, the new page load is the drop: if storage has an interview and `droppedAt` is null, set `droppedAt` to now.
3. **Same-page hard drop.** `ConnectionState.Disconnected` already sets the hook phase to `ended`. `V2TestPage` phase stays `live`, so `LiveInterview` stays mounted and the header shows the raw phase `ended`. Add a **Rejoin** button in that state. Do not call `onEnded` / `endAndScore`. The existing End control is the only path to the scorecard.
4. **`reconnecting` is not a drop.** Header stays **Linking**. No Rejoin button. LiveKit is still in the room.
5. **Refresh.** Setup screen sees storage, shows the interview id, a countdown of `120 - (now - droppedAt)` seconds, and Rejoin as the primary action. “Start a new interview” is secondary and warns that it abandons the old id (clears storage, then the normal Join form).
6. **Rejoin must not `POST /start`.** Add `POST /api/v2/interview/:id/rejoin` (name it clearly). It loads the v2 record, reads `extras.roomName` (shape `interview-v2-<id>`), and refuses when `controller.completed` is true or when `droppedAt` is irrelevant server-side: refuse when the interview is already completed. Mint a candidate token with the **same identity** start already uses: `candidate-<interviewId slice 0, 8>` in `server/v2/routes/interviewV2.ts`. Grants: `roomJoin`, publish, subscribe, for that room only.
7. **No second agent.** `createCandidateToken` sets `RoomConfiguration` with `RoomAgentDispatch`. The rejoin token must omit `roomConfig` agents. `ensureRoomAndDispatch` already returns early when a dispatch for `V2_AGENT_NAME` exists; do not call `createDispatch` on rejoin. First join is unchanged.
8. **Client connect.** Call the existing `connect({ url, token })` with the rejoin token. Same mic constraints as P1-06. Do not clear captions if you are still on `LiveInterview`; after a refresh, captions start empty and that is acceptable. Flow state is on the server, not in the captions.
9. **Agent, do not rewrite.** On return, `ConnectionGuard._on_connected` cancels the grace task and `speak_move(flow.resume())`. You should hear a short welcome plus the last question. Log already: `candidate disconnected; waiting 120s for them to return`. Move kind `resume`. Event `flow.resumed`.
10. **After 120 seconds** the agent logs `candidate did not return; ending interview as incomplete` and completes without speaking. The button hides. A late POST rejoin returns 409 (or 410) with a stable error string `rejoin_window_closed`. The UI tells the tester to start a new interview. Do not attach them to the old room.
11. **Unmount.** The hook’s cleanup calls `disconnect()` on unmount. That is correct for a refresh. Do not also fire `endAndScore` from that cleanup.
12. Scope the storage key to this route, for example `interviewai.elevenlabs.rejoin`, so `/gpt-live-interviewer` is untouched.

**Approach check**

- Try: join, answer one screening question, note the id, refresh, press Rejoin before 120 seconds. Second try: refresh and wait out the countdown.
- Check:
  - Same id in the UI, in `GET /api/v2/interview/:id`, and in the agent log.
  - `controller.flow` still has the screening answer.
  - Agent log includes `waiting 120s` and then a `move=resume` (or `speak` of the resume move). One voice, no second greeting from a second worker.
  - LiveKit room has one agent participant. If two speak, the token still dispatched.
  - Scorecard does not show until End.
  - After 120 seconds: `candidate did not return; ending interview as incomplete`. Rejoin hidden. Next Start is a new id.
- Failure:
  - New id on refresh: the button is still calling `POST /start`. Fix the client. Do not score station 6.
  - Two agents: strip dispatch from the rejoin token and retest. Do not “fix” it by setting `close_on_disconnect` true.
  - `persisting flow state failed`: stop. Fix `_persist` before more Rejoin UI work. Do not add a new session store.
  - Resume has no last question: `flow.state.last_question` was empty. Check that a real screening turn happened before the drop.
  - Rejoin succeeds after the agent logged incomplete: the API did not check `controller.completed`. Return 409.

**Done when:** The refresh script in the test matrix passes on one id, and the expired-window script ends that same id incomplete.

---

### P1-10 — Show the interview id and do not score a drop

**Status:** Not started  
**Why:** The sheet is useless without the id. Scoring on disconnect would classify a half call and fight Rejoin.

**Files likely touched**

- `client/src/v2/components/LiveInterview.tsx` (header next to the Live / Linking chip)
- `client/src/v2/V2TestPage.tsx` (`endAndScore` stays on the End button only)

**Steps**

1. Render `session.id` in the live header, selectable text, label “Interview id”.
2. Confirm `endInterview` is the only caller of `onEnded`. A `Disconnected` phase must not call it. P1-09’s Rejoin button must not call it.
3. After a successful End, clear the rejoin `sessionStorage` key, then run the existing summary and transcript fetch.

**Approach check**

- Try: join and read the id without opening devtools. Kill the network briefly.
- Check: id is on screen. Phase becomes `ended` or **Linking**, and the scorecard route does not appear. End still shows `ScorecardView` and the transcript download.
- Failure: if End no longer scores, you hooked `onEnded` to the wrong event. Restore End → `endAndScore`.

**Done when:** The id is visible for the whole live call, drops do not open the scorecard, and End still does.

---

### P1-11 — One persona per language, stable inside that call

**Status:** Not started  
**Why:** Each language needs its own voice, and a call that stays in one language must not swap speakers. A mid-call `switch_language` may change to the other language’s persona. That is the map working, not a bug.

**Files likely touched**

- `agent/providers/elevenlabs_voices.py` (`elevenlabs_voice_for`)
- Agent env: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_VOICE_ID_LOCAL`, `ELEVENLABS_VOICE_BY_LANG` (local only — do not commit)

**Steps**

1. Keep the two default voice id names equal, so a missing map entry has one fallback.
2. On a single-language call, copy `voice=` from `ElevenLabs TTS voice=` and from `TTS ready`.
3. They match, `model=eleven_v4_turbo`, and `lang=` is that join’s short code.
4. Per-language ids are chosen in P1-12. This task only proves one call keeps one id.

**Approach check**

- Try: one greeting in a single language. Do not ask to switch.
- Check: one voice id in both log lines. Transcript has no spoken audio-tag brackets.
- Failure: two ids with no language switch, or `model` is not `eleven_v4_turbo`. Fix the map so that code has one id, and restart. If tags are spoken aloud, confirm `VOICE_EXPRESSIVENESS=engine`. If they are still spoken, set expressiveness off for the demo rather than letting the LLM invent tags. Record which choice you shipped.

**Done when:** One single-language interview id shows one voice id and `eleven_v4_turbo`.

---

### P1-12 — Record the voice map and Odia language code

**Critical path:** Yes  
**Status:** Not started  
**Why:** The worker can already speak every join language through one ElevenLabs model, but it uses one shared voice id and sends Odia as `od`. Phase 1 needs a recorded id per language and a language code ElevenLabs accepts.

**Files likely touched**

- `agent/providers/elevenlabs_voices.py` (`elevenlabs_language`, `elevenlabs_voice_for`)
- `agent/providers/factory.py` (`_scribe_language_hints`, `build_tts` ElevenLabs branch)
- `agent/config.py` (comment on `elevenlabs_voice_by_lang` only; do not invent new default ids)
- `client/src/v2/components/LanguagePicker.tsx` (read the fallback; change it only if the languages API cannot be made to return the full list)
- `server/v2/lib/types.ts` (`SUPPORTED_LANGUAGES` — read; the eleven codes are already there)
- Agent env `ELEVENLABS_VOICE_BY_LANG` (local, do not commit)

**Steps**

1. Confirm `GET /api/v2/interview/languages` returns `en-IN`, `hi-IN`, `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN`, `od-IN`. If the picker shows only the six fallback options, the API failed. Fix that before any station that is missing from the fallback.
2. Map `od-IN` to ElevenLabs TTS language `or` inside `elevenlabs_language`. Leave every other short code as the first subtag (`en`, `hi`, `ta`, `te`, `kn`, `ml`, `mr`, `bn`, `gu`, `pa`). Those match the ElevenLabs models doc for `eleven_v4_turbo`.
3. Map the Odia Scribe hint off `od`. First try `or`. If Scribe errors or the transcript is another language, try `ori` once (the code on ElevenLabs’ Scribe language list). Record which hint the log accepted. Do not turn on auto-detect.
4. Set `ELEVENLABS_VOICE_BY_LANG` with one entry per code. Start every entry from the checked-in id `4mCfn38CsM9hGLvDrPxv` so a join is not silent. Replace an entry only after that language’s listen, and write the id in the voice-map table in this file. If you have not chosen a replacement, leave the cell as `TBD id`. Do not type a made-up id. Do not copy Sarvam speaker names (`ishita`, `priya`, `pooja`, `roopa`, `ritu`) into this variable.
5. Do not change `ELEVENLABS_MODEL` away from `eleven_v4_turbo`. Do not add voice cloning.

**Approach check**

- Try: a throwaway join in Hindi and a throwaway join in Odia after the map change. End both immediately.
- Check: Hindi log `lang=hi` and Odia log `lang=or` (TTS) with Scribe `lang=or` or `lang=ori`, both `model=eleven_v4_turbo`, both `TTS ready provider=elevenlabs`.
- Failure: `lang=od` on the Odia call means the map did not land. Fix `elevenlabs_language` and rerun Odia only. A missing picker option is the languages API, not a new language to add.

**Done when:** The voice-map table below has a row for all eleven codes, Odia no longer logs `od`, and `ELEVENLABS_VOICE_BY_LANG` has one entry per code. Ids may still say `TBD id` until that language’s task hears them.

**Voice map (update the id cell when a listen locks it)**

| Code | Persona | TTS language | Scribe hint | Voice id |
| --- | --- | --- | --- | --- |
| `en-IN` | Indian-accent English | `en` | `en`, no secondary | TBD id |
| `hi-IN` | Hindi | `hi` | `hi`, secondary `en` | TBD id |
| `te-IN` | Telugu | `te` | `te`, secondary `en`, `hi` | TBD id |
| `ta-IN` | Tamil | `ta` | `ta`, secondary `en`, `hi` | TBD id |
| `kn-IN` | Kannada | `kn` | `kn`, secondary `en`, `hi` | TBD id |
| `ml-IN` | Malayalam | `ml` | `ml`, secondary `en`, `hi` | TBD id |
| `bn-IN` | Bengali | `bn` | `bn`, secondary `en`, `hi` | TBD id |
| `mr-IN` | Marathi | `mr` | `mr`, secondary `en`, `hi` | TBD id |
| `gu-IN` | Gujarati | `gu` | `gu`, secondary `en`, `hi` | TBD id |
| `pa-IN` | Punjabi | `pa` | `pa`, secondary `en`, `hi` | TBD id |
| `od-IN` | Odia | `or` | `or`, or `ori` if `or` fails | TBD id |

Starting listen for every row is the checked-in id `4mCfn38CsM9hGLvDrPxv`. Replace the cell when the listen fails. OpenAI fallback, if a later task needs it, is `gpt-4o-mini-tts` voice `alloy` on `/v2/test`, not on this URL.

**Language station procedure (P1-13 through P1-23)**

1. Join `/elevenlabs-interviewer` in that code. Wait for the greeting.
2. Say one screening sentence in that language. Leave one English word such as ICU in Latin script.
3. Read the agent log for that interview id.
4. End the call. Do not score diaper care or the tier.

---

### P1-13 — English, Indian accent (`en-IN`)

**Critical path:** Yes  
**Status:** Not started  
**Why:** English is in the client list and in `SUPPORTED_LANGUAGES`. The plugin is called with `language="en"`, so the accent comes from the voice id, not from the locale `en-IN`.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `en` or `en-IN` entry)
- Read: `agent/providers/factory.py` (`build_tts`), `agent/interview/language.py` (`native_script_reminder` already says “Respond in clear Indian English.”)

**Steps**

1. Complete P1-12. Follow the language station procedure for `en-IN`.
2. Say: “I live in Delhi. I finished BSc nursing in 2019.”
3. If the greeting is American or British, replace the `en` voice id, record it in the voice map, restart, and rerun this task only.

**Approach check**

- Try: one English join.
- Check: you hear Indian English. Log `lang=en`, Scribe `lang=en` with no secondary, `model=eleven_v4_turbo`, one voice id. The transcript contains Delhi and 2019 as you said them.
- Failure: Western accent → new ElevenLabs id, not a prompt rewrite and not GPT-Live. Silent or `TTS ready provider=openai` → P1-03. Transcript in another language → section 3.7 of the plan (OpenAI STT on `/v2/test`, then Sarvam only if that also fails). Do not empty the ElevenLabs key to force OpenAI TTS.

**Done when:** One `en-IN` interview id is Indian-accent English, Scribe kept the sentence, and the voice-map cell is either the checked-in id or a real id you wrote down.

---

### P1-14 — Hindi (`hi-IN`)

**Critical path:** Yes  
**Status:** Not started  
**Why:** Hindi is the form default and the cascade proof language. It still needs its own persona and a Scribe hint of `hi` plus secondary `en`, so Hinglish is not treated as a language flip.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `hi` or `hi-IN` entry)
- Read: `agent/providers/factory.py` (`_scribe_language_hints`)

**Steps**

1. Follow the language station procedure for `hi-IN`.
2. Say: “main Delhi mein rehti hoon, BSc nursing 2019”.
3. On this same call you may also run barge-in, please-repeat, and Rejoin if P1-07, P1-08, and P1-09 are ready. Those rows do not have to be repeated on every language.

**Approach check**

- Try: the Hinglish sentence above.
- Check: greeting is Hindi. Log `lang=hi`, Scribe `secondary=['en']`, same voice id in both TTS lines. Transcript keeps the Hinglish line rather than translating it. One English word does not log `language.switched`.
- Failure: wrong language or silence → section 3.2 of the plan (new id, or Odia-style code check does not apply here). Wrong transcript language → OpenAI STT comparison, then Sarvam. A voice-id change with no switch → P1-11.

**Done when:** One `hi-IN` interview shows a Hindi persona, Scribe hint `hi`, and the Hinglish sentence stored as spoken.

---

### P1-15 — Telugu (`te-IN`)

**Critical path:** Yes  
**Status:** Not started  
**Why:** Telugu is the South Indian live station for the dry run. The turn detector does not cover it, so endpointing uses `ENDPOINTING_MIN_DELAY_UNCOVERED` (0.55). Do not retune that in this task unless the greeting never arrives.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `te` or `te-IN` entry)
- Read: `agent/interview/turns.py`, `agent/providers/factory.py`

**Steps**

1. Follow the language station procedure for `te-IN`. This is a fresh join, not only a mid-call switch from Hindi.
2. Say one screening sentence in Telugu and leave ICU in Latin script.
3. Confirm the picker offers Telugu (it is in the fallback list).

**Approach check**

- Try: the Telugu sentence.
- Check: log `lang=te`, Scribe `lang=te` secondary `['en', 'hi']`, `model=eleven_v4_turbo`, voice id is the Telugu cell. You hear Telugu. The transcript has Telugu script plus Latin ICU.
- Failure: agent speaks Hindi or English → replace the `te` voice id and rerun. `lang=` is not `te` → the join code was wrong. Transcript is another language → OpenAI STT, then Sarvam. Do not lower the uncovered endpointing delay in the same restart as a voice-id change.

**Done when:** One fresh `te-IN` join is heard in Telugu and transcribed with the Telugu hint.

---

### P1-16 — Tamil (`ta-IN`)

**Status:** Not started  
**Why:** Tamil is on the client list and in both `SUPPORTED_LANGUAGES` and the picker fallback. Wiring it is required. A full live answer may be a spot-check unless the Hindi call’s optional switch used Tamil.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `ta` or `ta-IN` entry)
- Read: `agent/main.py` (`switch_language`, `_switch_tts_language`)

**Steps**

1. Follow the language station procedure, or, if you already switched into Tamil on the Hindi call, still confirm a startup log with `lang=ta` on some join (the switch log is extra evidence, not a substitute for `lang=ta`).
2. Say one screening sentence in Tamil with ICU in Latin script.
3. If you test the switch: ask out loud to continue in Tamil. Expect `language.switched` and the Tamil voice id. The same question continues.

**Approach check**

- Try: a Tamil greeting plus one sentence.
- Check: Scribe `lang=ta` secondary `['en', 'hi']`, one Tamil voice id, Tamil heard, transcript not flipped by the word ICU.
- Failure: same as Telugu, with code `ta`. A switch that starts a new topic is a Flow note for Phase 2, not a reason to change brains in this task. Fix the voice or the ear first.

**Done when:** Tamil is wired: voice-map cell filled after a listen, and a log shows `lang=ta` with Scribe `lang=ta`. A spot-check sentence is enough if the dry-run note says who heard it.

---

### P1-17 — Kannada (`kn-IN`)

**Status:** Not started  
**Why:** Kannada is in `SUPPORTED_LANGUAGES` and in the picker fallback. Phase 1 is not a Hindi-only station.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `kn` or `kn-IN` entry)
- Read: `agent/providers/factory.py`

**Steps**

1. Follow the language station procedure for `kn-IN`.
2. Say one screening sentence in Kannada with ICU in Latin script.
3. A short greeting plus the log is enough for wiring. Stay for the full sentence if someone who speaks Kannada is on the call.

**Approach check**

- Try: join `kn-IN`.
- Check: `lang=kn`, Scribe `lang=kn` secondary `['en', 'hi']`, `eleven_v4_turbo`, one voice id, Kannada heard.
- Failure: wrong language heard → new id for `kn` only. Wrong transcript → OpenAI STT on `/v2/test`, then Sarvam. Silent → confirm the key and `TTS ready provider=elevenlabs` before changing ids.

**Done when:** The Kannada voice-map cell is a real id or an explicit “kept the starting id” after a listen, and a log shows the Kannada hint.

---

### P1-18 — Malayalam (`ml-IN`)

**Status:** Not started  
**Why:** Malayalam is in the client list, the picker fallback, and `SUPPORTED_LANGUAGES`. Sarvam’s older Bulbul does not matter unless both ElevenLabs and OpenAI fail this station.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `ml` or `ml-IN` entry)
- Read: `agent/interview/language.py` (Sarvam speaker `pooja` is not an ElevenLabs id)

**Steps**

1. Follow the language station procedure for `ml-IN`.
2. Say one screening sentence in Malayalam with ICU in Latin script.
3. Do not set `TTS_PROVIDER=sarvam` on the demo worker.

**Approach check**

- Try: join `ml-IN`.
- Check: `lang=ml`, Scribe `lang=ml` secondary `['en', 'hi']`, Malayalam heard, one voice id.
- Failure: same pattern as Kannada. Sarvam speaker `pooja` is allowed only inside a section 3.7 comparison after OpenAI STT has also failed.

**Done when:** Malayalam is wired the same way as Kannada: listen recorded, hint `ml` in a log.

---

### P1-19 — Bengali (`bn-IN`)

**Status:** Not started  
**Why:** Bengali is on the client list and in `SUPPORTED_LANGUAGES`. It is not in the picker fallback, so this task also proves the languages API.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `bn` or `bn-IN` entry)
- `client/src/v2/components/LanguagePicker.tsx` and `server/v2/routes/interviewV2.ts` (the `GET /languages` handler) only if Bengali is missing from the select

**Steps**

1. Confirm the picker lists Bengali after the languages request. If it does not, fix the API. Do not add a second language list by hand unless the API cannot be reached.
2. Follow the language station procedure for `bn-IN`.
3. Say one screening sentence in Bengali with ICU in Latin script.

**Approach check**

- Try: join `bn-IN` from the picker, not a hardcoded request.
- Check: `lang=bn`, Scribe `lang=bn` secondary `['en', 'hi']`, Bengali heard.
- Failure: option missing → API, not “drop Bengali”. Wrong voice or transcript → the same ElevenLabs-then-OpenAI-then-Sarvam order.

**Done when:** Bengali is selectable, the voice-map cell is filled after a listen, and a log shows `lang=bn`.

---

### P1-20 — Marathi (`mr-IN`)

**Status:** Not started  
**Why:** Marathi is on the client list and in `SUPPORTED_LANGUAGES`. It shares Devanagari with Hindi, so the script detector in `language.py` prefers `hi-IN` when the counts tie. The join hint must stay `mr` or a Marathi call will be logged as Hindi.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `mr` or `mr-IN` entry)
- Read: `agent/interview/language.py` (`detect_script_language`), `agent/providers/factory.py`

**Steps**

1. Confirm Marathi is in the picker via the languages API (it is not in the fallback).
2. Follow the language station procedure for `mr-IN`.
3. Say one screening sentence in Marathi with ICU in Latin script.

**Approach check**

- Try: join `mr-IN`.
- Check: Scribe `lang=mr` secondary `['en', 'hi']`, TTS `lang=mr`. A `language.detected` log of `hi-IN` must not retarget STT by itself.
- Failure: hint flips to `hi` without `switch_language` → stop and fix the retarget. Do not “solve” it by using the Hindi voice. Wrong mouth → new `mr` id.

**Done when:** A `mr-IN` join logs `lang=mr` for TTS and Scribe, and the voice-map cell is filled after a listen.

---

### P1-21 — Gujarati (`gu-IN`)

**Status:** Not started  
**Why:** Gujarati is in `SUPPORTED_LANGUAGES` and `PROFILES`, which is the product list Phase 1 has to cover. It is not in the picker fallback.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `gu` or `gu-IN` entry)
- `client/src/v2/components/LanguagePicker.tsx` only if the languages API does not add Gujarati

**Steps**

1. Confirm Gujarati is in the picker after the languages request.
2. Follow the language station procedure for `gu-IN`.
3. Say one screening sentence in Gujarati with ICU in Latin script.

**Approach check**

- Try: join `gu-IN`.
- Check: `lang=gu`, Scribe `lang=gu` secondary `['en', 'hi']`, Gujarati heard, one voice id.
- Failure: missing option → API. Wrong voice → new `gu` id. Wrong transcript → OpenAI STT, then Sarvam.

**Done when:** Gujarati is selectable, wired to a heard voice id, and a log shows `lang=gu`.

---

### P1-22 — Punjabi (`pa-IN`)

**Status:** Not started  
**Why:** Punjabi is in `SUPPORTED_LANGUAGES`. The short code `pa` matches ElevenLabs TTS. Scribe’s published list uses `pan`; the realtime API accepts ISO 639-1 or 639-3, so try `pa` first and do not change it unless that station fails.

**Files likely touched**

- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `pa` or `pa-IN` entry)
- `agent/providers/factory.py` (`_scribe_language_hints`) only if `pa` is rejected
- Picker files only if Punjabi is missing after the languages API

**Steps**

1. Confirm Punjabi is in the picker after the languages request.
2. Follow the language station procedure for `pa-IN`.
3. Say one screening sentence in Punjabi with ICU in Latin script.

**Approach check**

- Try: join `pa-IN`.
- Check: TTS `lang=pa`, Scribe `lang=pa` secondary `['en', 'hi']`, Punjabi heard.
- Failure: Scribe error on `pa` → one retry with hint `pan`, record which hint worked. Do not also change the voice id in that restart. Wrong voice after a good hint → new `pa` id.

**Done when:** Punjabi is selectable, the hint that worked is written in the voice map, and a log shows that hint.

---

### P1-23 — Odia (`od-IN`)

**Status:** Not started  
**Why:** Odia is in `SUPPORTED_LANGUAGES` as `od-IN`. ElevenLabs TTS documents Odia as `or`. Scribe’s list uses `ori`. The worker sends `od` until P1-12 maps it. This task checks the mapped station, not the old code.

**Files likely touched**

- `agent/providers/elevenlabs_voices.py` (`elevenlabs_language`)
- `agent/providers/factory.py` (`_scribe_language_hints`)
- Agent env `ELEVENLABS_VOICE_BY_LANG` (the `or` or `od-IN` entry — match whatever key `elevenlabs_voice_for` sees after the map)
- Picker files only if Odia is missing after the languages API

**Steps**

1. Confirm P1-12 has landed and Odia is in the picker via the languages API.
2. Follow the language station procedure for `od-IN`.
3. Say one screening sentence in Odia with ICU in Latin script.
4. If Scribe rejects `or` or transcribes another language, change only the Scribe hint to `ori`, restart, and rerun.

**Approach check**

- Try: join `od-IN`.
- Check: TTS `lang=or`, Scribe `lang=or` or `lang=ori`, Odia heard, not Hindi. `lang=od` is a fail.
- Failure: `lang=od` → return to P1-12. Wrong voice with `lang=or` → new id. Both Scribe hints fail → OpenAI STT on `/v2/test`, then one Sarvam comparison (`bulbul:v3`, speaker `ritu`). Then restore the demo worker to Scribe and ElevenLabs.

**Done when:** An Odia join logs TTS `lang=or` and a Scribe hint of `or` or `ori`, the voice-map cell records the id and the hint, and the sentence is stored in Odia.

---

### P1-24 — Dry-run the Phase 1 matrix and fill the sheet

**Critical path:** Yes  
**Status:** Not started  
**Why:** Phase 1 exits on scored calls, not on code landing. The dry run is English, Hindi, and Telugu live, plus a wiring check for the other languages.

**Files likely touched**

- None, unless a row fails and you return to the task named in that row.
- Write results under “Dry-run record” at the bottom of this file (interview ids and pass/fail only).

**Steps**

1. P1-01 through P1-23 are Done or explicitly N/A with a log quote (P1-03 and P1-04 negative tests can be Done before the dry run). P1-16 through P1-23 may be Done on a wiring log plus a spot-check note.
2. Three live interviews: `en-IN`, `hi-IN`, `te-IN`. On Hindi, also run matrix rows A–K. On English, run the language row and the short backchannel “okay” if you have time. On Telugu, run the language row.
3. For Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, and Odia, confirm the voice-map id and a log line. Spot-check any you can. Do not block the exit on a missing native speaker if the log and a listen of the greeting passed.
4. Fill the sheet columns. End the call only after the rows that need a scorecard (none of the Phase 1 rows require the tier except “End still works”, which is one extra press at the end of the Hindi call).
5. If a row fails, apply that row’s next action, restart if the action was a config change, and rerun **that row**. Do not rerun the whole matrix unless the worker was restarted.

**Approach check**

- Try: English, Hindi, and Telugu live, then the wiring checklist.
- Check: each live row’s pass signal, and a voice id plus Scribe hint for every other language.
- Failure: follow the row. If the next action says stop, leave P1-24 Blocked and do not open Phase 2.

**Done when:** English, Hindi, and Telugu live rows are Pass, every other language row is Pass or “wired, spot-check pending” with a log quote, and any Fail has a stop the team has accepted in writing in the dry-run record. A silent Fail does not count as Done.

---

## Manual test matrix (Phase 1 stations)

URL: `/elevenlabs-interviewer`. Record the interview id from the header (P1-10).

Rows A–K run on the **Hindi** live call. English and Telugu run their language rows live. The other language rows are wiring plus a spot-check.

| Row | Station | What you do | Pass signal | If it fails |
| --- | --- | --- | --- | --- |
| A | Stack | Join and wait for the greeting | P1-02 log set for this id. Header shows the id. One voice. | Return to the failed P1-02 line. Do not continue the matrix. |
| B | Published mic | In devtools, published mic settings | `noiseSuppression` false. Echo cancellation on. | P1-06. |
| C | Backchannel | Say only “haan” while the agent is speaking | Speech continues. Log `false interruption (resumed=True)`. | P1-07. One knob, then this row only. |
| D | Real barge-in | Interrupt with “no, not Delhi, Noida” | Agent stops. Transcript has the correction. Next `move=` uses it. | P1-07. |
| E | Pause | Pause ~2s mid-answer, then finish | Agent does not take the floor during the pause. | Raise `ENDPOINTING_MAX_DELAY` once (P1-07). If Scribe and LiveKit both feel late **and** chopped, change only `vad_silence_threshold_secs`. |
| F | Please-repeat | Mumble a screening answer, then say the city clearly | `move=ask_repeat`. No invented city. Clear repeat stored on `GET /api/v2/interview/:id` `controller.flow`. | P1-08. If the BVC line was absent, the row is invalid (P1-05). |
| G | Noise help | Mumble until it suggests a quieter place, or confirm you already saw `noise_help` | `move=noise_help` once, then it can continue. It does not stay on `ask_repeat` forever. | Fix `_unclear`. Do not raise `max_unclear_streak`. |
| H | Blip | Toggle network for a second without refreshing | Header **Linking**, then **Live**. Same id. No Rejoin required. | If it dead-ends, that is the Rejoin path (row I), not a brain bug. |
| I | Refresh rejoin | Answer one fact. Refresh. Rejoin within 120s | Same id. Last question repeated. Fact still on `controller.flow`. One agent voice. No scorecard. Log `waiting 120s` then resume. | P1-09. |
| J | Grace expiry | New call. Refresh. Wait past 120s. Do not rejoin | Log `candidate did not return; ending interview as incomplete`. Rejoin hidden or API `rejoin_window_closed`. | P1-09 server check. |
| K | End | Press End on a call you mean to finish | Scorecard and transcript download. Storage key cleared. | P1-10. |

Rows that are **not** Phase 1 and must not block this matrix: diaper-care refusal, partial clinical answer, scorecard tier quality. If you happen to hit them, note them and leave them for Phase 2. Tamil is in Phase 1 as row L-ta, not as a brain station.

### Language matrix

Voice provider for a Pass is ElevenLabs `eleven_v4_turbo` on this URL. Voice id stays `TBD id` until that task writes a real id into the P1-12 voice map. STT hint is what `_scribe_language_hints` sends after P1-12 (explicit hint, not auto).

| Row | Language | Live or wired | Voice provider | Voice name or id | STT language hint | Pass signal | If it fails |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L-en | English, Indian accent | Live | ElevenLabs `eleven_v4_turbo` | TBD id | `en`, no secondary | Indian accent. `lang=en`. Transcript has the English sentence. | New `en` id if the accent is Western. P1-03 if OpenAI TTS spoke the demo. OpenAI STT on `/v2/test` if the transcript language is wrong, then Sarvam. |
| L-hi | Hindi | Live | ElevenLabs `eleven_v4_turbo` | TBD id | `hi`, secondary `en` | Hindi greeting. Hinglish sentence stored. One English word does not switch language. | New `hi` id if the mouth is wrong. Ear fallback as in L-en. |
| L-te | Telugu | Live | ElevenLabs `eleven_v4_turbo` | TBD id | `te`, secondary `en`, `hi` | Telugu heard. Telugu script plus Latin ICU. `lang=te`. | New `te` id. Do not retune endpointing in the same restart. |
| L-ta | Tamil | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `ta`, secondary `en`, `hi` | `lang=ta` and Tamil heard on the greeting or on a switch from Hindi. | New `ta` id, then the ear fallback. |
| L-kn | Kannada | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `kn`, secondary `en`, `hi` | `lang=kn` and Kannada heard. | New `kn` id, then the ear fallback. |
| L-ml | Malayalam | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `ml`, secondary `en`, `hi` | `lang=ml` and Malayalam heard. | New `ml` id, then the ear fallback. Sarvam speaker `pooja` only after OpenAI STT fails. |
| L-bn | Bengali | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `bn`, secondary `en`, `hi` | Picker shows Bengali. `lang=bn`. Bengali heard. | If the option is missing, fix `GET /languages` before the voice. |
| L-mr | Marathi | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `mr`, secondary `en`, `hi` | `lang=mr` stays `mr`. Devanagari does not retarget to Hindi by itself. | Fix retarget before swapping the voice. |
| L-gu | Gujarati | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `gu`, secondary `en`, `hi` | Picker shows Gujarati. `lang=gu`. Gujarati heard. | Same order as Bengali. |
| L-pa | Punjabi | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `pa`, secondary `en`, `hi` | `lang=pa`. Punjabi heard. | If Scribe rejects `pa`, one retry with `pan`. |
| L-od | Odia | Wired, spot-check | ElevenLabs `eleven_v4_turbo` | TBD id | `or`, or `ori` if `or` fails | TTS `lang=or`. Not `od`. Odia heard. | P1-12 if `lang=od`. Then a new id. Then OpenAI STT, then Sarvam speaker `ritu`. |

### Feedback to write for each row

| Column | What to write |
| --- | --- |
| Row | A–K or a language row |
| Interview id | UUID from the header |
| Pass / Fail | One word, or “wired” for a spot-check language |
| Heard | One sentence |
| Transcript line | User or assistant quote |
| Voice | Provider and the id, or `TBD id` |
| STT hint | The `lang=` and `secondary=` from the log |
| Log | The `move=` or the startup line that decided the row |
| Next action | Blank on Pass. On Fail, the task id you returned to |

---

## Risks and stop conditions

Stop the phase. Do not “try GPT-Live quickly”. Do not make Sarvam the demo default. OpenAI STT and then Sarvam are allowed only as the written fallback for one failed language station, on `/v2/test`, and the demo worker goes back to Scribe.

| Condition | Stop and do this |
| --- | --- |
| Worker is the example file (`STT_PROVIDER=openai`) | P1-01. No calls count. |
| OpenAI TTS or OpenAI STT spoke a scored demo call | P1-03 / P1-04. Discard that interview id. A deliberate `/v2/test` comparison is not this row. |
| Log says `Krisp NC only` or Krisp unavailable | P1-05. Do not run rows F–G. |
| Turn detector unavailable on a Hindi call | Fix the plugin. Do not drop to a new turn model. Other languages already use the higher silence floor. |
| Two interviewers after Rejoin | Strip dispatch from the rejoin token. Retest row I before any other row. |
| `persisting flow state failed` | Fix persist. Rejoin cannot pass. |
| Please-repeat stores a fact you did not say | Fix Flow/Director. Do not add a second denoiser. |
| Double agent replies on more than one turn after fillers are off | Stop. Speech-arbiter rewrite is out of Phase 1. |
| `GET /api/roles` fails and Join never enables | Only then look at roles. Do not build invite tokens in this phase. |
| Odia logs `lang=od` | P1-12. Do not score L-od. |
| Someone starts scoring diaper care or the tier on this sheet | Park the note. It does not close or fail Phase 1. |

---

## Dry-run record

Fill this when P1-24 runs. Leave the template until then. Live calls are English, Hindi, and Telugu. Other language rows can be “wired” with a log quote.

| Row | Interview id | Pass / Fail | Note |
| --- | --- | --- | --- |
| A | | Not started | Hindi stack |
| B | | Not started | |
| C | | Not started | Hindi “haan” |
| D | | Not started | |
| E | | Not started | |
| F | | Not started | |
| G | | Not started | |
| H | | Not started | |
| I | | Not started | |
| J | | Not started | |
| K | | Not started | |
| L-en | | Not started | Live. Indian accent |
| L-hi | | Not started | Live |
| L-te | | Not started | Live. South Indian |
| L-ta | | Not started | Wired unless spot-checked |
| L-kn | | Not started | Wired unless spot-checked |
| L-ml | | Not started | Wired unless spot-checked |
| L-bn | | Not started | Wired unless spot-checked |
| L-mr | | Not started | Wired unless spot-checked |
| L-gu | | Not started | Wired unless spot-checked |
| L-pa | | Not started | Wired unless spot-checked |
| L-od | | Not started | Wired unless spot-checked. Hint `or` or `ori` |

Knob changed during P1-07 (or “none”):

Grace-expiry interview id (row J):

Voice ids locked (code → id, or “TBD id”):

Phase 1 exit (yes/no):
