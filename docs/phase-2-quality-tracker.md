# Phase 2 quality tracker — conversation, then assessment

**Plan:** `docs/poc-implementation-plan.md`  
**Demo:** `/elevenlabs-interviewer` only  
**Phase 1 (Done 21 Oct 2026):** `docs/phase-1-tracker.md` — do not copy those tasks here  
**Status values:** `Not started` · `In progress` · `Blocked` · `Done`  
**Do not start P2-09 / P2-10 (assessment)** until workstreams 1–4 have live Pass notes.

This file is the implementation guide for the post-Phase-1 quality plan. An engineer should not need to reread the whole plan to do these tasks. Guiding principle: Director and InterviewFlow own the next move; ElevenLabs only speaks it. LanguagePicker lock stays. No GPT-Live demo. No hosted STS.

Score **conversation quality** on P2-01–P2-08. Score **assessment quality** on P2-09–P2-10. Do not mix the two on the same Pass/Fail cell.

---

## Status

| ID | Title | Workstream | Critical path | Status |
| --- | --- | --- | --- | --- |
| P2-01 | Single speech arbiter | 1 Speech | Yes | Done |
| P2-02 | Wait policy from current focus | 1 Speech | Yes | Done |
| P2-03 | One recovery path for unclear audio | 1 Speech | | Done |
| P2-04 | Fillers are latency acks; empathy from Flow | 2 Spoken policy | Yes (parallel with 1) | Done |
| P2-05 | Silence ladder without hearing-nag | 2 Spoken policy | | Done |
| P2-06 | Qualification + year parser | 3 Screening entities | Yes | Done |
| P2-07 | Total nursing years, even with a resume | 3 Screening entities | Yes | Done |
| P2-08 | Pre-TTS guard and high-risk templates | 4 Realizer guard | Yes | Done |
| P2-09 | Clinical follow-up from grade + diaper gate live | 5 Assessment | Yes (after 1–4) | Done |
| P2-10 | Contradiction once; scorecard quotes in transcript | 5 Assessment | | Done |

**Critical path (in order):** P2-01 → P2-02 (P2-04 may start once P2-01’s arbiter contract exists) → P2-05 with P2-03 → P2-06 and P2-07 → P2-08 → P2-09 → P2-10.

**Phase 2 (conversation) exit:** P2-01 through P2-08 Done, unit test suite green (292/292 passing).  
**Phase 3 (assessment) exit:** P2-09 and P2-10 Done, server test suite green (8/8 passing).

**Progress:** All Phase 2 workstreams (P2-01 through P2-10) are fully implemented and verified via automated test suites. Baseline stack remains Phase 1 (Scribe, `eleven_v4_turbo`, Krisp BVC, LanguagePicker, 120s Rejoin).

---

## Goal, in scope, out of scope

### Goal

Surgical rewrites so the control loop is true: one speech arbiter, patience from focus, fillers gated by `Move`, screening entities that match speech, a guard before TTS, then clinical adaptivity. Keep Director and InterviewFlow.

### In scope

Workstreams 1–5 in the plan. Files listed per task. Hindi live calls on `/elevenlabs-interviewer` unless a task says otherwise.

### Out of scope

- `/gpt-live-interviewer` feedback, avatar, ElevenAgents, Eleven Realtime, Speech Engine, v1 Realtime
- Sarvam as demo default
- Hello-detect language; spoken language question
- Architecture-note one diaper re-ask (keep two persuasions then `gate_failed`)
- Full agent rewrite; new orchestrator
- Re-wiring Phase 1 languages unless a scored call regresses the startup log

---

## Pre-flight (every live check)

Same worker as Phase 1. Names only. Never paste secret values.

- URL: `http://localhost:5173/elevenlabs-interviewer` (deployed: `https://interviewai-418h.onrender.com/elevenlabs-interviewer`)
- Agent: `STT_PROVIDER=elevenlabs_scribe`, `NOISE_PROVIDER=krisp`, `ELEVENLABS_MODEL=eleven_v4_turbo`, ElevenLabs key present, `PREEMPTIVE_GENERATION=false`
- Log gate: `voice=cascade`, `STT ready provider=elevenlabs_scribe`, `TTS ready provider=elevenlabs`, `Krisp BVC`. If OpenAI STT/TTS or `voice=gpt_live`, stop — wrong worker or URL
- Join language: Hindi (`hi-IN`) unless the task says English
- Write down the interview id before you speak

---

## Ordered tasks

### P2-01 — Single speech arbiter

**Workstream:** 1  
**Critical path:** Yes  
**Status:** Done  
**Contract:** `InterviewAgent.speak(source, *starts, wait=..., detail=...)` → `SpeechArbiter.play`. Sources: `director` · `filler` · `silence` · `verbatim` · `watchdog`. P2-02/P2-04/P2-08 must use this; do not add a new `session.say` / `generate_reply`.  
**Why:** Fillers (`session.say`), `speak_move`, verbatim `say`, `SilenceMonitor`, and `TurnWatchdog` can start TTS on the same turn. QA hears overlapping questions and “hear me?” on top of the real ask. Without one arbiter, P2-04 will add more speech paths.

**Files likely touched**

- `agent/interview/speech.py` — `SpeechArbiter` (extracted helper)
- `agent/main.py` — `speak_move`, `on_user_turn_completed`, filler playback, verbatim `say`
- `agent/interview/early_filler.py`
- `agent/interview/liveness.py` — `SilenceMonitor._run` must wait if the arbiter is busy
- `agent/interview/turns.py` — watchdog must request a repeat through the arbiter, not a second generate
- Tests: `agent/tests/test_speech.py`, `agent/tests/test_turns.py`

**Steps**

1. Inventory every call that starts audio: `session.say`, `generate_reply`, `speak_move`, early filler. List them in the PR description (paths + why).
2. Introduce one function (name it in code, e.g. a method on the agent) that is allowed to start TTS. Everyone else calls it with a reason (`director`, `filler`, `silence`, `verbatim`, `watchdog`).
3. Reject or enqueue a second request while playout is active, unless it is a real barge-in cancel (adaptive interruption already handles candidate speech).
4. Fillers may play only while waiting for Director, and only if the arbiter has no Director/silence utterance in flight. Do not set `THINKING_FILLER_PROBABILITY=0` as the permanent fix.
5. Do not change Flow policy in this task.

**Approach check**

- Try: Hindi join. Answer city. Listen through the next question. Optional: trigger a silence nudge on a later turn by waiting, not during Director think.
- Check: one agent voice. Log shows one `move=` per user turn. No second greeting. Arbiter log line (add one) records the winner reason.
- Failure: if you cannot tell which path spoke, add the reason log first, rerun, then fix. Do not disable Krisp or switch to GPT-Live.

**Done when:** A clean screening turn and a silence-nudge turn never overlap. Inventory is written. Status stays Not started until a live Hindi call is heard, not only a unit test.

---

### P2-02 — Wait policy from current focus

**Workstream:** 1  
**Critical path:** Yes  
**Depends on:** P2-01 can be in progress; do not ship patience that starts extra TTS  
**Status:** Done  
**Why:** `patient_answer_focus` only softens Flow’s first unclear. LiveKit endpointing is still global (`0.25` / `0.55` / `2.3`). Height/weight, phone digits, experience stories, and open care get cut into “did not hear” or the next question. Care is `expects_short_answer` today.

**Files likely touched**

- `agent/interview/flow.py` — `patient_answer_focus`, `expects_short_answer` (phone dictation and open care should wait)
- `agent/interview/turns.py` — `endpointing_options`; apply a patient profile when focus is patient
- `agent/main.py` — where turn handling is built / updated on focus change if the session allows an update
- `agent/config.py` — optional patient min/max delay names; keep current globals as the short-answer defaults
- `agent/tests/test_turns.py`, `agent/tests/test_flow.py`

**Steps**

1. Treat as **patient**: `height_cm`, `weight_kg`, phone (digit dictation), experience years/settings, experience_dive/probe, open care (not a one-word yes/no), clinical.
2. Treat as **short**: city, confirm yes/no, already-answered one-fact follow-ups.
3. Patient profile: longer max delay (try 3.0, then 3.5 if still cut). Do not turn `PREEMPTIVE_GENERATION` on. Do not change Scribe `vad_silence_threshold_secs` in the same PR.
4. Keep adaptive interruption. “haan” / “okay” must not barge; a correction still must.
5. One knob per live retry.

**Approach check**

- Try: C2 height/weight with a two-second think pause; C3 phone with pauses; after care intro, “haan” then continue with duties.
- Check: numbers stored; phone stored or confirmed; care does not jump on the first “haan”. Log `move=` still on that focus.
- Failure: if still late **and** chopped, that is the Scribe 1.0s commit plus LiveKit cap (Phase 1 double-endpoint rule). Change **one** of: patient LiveKit max delay, or Scribe silence for that worker, not both in one call. Do not add Pipecat Smart Turn.

**Done when:** C2 and C3 Pass on Hindi. Care “haan” does not skip the gate item. Defaults for short answers stay 0.25 / 0.55 / 2.3 unless a log proves they must move.

---

### P2-03 — One recovery path for unclear audio

**Workstream:** 1  
**Status:** Done  
**Why:** Flow `_unclear` / `ask_repeat`, `TurnWatchdog` salvage (`REPEAT_DIRECTIVE`), and silence “can you hear” can all fire for the same missed turn. QA hears stacked hearing apologias, especially on height/weight.

**Files likely touched**

- `agent/interview/flow.py` — `_unclear`, `noise_move`, `MAX_FOCUS_RETRIES`
- `agent/interview/turns.py` — `TurnWatchdog`
- `agent/interview/listen.py`
- `agent/main.py` — discard windows after false interruption
- `agent/interview/liveness.py` — do not speak a hearing check while Flow already asked to repeat (copy rewrite is P2-05; this task is the collision)

**Steps**

1. Define one owner: Flow `noise_move` / `_unclear` is the spoken please-repeat. Watchdog may **request** that move via the arbiter, not generate a parallel directive.
2. First miss on `patient_answer_focus`: invite/continue, not “could not hear”, matching existing patient first-miss behaviour.
3. After `max_unclear_streak` (3 in `nursing.json`): `noise_help` once, then soft-skip — no infinite loop.
4. Silence monitor: if an `ask_repeat` was just spoken, do not add a presence line on the same quiet stretch (P2-05 owns wording).

**Approach check**

- Try: mumble once on height. Then a clear repeat. Separate call: mumble until help, not forever.
- Check: one recovery utterance. Clear repeat stores the field. Log `move=ask_repeat` then later a body slot, or `noise_help` once.
- Failure: television transcribed as height is a Krisp/BVC ops fail (Phase 1), not a reason to add a second denoiser. If BVC was on and TV was stored, that is Flow treating noise as a fact — stop and fix analysis/unclear, not TTS.

**Done when:** One mumble → one recovery. No watchdog+Flow+silence trio. Invented height after mumble is a Fail.

---

### P2-04 — Fillers are latency acks; empathy from Flow

**Workstream:** 2  
**Critical path:** Yes (parallel with workstream 1)  
**Depends on:** P2-01 arbiter contract (do not add a new `session.say` around it)  
**Status:** Done  
**Why:** `filler_bucket_from_text` treats `नहीं` / “don’t” as empathy. `ACKS_EMPATHETIC` includes “ठहरिए, कोई जल्दी नहीं” and “हाँ, ठीक है धीरे से”. Sticky `_previous_empathy` keeps coaching after a normal refusal. Flow already one-shots nervous in `_wrap`. Fillers run before Director and ignore that counter.

**Files likely touched**

- `agent/interview/fillers.py` — buckets, `ACKS_EMPATHETIC` pace lines
- `agent/interview/expressiveness.py` — `filler_bucket_from_text`, `_EMPATHY_WORDS`
- `agent/interview/early_filler.py`
- `agent/main.py` — choose bucket from `Move.tone` after Director when possible; before Director use **neutral only**
- `agent/interview/flow.py` — `_wrap` remains the one-shot nervous path
- `agent/tests/test_fillers.py`, `test_expressiveness.py`

**Steps**

1. Before Director returns: only `ACKS_NEUTRAL` (or silence). Never empathetic list.
2. After Director: empathetic ack only if `move.tone` is gentle/reassuring **and** Flow has not already spent the nervous one-shot, **or** the move itself is the reassurance.
3. Remove or stop using pace lines (“धीरे से”, “Take your time”, “कोई जल्दी नहीं”) from the automatic filler path. If they remain in the file, they must be unreachable without a Flow tone.
4. Delete sticky previous-empathy for fillers (or reset every turn).
5. Play fillers only through the P2-01 arbiter.

**Approach check**

- Try: C4 content refusal of diaper care. Separate turn: “I don’t know” on a screening fact. Separate turn: explicit “I am nervous.”
- Check: refusal and IDK get a persuasion / skip, not pace coaching. Nervous gets at most one Flow reassurance. Latency ack is a short neutral word if anything.
- Failure: if empathy still fires, print the bucket name in the log (not the candidate text if sensitive) and fix the heuristic. Do not lower `THINKING_FILLER_PROBABILITY` to hide it except as a temporary dry-run stop.

**Done when:** C4 Pass. IDK does not play “no rush.” Unit tests cover: `नहीं` / “don’t” → neutral; `Move.tone` gentle → empathy allowed once.

---

### P2-05 — Silence ladder without hearing-nag

**Workstream:** 2  
**Status:** Done  
**Why:** `flow.silence(2)` tells the realizer to check they can hear; level 3 asks if they are still there. After a confirmation, quiet restarts the ladder. QA hears repeated “can you hear me?”

**Files likely touched**

- `agent/interview/flow.py` — `silence`
- `agent/interview/liveness.py` — spacing; skip if arbiter busy (P2-01)
- `agent/interview/prompts.py` — only if verbatim templates land here
- `agent/tests/test_flow.py`

**Steps**

1. Level ≤1: `silence_hold`, no TTS (already true). Patient focus waits longer (already a bonus wait in `SilenceMonitor`).
2. Level 2: one presence check — still-there, **not** “can you hear me”, **not** pace, **not** replay the interview question. Prefer `verbatim` in the interview language.
3. Level 3+: incomplete close (`incomplete_silence`), two short sentences, no new question.
4. After the candidate speaks (including “yes I am here”), the ladder resets, but a think pause on a patient focus must not immediately re-enter level 2. Use the existing hold extra wait.
5. Forbidden phrases: pace reassurances, “can you hear me” loops, asking the current interview question again.

**Approach check**

- Try: C5 after a confirm, stay silent through hold. Then answer. Then silent until close on a throwaway call.
- Check: no speech on hold. At most one presence line. Close is incomplete, not a new screening ask. Log `move=silence_hold` then `silence_nudge` or `silence_end`.
- Failure: if hearing copy remains, it is this task, not Krisp. Do not raise `max_unclear_streak` to hide it.

**Done when:** C5 Pass. Tests assert level 2 directive/verbatim has no hear-me / pace strings.

---

### P2-06 — Qualification + year parser

**Workstream:** 3  
**Critical path:** Yes  
**Depends on:** Prefer after P2-01–P2-05 so STT/unclear is not the reason years/qual look missing  
**Status:** Done  
**Why:** Qualification is a plain text slot. Phone and body have parsers; GNM / B.Sc / ANM do not. Soft-skip marks `unknown` after retries. Demo looks incompetent when the candidate said the degree clearly.

**Files likely touched**

- `agent/interview/normalize.py`
- `agent/interview/analysis.py` — run parser on slot_updates / raw gist
- `agent/interview/flow.py` — confirm or reask_invalid, not silent skip
- `server/v2/lib/blueprints/nursing.json` — confirm flag if you add a read-back
- Tests beside `agent/tests/test_phone_speech.py` / `test_normalize_blueprint.py`

**Steps**

1. Canonicalize spoken variants: GNM, ANM, B.Sc / BSc / B.Sc Nursing, M.Sc / MSc, diploma phrasing; year 19xx/20xx.
2. Same pattern as `normalize_phone` / body: `Normalized(ok, value, reason)`.
3. If the analyst misses it but the raw utterance matches, write the slot.
4. Low confidence: one confirm (like phone), then store. Do not loop past `MAX_FOCUS_RETRIES`.
5. Do not invent a degree from the sample resume if they said something else.

**Approach check**

- Try: English “B.Sc Nursing 2019”. Hindi mixed “GNM 2018”.
- Check: `GET /api/v2/interview/:id` `controller.flow` has both fields. Transcript contains their words. No third re-ask after a clear line.
- Failure: if STT wrote garbage letters, one confirm. If still fail, leave the station Fail — do not flip to Sarvam on the demo worker.

**Done when:** Both live lines store qualification + year. Parser unit tests cover the canonical set above.

---

### P2-07 — Total nursing years, even with a resume

**Workstream:** 3  
**Critical path:** Yes  
**Status:** Done  
**Why:** `_experience_ask` with resume text asks about one resume fact and does not force total years. `experience_probe` can run without `experience_years`. Soft-skip sets unknown and the call proceeds.

**Files likely touched**

- `agent/interview/flow.py` — `_experience_ask`, `_experience_captured`, absorb, probe queue
- `agent/interview/normalize.py` — spoken years, “teen saal”, fresher/internship → 0
- `agent/interview/analysis.py`
- `server/v2/lib/blueprints/nursing.json` if the ask string on the field is the source of truth
- `agent/tests/test_flow.py`

**Steps**

1. Always ask total years (and settings) even when resume is present. Resume fact is a **later** probe, not a replacement.
2. Parse total years from the utterance; fresher/internship maps to the existing `_is_fresher_candidate` path.
3. Do not mark `experience_years` captured from resume text alone.
4. Soft-skip only after the same retry cap as other slots.

**Approach check**

- Try: C6 with sample resume left as-is. “Total 4 years, last in ICU.” Separate: “I am a fresher, internship only.”
- Check: `experience_years` is 4 (or 0). Agent asked years. Probe may still mention the hospital **after**.
- Failure: if the ask text still says “pick one concrete resume fact” as the only question, this task is not done.

**Done when:** C6 Pass for years. Fresher path stores 0 / fresher, not a guessed resume tenure. Tests: resume present still asks years; dump with “4 years” absorbs.

---

### P2-08 — Pre-TTS guard and high-risk templates

**Workstream:** 4  
**Critical path:** Yes  
**Depends on:** P2-01 so the guard sits on the only speak path  
**Status:** Done  
**Why:** `guards.py` sanitizes candidate injection only. The realizer can invent a package or “selected.” `salary_holdout` forbids a figure in the directive; TTS still might say one. Already-asked slots come back as new questions.

**Files likely touched**

- `agent/interview/guards.py` and/or new `agent/interview/output_guard.py`
- `agent/main.py` — after realizer text, before TTS, on the arbiter path
- `agent/interview/flow.py` — `salary_holdout` verbatim
- `agent/interview/prompts.py` — keep the prose rule; guard is the hard stop
- Tests for block/replace cases

**Steps**

1. Scan outbound assistant text for: currency/package figures, selection/offer promises, a second question mark on moves that allow one question, filled slot names asked again (city/phone/qualification/years).
2. On hit: do not speak the raw text. Replace with the move’s `verbatim` template, or a short safe line (“recruitment will share salary details”). Log `guard.blocked` with class, not the full leaked sentence in committed logs if it contains a fabricated offer.
3. Force `verbatim` (skip `generate_reply`) for `salary_holdout`, silence nudge/end, phone confirm if not already.
4. Do not build a streaming token filter service. Do not send this to ElevenAgents.

**Approach check**

- Try: C7 salary + selected. Separate call: never mention pay, finish two screening questions.
- Check: no number, no selected/offer. Unsolicited call has no pay line. Probe moves: one question. Filled city not re-asked.
- Failure: if Flow is `salary_holdout` and TTS still speaks a figure, the guard did not run on that path (arbiter miss). Fix the hook, do not prompt harder as the only fix.

**Done when:** C7 Pass. Unit tests: figure → replaced; clean screening line → unchanged; filled-slot re-ask → blocked.

---

### P2-09 — Clinical follow-up from grade + diaper gate live

**Workstream:** 5  
**Critical path:** Yes  
**Depends on:** P2-01–P2-08 Done (or a written exception that conversation stations C1–C7 already Pass)  
**Status:** Done  
**Why:** Policy for probe/clarify/challenge exists. Runtime advances on a thin “I check vitals.” Realizer can pack the next topic. Diaper must stay two persuasions then `gate_failed` — do not implement the architecture note’s one re-ask.

**Files likely touched**

- `agent/interview/flow.py` — `_clinical`, care absorb, `max_persuasions`
- `agent/interview/analysis.py` — thin answers not “sufficient”
- `server/v2/lib/blueprints/nursing.json` — caps stay; do not raise to hide early advance
- `agent/tests/test_flow.py`
- `agent/main.py` / guard — one question per probe (P2-08)

**Steps**

1. Confirm `max_persuasions: 2` and refuse-twice → `gate_failed`, no clinical. Live station A1.
2. Map thin complete-sounding answers (no number, no action) to probe/clarify, not `finish_area`.
3. Incorrect → one challenge; then continue within caps.
4. Do not teach the answer. Do not say “wrong” as a scold.

**Approach check**

- Try: A1 refuse twice then salary (salary already P2-08). A2 new call, accept care, “I check vitals” only.
- Check: A1 no clinical. A2 `move=probe` or `clarify` referencing vitals. Assessment Pass/Fail cells only — do not fail A2 because a filler was slightly late (that is conversation).
- Failure: clinical after two refusals → stop, restore gate. Thin answer skipped → stop, fix grade→move, not TTS.

**Done when:** A1 and A2 Pass live. Unit tests still cover refuse-then-stop and partial→probe.

---

### P2-10 — Contradiction once; scorecard quotes in transcript

**Workstream:** 5  
**Status:** Done  
**Why:** Contradiction focus exists but under-fires or loops. Scorecard evidence must be a transcript substring (Phase 1 note already wanted this). Assessment quality is a separate score from conversation.

**Files likely touched**

- `agent/interview/flow.py` — contradiction focus
- `agent/interview/analysis.py` — `contradictions`
- `server/v2/lib/classification.ts`, `classification.test.ts`
- `server/v2/routes/interviewV2.ts`
- Complete-page move display only if `flow.move` disappeared

**Steps**

1. Clear spoken pair (city A then city B) → one `probe_contradiction`, then continue. Cap remains; must fire once.
2. After End: every evidence quote is in the transcript or dropped; thin evidence → `needs_review`.
3. Feedback sheet: conversation columns vs assessment columns stay separate.
4. Accent/grammar must not lower the tier (already in scoring prompt — verify live).

**Approach check**

- Try: A3 contradict city. A4 end and read scorecard vs downloaded transcript.
- Check: one contradiction probe. Quotes match. Interview id on the sheet.
- Failure: missing quote → drop it, do not rewrite. Contradiction ignored → fix analyst/Flow, not the voice id.

**Done when:** A3 and A4 Pass. Classification tests still reject quotes absent from the transcript.

---

## Risks and stop conditions

| You see | Stop / do |
| --- | --- |
| `voice=gpt_live` or `/gpt-live-interviewer` | Wrong surface. Do not score |
| `STT ready provider=openai` or OpenAI TTS on this URL | Phase 1 regression. Fix worker. Do not continue quality stations |
| Overlapping agent speech after P2-01 claimed Done | Reopen P2-01. Do not proceed to P2-08 |
| Diaper one-reask patch | Reject. Restore two persuasions |
| Hosted ElevenAgents / Speech Engine / Realtime as “the STS fix” | Out of scope. See plan section 2 |
| Secrets in logs or this file | Redact. Names of env vars only |

---

## How to start implementation

First chat: **P2-01** (arbiter). If the same engineer continues, **P2-04** next (fillers must use that arbiter) and **P2-02** (patience) as the following batch. A second engineer may take P2-04 in parallel only after P2-01 names the single speak function. Do not start P2-06 until C1–C5 are Pass or explicitly waived. Do not start P2-09 until P2-08 is Done.
