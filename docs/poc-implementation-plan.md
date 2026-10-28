# Voice POC implementation plan

**Date:** 28 October 2026 (quality plan after Phase 1 + QA + STS R&D)  
**Decision source:** `docs/voice-poc-approach.md` (demo route and cascade unchanged)  
**Demo surface:** `/elevenlabs-interviewer` only  
**Trackers:** Phase 1 (Done) `docs/phase-1-tracker.md` · Phase 2 quality `docs/phase-2-quality-tracker.md`  
**This file is the execution plan.** It does not rewrite client requirements or the senior architecture note.

**Guiding principle:** Director and InterviewFlow own the next move. ElevenLabs only speaks it. Language is the join-screen LanguagePicker. No hello-detect. No spoken language question. No avatar this round.

Phase 1 voice, languages, and rejoin is a **completed baseline** (21 October 2026). New work is conversation quality (workstreams 1–4) then assessment quality (workstream 5). Do not re-open languages, Scribe, Krisp, or Rejoin unless a scored call regresses those stations. Teammates shipped brain/flow changes after Phase 1; this plan is the post-Phase-1 quality plan driven by QA and client expectations, not a second language rollout.

---

## POC decisions (do not re-open)

These are locked unless a workstream exit fails for that reason. The senior architecture note is not rewritten; where it disagrees, this box wins for the demo.

| Topic | This POC | Not this round |
| --- | --- | --- |
| Demo URL | `/elevenlabs-interviewer` | `/gpt-live-interviewer`, v1 `/i/:token`, `/avatar-interviewer` |
| Stack | Cascade: Scribe → Director → InterviewFlow → realizer → ElevenLabs TTS | Hosted ElevenAgents / Eleven Realtime / Speech Engine as the demo; fused STS |
| Brain | Keep Director + InterviewFlow. Surgical rewrites of broken outer loops | Full agent rewrite; moving policy into the voice model |
| Language | LanguagePicker locks Scribe hint + ElevenLabs voice before audio | Detect language from hello; spoken language question |
| Diaper gate | Two persuasions, then `gate_failed`, stop before clinical (`nursing.json` `max_persuasions: 2`) | Architecture-note one re-ask |
| Face | Presence orb | Tavus / avatar |
| Sarvam | Fallback comparison only after Scribe then OpenAI STT fail a language | Sarvam as demo default |
| Endpointing defaults | Keep `0.25` / `0.55` / `2.3`, `PREEMPTIVE_GENERATION=false`, `INTERRUPTION_MIN_WORDS=2` | Architecture-note 0.6 / 3.5 / preemptive on / `min_words` 1 as a global swap |
| STS | Deferred. See section 2 | Replacing the cascade because marketing says “speech-to-speech” |

“Refactor to the root” means make the control loop true: **one speech arbiter**, wait policy from current focus, fillers gated by `Move`, pre-TTS guard. It does not mean delete Flow.

Score **conversation quality** (how it talks: turns, fillers, silence, no invented speech) separately from **assessment quality** (what it captured and graded: qualification, years, clinical probes, scorecard evidence). Do not fail a clinical station because a filler sounded wrong, and do not pass a polite call that stored the wrong qualification.

---

## 1. Current goal and non-goals

### Goal

On the same join URL a tester can already use, the call must sound like one interviewer, wait through real answers, capture screening facts that were actually said, and only then be scored as a clinical interviewer.

- Conversation-quality exit (Phase 2, workstreams 1–4): one voice at a time; patient turns on body / phone / experience / open care; latency acks only; silence without hearing-nag; qualification and total years stored or confirmed, not skipped; no spoken salary figure, selection promise, or second question the directive did not ask.
- Assessment-quality exit (Phase 3, workstream 5): after 1–4 stabilize, a thin clinical answer gets one probe, a contradiction gets one probe, and the scorecard quotes exist in the transcript.

### In scope

| Item | Where it lives |
| --- | --- |
| Demo URL | `client/src/App.tsx` → `V2TestPage` with `ttsProvider="elevenlabs"` |
| Transport / ears / mouth | Existing LiveKit v2 worker. `STT_PROVIDER=elevenlabs_scribe`. ElevenLabs `eleven_v4_turbo`. Krisp BVC. LanguagePicker lock |
| Brain | `Director.decide` + `InterviewFlow`. Policy stays here |
| Speech loop | `agent/main.py` (`speak_move`, `on_user_turn_completed`, filler `session.say`), `turns.py`, `listen.py`, `liveness.py` |
| Spoken colour | `fillers.py`, `expressiveness.py`, `early_filler.py`, `flow.silence` / `_wrap` |
| Screening entities | `normalize.py`, `phone_speech.py` (pattern to copy), `analysis.py`, `flow.py` `_experience_ask`, `server/v2/lib/blueprints/nursing.json` |
| Pre-TTS guard | Extend `guards.py` (today injection-only) or a small sibling module; `prompts.py`; `speak_move` |
| Clinical / scorecard | `flow.py` `_clinical`, `analysis.py`, `server/v2/lib/classification.ts`, `server/v2/routes/interviewV2.ts` |
| Rejoin (already shipped) | `client/src/v2/rejoin.ts`, `V2TestPage.tsx`, `useLiveKitInterview.ts`, `ConnectionGuard` |

### Non-goals

- `/gpt-live-interviewer` as the place language, policy, or clinical feedback is collected
- ElevenLabs Agents, Eleven Realtime, Speech Engine, Sarvam hosted agents, Pipecat Flows, v1 browser Realtime
- Avatar / Tavus on this route
- Hello-detect language; a spoken language question
- Voice cloning; Sarvam as the default ear or mouth
- Deleting InterviewFlow or replacing it with a hosted workflow graph
- Architecture-note one-diaper-reask
- Live backchannels (“mm-hmm” while the candidate is still talking)
- Re-doing Phase 1 language wiring, Odia `or`, or Rejoin unless a regression is logged

---

## 2. STS verdict (researched 28 October 2026)

**Keep the LiveKit cascade. Do not demo hosted STS. Do not demo GPT-Live.**

### What exists

ElevenLabs ships three “voice agent” products, and marketing uses “Speech to Speech” for some of them. The inspectable architecture is still cascaded.

1. **ElevenAgents** (Conversational AI). Hosted omnichannel agents: ASR + chosen LLM + TTS + proprietary turn-taking, plus visual Workflows, tools, and evals. ElevenLabs’ own architecture note (updated 5 Oct 2026) calls this an **advanced cascaded** stack, not a fused audio-in/audio-out model. Custom LLM is supported only as an OpenAI-compatible HTTP endpoint, and **a custom LLM cannot be used with Realtime models**. Workflows would replace `flow.py`.
2. **Eleven Realtime** (`eleven_realtime_v1_mini` / `_max`, launched 20 Oct 2026). Sold as Speech-to-Speech models, also via an OpenAI-Realtime-compatible WebSocket. ElevenLabs’ FAQ is explicit: **Realtime models are not fused**; they are a co-optimized cascade. Realtime mode manages LLM, TTS, and ASR for you. That is the same policy-leak shape as GPT-Live: the mouth can talk while our Director is still deciding.
3. **Speech Engine.** Closest to “our brain, their mouth.” ElevenLabs runs STT, VAD, turn-taking, and TTS; your server receives transcripts and `sendResponse()`s text. A LiveKit bridge exists (worker pipes room PCM to Speech Engine). This is still STT → text brain → TTS. Turn-taking moves to ElevenLabs. LanguagePicker, Krisp, LiveKit adaptive interruption, ConnectionGuard, and the speech arbiter would all be re-platformed. It is a transport rewrite, not a drop-in STS mouth on `/elevenlabs-interviewer`.

**Scribe + `eleven_v4_turbo` on LiveKit** is the cascade we already run. That is the same family of architecture ElevenLabs recommends for enterprise/healthcare when you need text-layer guardrails.

**OpenAI** ([Voice agents](https://developers.openai.com/api/docs/guides/voice-agents)): use a **chained** pipeline when you must inspect text and “generate speech only after the workflow reaches an approved answer.” GPT-Live / Realtime S2S is for full duplex while a backend works — the live model still decides when to speak. That is why GPT-Live is not the demo.

**LiveKit + ElevenLabs STS:** there is no fused STS plugin. LiveKit’s ElevenLabs plugins are STT and TTS. The Speech Engine LiveKit guide is a bridge to ElevenLabs’ hosted conversation socket, not “Flow in the middle of audio.”

### Why cascade stays for this product

Director must see a transcript, InterviewFlow must emit one `Move`, and ElevenLabs must speak that move — including two diaper persuasions then `gate_failed`, no salary figure, no second question. Hosted Agents / Realtime cannot take a deterministic controller **before** speech without either (a) becoming a custom-LLM cascade we already have, or (b) letting the voice model talk first. Speech Engine could keep Flow as the text brain, but it does not give a fused mouth, it steals turn-taking, and it would reopen Phase 1. Latency of cascade is the price of policy-before-speech. Fillers (workstream 2) cover that wait; they must not become policy.

### When to revisit (future-scope only)

Revisit only if all of these are true: workstreams 1–4 are Done; a measured latency problem remains after fillers + arbiter; Speech Engine (or equivalent) can play **only** text that Flow already approved; LanguagePicker still locks language; their turn-taker cannot speak a question Flow did not emit. True fused STS is out while policy must inspect text. Pointer: `docs/future-scope.md`.

Sources: [Cascaded vs fused](https://elevenlabs.io/blog/cascaded-vs-fused-models), [ElevenAgents overview](https://elevenlabs.io/docs/eleven-agents/overview), [Realtime models](https://elevenlabs.io/docs/eleven-agents/customization/realtime-models), [Realtime FAQ (not fused)](https://elevenlabs.io/docs/eleven-agents/guides/openai-realtime-compatibility), [Eleven Realtime launch](https://elevenlabs.io/blog/realtime), [Speech Engine × LiveKit](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-engine/livekit-integration), [OpenAI voice agents](https://developers.openai.com/api/docs/guides/voice-agents).

---

## 3. Phases (quality workstreams)

Phase 1 is Done. Do not start workstream 5 until 1–4 have live Pass notes. Workstream 2 may run **in parallel with** workstream 1 once the arbiter contract in P2-01 is written (fillers must not grow new `session.say` paths around the arbiter). Workstreams 3 and 4 wait until overlapping speech and hearing-nag are no longer flooding the transcript. Workstream 5 waits until screening facts are true.

| Phase | Name | Workstreams | Starts when |
| --- | --- | --- | --- |
| 1 | Cascade baseline | Languages, Scribe, TTS, Krisp, turns, Rejoin | Done 21 Oct 2026 |
| 2 | Conversation quality | 1 speech arbiter + patience · 2 fillers/empathy/silence · 3 screening entities · 4 pre-TTS guard | Now |
| 3 | Assessment quality | 5 clinical adaptivity + scorecard evidence | After Phase 2 exits |

Critical path: **P2-01 + P2-02**, then **P2-04 + P2-05**, then **P2-06 + P2-07**, then **P2-08**, then **P2-09 + P2-10**.

---

### Workstream 1 — Speech arbitration and turn patience

**Goal.** One path starts TTS per turn. Wait policy comes from current focus. Unclear, silence, and false barge-in stay different. Care / body / phone / experience are not cut off into “did not hear.”

**In scope.** A single speech arbiter wrapping `speak_move`, filler playback, verbatim `session.say`, and SilenceMonitor. Per-focus endpointing (patient vs short). Collapse duplicate please-repeat (Flow `_unclear` vs `TurnWatchdog` vs silence “can you hear”). Keep LiveKit adaptive interruption and `PREEMPTIVE_GENERATION=false`.

**Out of scope.** New turn-detector product, Pipecat Smart Turn, indic-smart-turn, enabling preemptive generation, changing Scribe `vad_silence_threshold_secs` globally without a measured station, GPT-Live, Speech Engine.

**Files likely touched**

- `agent/main.py` — `speak_move`, `on_user_turn_completed`, filler `session.say` (~1472), verbatim `say` (~1506), watchdog attach
- `agent/interview/turns.py` — `endpointing_options`, `TurnWatchdog`, `REPEAT_DIRECTIVE`
- `agent/interview/listen.py` — `is_candidate_speech`
- `agent/interview/liveness.py` — `SilenceMonitor` (must not overlap an in-flight Director reply)
- `agent/interview/flow.py` — `patient_answer_focus`, `expects_short_answer`, `_unclear` / `noise_move`
- `agent/interview/early_filler.py` — another `session.say`
- `agent/config.py` — endpointing settings; optional per-focus overrides
- Tests: `agent/tests/test_turns.py`, `agent/tests/test_listen.py`

**Try / how to check / failure handling**

| Station | Try | Pass | On fail |
| --- | --- | --- | --- |
| One speaker | Hindi call. Answer city. During Director wait, do not barge. Listen for overlapping greeting + ack + question | One audio stream. One `move=` per user turn in the log. No second interviewer voice | Stop. Find the second `session.say` / `generate_reply` / `speak_move`. Do not mute fillers by setting probability to 0 as the “fix” except as a temporary dry-run stop |
| Body patience | Height then weight, spoken slowly with a two-second think pause | Agent waits. No `ask_repeat` / “could not hear” on the pause. Both numbers stored after a clear finish | One change: raise delay only for `patient_answer_focus` (include `height_cm` / `weight_kg`). Do not raise global `ENDPOINTING_MAX_DELAY` past 3.5 unless this station still fails |
| Phone patience | Dictate a 10-digit mobile with pauses | Digits captured or one confirm. Not `ask_repeat` mid-number | Treat phone as patient dictation even if `expects_short_answer` is true today |
| Care wait | After diaper/care intro, give a short “haan” then continue with duties | Does not jump to the next care item or screening slot on the first “haan”. Log `move=` is still care, not `_screening_next` | Fix absorb / endpointing for open care. Do not retune TTS |
| Duplicate hear-me | Mumble once, then sit quiet | One please-repeat **or** one silence nudge, not both stacked. Watchdog salvage does not add a third | Collapse watchdog into Flow `noise_move` / `_unclear`. Silence must not say “can you hear” (that copy is workstream 2) |

**Exit.** On `/elevenlabs-interviewer` Hindi: no overlapping agent speech on a clean screening turn; height/weight and phone survive a mid-answer pause; one mumble produces one recovery line. Conversation-quality sheet rows for arbiter and patience are Pass.

---

### Workstream 2 — Filler, empathy, and silence spoken policy

**Goal.** Acks cover Director latency only. Emotion only when Flow says so. Silence holds, then one presence check, then incomplete — never a “dheere se” / “can you hear me?” loop.

**In scope.** Rewrite filler bucket selection. Empathetic acks fire only from `Move.tone` / nervous wrap (Flow already one-shots nervous). Neutral latency acks otherwise. Silence ladder copy and spacing. Gate fillers through the workstream-1 arbiter.

**Out of scope.** Live backchannels while the candidate talks. Expressiveness engine off unless tags are spoken aloud (then turn engine off for the demo rather than free-form tags). Changing Director models.

**Files likely touched**

- `agent/interview/fillers.py` — `ACKS_EMPATHETIC` pace lines, `filler_bucket_from_text` (also in `expressiveness.py`)
- `agent/interview/expressiveness.py` — `_EMPATHY_WORDS`, sticky `_previous_empathy`
- `agent/interview/early_filler.py`
- `agent/interview/flow.py` — `silence`, `_wrap` nervous
- `agent/main.py` — filler-before-Director ordering; pass Move into filler choice
- `agent/interview/liveness.py` — spacing after hold
- Tests: `agent/tests/test_fillers.py`, `test_expressiveness.py`, `test_flow.py` (silence kinds)

**Try / how to check / failure handling**

| Station | Try | Pass | On fail |
| --- | --- | --- | --- |
| No pace coaching | Hindi. Say “main diaper care nahi kar sakti” (content refusal, not nervous) | No “धीरे से” / “कोई जल्दी नहीं” / “Take your time” before the persuasion. Empathy only if `move.tone` is gentle/reassuring | Stop shipping STT-heuristic empathy. Neutral ack or silence until Flow returns |
| Latency ack | Pause after a clear city answer until the next question | At most one short neutral ack (“ठीक है.” / “Okay.”), then the next question. Same voice | If double speech, that is workstream 1. If the ack is an empathy line, fix the bucket |
| Silence | After a confirmation, stay quiet | Level 1: no speech. Then one “still there?” equivalent, not “can you hear me?” twice. Then incomplete close. No pace reassurance | Rewrite `flow.silence` level 2–3 copy. Reset must not re-nag after a “yes I am here” then a think pause |
| Nervous one-shot | Explicit “I am nervous / I am scared” once | One reassurance from Flow `_wrap`. Second nervous turn does not replay it | Fillers must not have a separate nervous counter |

**Exit.** A refusal and an “I don’t know” never trigger pace-coaching fillers. Silence after confirm does not loop hearing checks. Conversation-quality rows for fillers and silence are Pass.

---

### Workstream 3 — Screening entity truth (qualification + total years)

**Goal.** Qualification (+ year) and **total** nursing years are captured or confirmed the way phone already is. Resume-tied probes deepen a story; they do not replace tenure.

**In scope.** Deterministic parsers/dictionaries for GNM / ANM / B.Sc / BSc Nursing / M.Sc and passing year. Total-years parser (spoken numbers, “teen saal”, fresher/internship). `_experience_ask` always asks total years even when resume text exists. Soft-skip to `unknown` only after the same retry cap as other slots, not because the resume question skipped years. Optional confirm when the parser is low-confidence.

**Out of scope.** New clinical rubric. Changing diaper `max_persuasions`. Building a general NER service. Hello-detect.

**Files likely touched**

- `agent/interview/normalize.py` — extend the phone/body pattern
- `agent/interview/phone_speech.py` — pattern only; do not weaken phone
- `agent/interview/analysis.py` — slot_updates still run; parsers post-check
- `agent/interview/flow.py` — `_experience_ask`, absorb / `_experience_captured`, soft-skip
- `server/v2/lib/blueprints/nursing.json` — field asks / confirm flags if needed
- Tests: `agent/tests/test_flow.py`, `test_normalize_blueprint.py`; add focused parser tests beside `test_phone_speech.py`

**Try / how to check / failure handling**

| Station | Try | Pass | On fail |
| --- | --- | --- | --- |
| Qualification | Clear “B.Sc Nursing 2019” (and one Hindi mixed line, e.g. “GNM 2018”) | `controller.flow` has qualification + year. Not a re-ask loop. Not `unknown` after one clear answer | Add canonicalizer. If STT mangled the letters, one confirm, then store. Do not soft-skip |
| Total years with resume | Sample resume left as-is. Answer “total 4 years, last in ICU” | Slot `experience_years` is 4 (or confirmed). Agent asked years, not only “tell me about the hospital on your resume” | Rewrite `_experience_ask` so resume is a probe **after** years, or the same turn still extracts years |
| Fresher | “I am a fresher, internship only” | Years 0 / fresher path. Not skipped, not invented as 3 years from resume | Parser + Flow fresher helper already exists — wire it to the spoken line |
| Soft-skip | Refuse to give years twice, then a third miss | `unknown` only after `MAX_FOCUS_RETRIES`. Clinical must not start on a guessed tenure | Do not raise the retry cap to hide the miss |

**Exit.** Two live Hindi (or English) screening passes store qualification+year and total years from speech. Resume probes may still run. Conversation-quality sheet: entities Pass. This is still conversation/screening truth, not clinical scoring.

---

### Workstream 4 — Realizer guard before TTS

**Goal.** The dialogue model words the directive. It cannot invent a salary, an offer, a second question, or a slot already captured. High-risk moves use verbatim / templates.

**In scope.** A pre-TTS scan on the text about to be spoken (cascade only). Block or replace: rupee/lakh/package figures, “you are selected”, a second interrogative when the move is not ask/probe, re-asking a filled slot. Prefer `verbatim` for `salary_holdout`, silence, phone confirm (already partly done). `guards.py` today only sanitizes **candidate** injection — extend it or add a sibling; do not reuse injection patterns as the salary list.

**Out of scope.** Architecture-note full streaming token guard as a new service. Hosted agent guardrails. GPT-Live output filter as a substitute (GPT-Live is not the demo).

**Files likely touched**

- `agent/interview/guards.py` or new `agent/interview/output_guard.py`
- `agent/main.py` — `speak_move` / generate_reply path, after realizer text, before TTS
- `agent/interview/prompts.py` — keep “never invent”; guard is the hard stop
- `agent/interview/flow.py` — `salary_holdout` verbatim variants
- Tests next to existing guard/flow tests

**Try / how to check / failure handling**

| Station | Try | Pass | On fail |
| --- | --- | --- | --- |
| Salary ask | After screening, ask “what salary will I get, am I selected?” | Holdout: recruitment shares salary; no number; no yes/selected. `move=salary_holdout` or `answer_question` without a figure | If Flow is correct and TTS still speaks a figure, the guard must replace with the template. Do not move the brain to ElevenAgents |
| Unsolicited pay | Normal screening, never mention pay | No package/offer line | Same guard. Log a `guard.blocked` event (no secret content) |
| No double question | Any probe move | Spoken text is one question. Captured city/phone/qualification do not reappear as asks | Facts line is not enough — scan against filled slots |
| Verbatim silence / salary | Trigger those moves | Spoken text matches template in that language | If the LLM paraphrases, force `verbatim` and skip generate_reply |

**Exit.** Refusal station plus an unsolicited-pay call: no figure, no selection. One probe is one question. Conversation quality can be scored without a leaked promise.

---

### Workstream 5 — Clinical adaptivity and scorecard evidence

**Goal.** After the call is conversationally trustworthy, a partial or wrong clinical answer gets one targeted follow-up. A contradiction is probed once. Tier evidence quotes appear in the transcript. Conversation scores and assessment scores are recorded on separate rows.

**In scope.** `flow._clinical` honouring grade (clarify / probe / challenge / deepen). Analyst `ClinicalGrade` tightness enough that “I check vitals” does not finish the area. Contradiction focus once then continue. Scorecard quote verification already exists — keep quotes that match the transcript; do not invent. Reviewer can see `move=` beside the candidate line (Phase 1 progress already pointed at the complete page).

**Out of scope.** Replacing the blueprint with a free-form clinical LLM. Raising area caps as a way to hide early advance. Avatar. GPT-Live clinical A/B as the scored demo.

**Files likely touched**

- `agent/interview/flow.py` — `_clinical`, contradiction
- `agent/interview/analysis.py` — clinical schema / thin-answer grades
- `server/v2/lib/classification.ts`, `server/v2/lib/classification.test.ts`
- `server/v2/routes/interviewV2.ts` — scorecard payload
- `agent/tests/test_flow.py`
- Complete-page move display only if a regression hid `flow.move`

**Try / how to check / failure handling**

| Station | Try | Pass | On fail |
| --- | --- | --- | --- |
| Diaper refuse-twice | Refuse, hear explanation, refuse again | Two persuasions, `gate_failed`, no clinical question. Then salary ask is workstream 4 | Restore `max_persuasions: 2`. Do not adopt one re-ask |
| Thin clinical | Second call, accept care. “I check vitals” with no number and no action | `move=probe` or `clarify`, references what they said. Does not finish the area | Fix grade → move. Do not retune TTS |
| Contradiction | Give city A, later city B | One `probe_contradiction`, then continue. No loop | Cap already 2 — must fire once on a clear pair |
| Evidence | End a complete call | Scorecard quotes are substrings of the transcript. Accent/grammar not the tier reason | Drop the quote; `needs_review` if evidence is thin. Do not generate a nicer quote |

**Exit.** Assessment-quality sheet has Pass for refuse-twice, thin probe, contradiction, and quote-in-transcript. Conversation-quality scores from Phase 2 are not reused as the clinical grade.

---

## 4. Demo script (quality)

Local: `http://localhost:5173/elevenlabs-interviewer`. Deployed: `https://interviewai-418h.onrender.com/elevenlabs-interviewer`. Do not open `/gpt-live-interviewer` for these scores.

Use Hindi (`hi-IN`) unless a station names another language. Record interview id, `move=`, transcript line, conversation Pass/Fail, assessment Pass/Fail (N/A on Phase 2 stations). Accent and grammar are never the reason for a lower tier.

**Phase 2 conversation (workstreams 1–4)**

| # | Do this | Pass | Fail |
| --- | --- | --- | --- |
| C1 | Join. Hear one greeting. Answer city | One voice. No overlapping ack+question | Two voices or two questions. Workstream 1 |
| C2 | Height and weight slowly, pause mid-number | Both stored. No “did not hear” on the pause | Cut-off / ask_repeat. Workstream 1 |
| C3 | Phone digits with pauses | Stored or one confirm | Mid-number repeat loop. Workstream 1 |
| C4 | “I don’t do diaper care” (content, not tears) | Persuasion, not “धीरे से” | Pace filler. Workstream 2 |
| C5 | After a confirm, stay silent | Hold, one presence check, or continue — no hear-me loop | Workstream 2 |
| C6 | “B.Sc Nursing 2019” and “total 4 years ICU” (resume left as-is) | Both slots in `controller.flow` | Missing years or qual. Workstream 3 |
| C7 | “What salary will I get, am I selected?” | No figure, no selected | Workstream 4 |

**Phase 3 assessment (workstream 5)** — only after C1–C7 Pass on a prior call, or the same call if 1–4 already shipped.

| # | Do this | Pass | Fail |
| --- | --- | --- | --- |
| A1 | Refuse diaper twice | `gate_failed`, no clinical | Clinical starts |
| A2 | New call, accept care, “I check vitals” only | One probe | Next blueprint question |
| A3 | Contradict city | One contradiction probe | Ignore or loop |
| A4 | End. Read scorecard | Quotes in transcript | Hallucinated evidence |

**Sheet columns:** station, conversation pass/fail, assessment pass/fail, heard, transcript line, move or event, next action from this plan (not “investigate”).

---

## 5. Where the docs and the code disagree

The plan follows `docs/voice-poc-approach.md` (demo route) and this quality update. Mismatches a reader will hit:

| Topic | Other doc | Code / this plan |
| --- | --- | --- |
| Face on the demo | `docs/client-requirements.md` §8 wants a face | Presence orb. Avatar stays out. Pointer in `docs/future-scope.md` |
| Diaper re-ask | Architecture note: at most one re-ask | Two persuasions then `gate_failed`. Keep two |
| Endpointing numbers | Architecture note: min 0.6, max 3.5, preemptive on, `min_words` 1 | Keep example defaults. Per-focus patience is P2-02, not a global swap to the note |
| Output guard | Architecture note: streaming guard as control design. Approach note deferred it | Now in scope as workstream 4: small pre-TTS scan + templates. Not a new brain |
| Speech arbiter | Approach note deferred a full arbiter rewrite unless double replies | Now in scope as workstream 1. Keep Flow |
| Sarvam as voice A/B | Architecture note: A/B Bulbul for Hindi/Marathi up front | Fallback only after Scribe then OpenAI STT fail |
| STS / hosted agents | Approach note already deferred ElevenAgents | Confirmed 28 Oct 2026: still deferred. See section 2 |
| STT default | `agent/.env.example` is `openai` | Demo worker stays `elevenlabs_scribe` |
| TTS default | `agent/.env.example` is `google` | This URL overrides to ElevenLabs |
| Language picker | Client list vs `SUPPORTED_LANGUAGES` | Phase 1 wired eleven codes. Picker fallback still omits some until `GET /api/v2/interview/languages` succeeds |
| Rejoin | Older client-requirements gap said test pages do not rejoin | Phase 1 P1-09 Done. `client/src/v2/rejoin.ts` within 120s |
| Both public URLs | Requirements present GPT-Live and ElevenLabs as two live surfaces | Feedback for this POC is `/elevenlabs-interviewer` only |
| Old Phase 2/3 in the 19 Oct plan | Brain-loop visibility and drop-past-120s hardening | 21 Oct tracker: move display and quote-in-transcript / incomplete-after-grace were called out as done. **This document’s Phase 2/3 are the quality workstreams**, not those old names |

---

## 6. Working trackers

- Phase 1 (historical, all rows Done): `docs/phase-1-tracker.md`
- Phase 2 conversation quality + Phase 3 assessment quality: `docs/phase-2-quality-tracker.md`
- Gaps analysis (why): `docs/elevenlabs-interviewer-gaps.md`
- Deferred STS / GPT-Live-as-demo / avatar / one-diaper-reask / Sarvam-default: `docs/future-scope.md`

Do not add Phase 2 tasks into the Phase 1 file.

---

## Appendix A — Completed Phase 1 baseline (21 October 2026)

Do not re-execute these as a project. Use them as the stack gate if a quality call logs the wrong provider. Full try/check tables: `docs/phase-1-tracker.md`.

### What Phase 1 proved

`/elevenlabs-interviewer` starts in every claimed language, Scribe takes the join hint, ElevenLabs `eleven_v4_turbo` speaks, Krisp BVC is on, please-repeat does not invent a fact, and Rejoin within 120 seconds repeats the last question on the same interview id. Brain-quality scoring was not a Phase 1 exit. Confirmed 21 Oct 2026. Persona on those calls: voice id `4mCfn38CsM9hGLvDrPxv`. Odia TTS and Scribe stay `or`. Endpointing stayed `0.25` / `0.55` / `2.3`.

### Stack that must still log on every scored call

| Layer | POC choice |
| --- | --- |
| Route | `/elevenlabs-interviewer` (`ttsProvider: "elevenlabs"`) |
| Transport | LiveKit room, worker `V2_AGENT_NAME` (default `interview-v2`) |
| Ears | `STT_PROVIDER=elevenlabs_scribe`, model `scribe_v2_realtime`, join language as hint, not auto-detect |
| Mouth | `eleven_v4_turbo`, `ELEVENLABS_VOICE_BY_LANG` / fallback id above |
| Noise | Krisp BVC on the agent. Published mic `noiseSuppression: false` |
| Turns | LiveKit VAD + turn detector + adaptive interruption. Preemptive generation off |
| Brain | `Director.decide` + `InterviewFlow`. Dialogue model only realises the directive |
| Language | `LanguagePicker` → `SUPPORTED_LANGUAGES` in `server/v2/lib/types.ts` and `PROFILES` in `agent/interview/language.py` |
| State | Persisted `FlowState`. Rejoin same id inside 120 seconds (`client/src/v2/rejoin.ts`) |
| Diaper | `max_persuasions: 2` then `gate_failed` |

Languages: `en-IN` (Indian accent), `hi-IN`, `te-IN`, `ta-IN`, `kn-IN`, `ml-IN`, `bn-IN`, `mr-IN`, `gu-IN`, `pa-IN`, `od-IN`. Scribe primary is the first subtag (`en`, `hi`, …). Odia maps to `or` (try `ori` only if Scribe rejects `or`). English secondary list is empty; other Indic add `en`, and non-Hindi Indic add `hi`.

Worker names (values, not secrets): `STT_PROVIDER=elevenlabs_scribe`, `NOISE_PROVIDER=krisp`, `ELEVENLABS_MODEL=eleven_v4_turbo`, `ELEVENLABS_API_KEY` or `ELEVEN_API_KEY` present, `VOICE_EXPRESSIVENESS=engine`, `TURN_DETECTOR_ENABLED=true`, `ENDPOINTING_MODE=dynamic`, `INTERRUPTION_MODE=adaptive`, `PREEMPTIVE_GENERATION=false`, `RECONNECT_GRACE_SECONDS=120`. A Scribe or TTS silent fallback to OpenAI is a **stop**, not a scored call. `agent/.env.example` still defaults STT `openai` and TTS `google` — the **running** worker must match the table.

### Phase 1 regression script (only if logs look wrong)

English, Hindi, Telugu live; other languages wired. Hindi also: noise (TV) → `ask_repeat`; barge-in correction vs “haan”; refresh → Rejoin within 120s, same id, one agent. Do not score diaper or clinical on a regression pass.

### Old 19 Oct Phase 2 / Phase 3 names

The 19 Oct plan’s “Phase 2 brain loop” (surface `move=` / refuse-twice / thin probe / contradiction) and “Phase 3 hardening” (drop past 120s incomplete, quote-in-transcript) are **not** the current phase names. The 21 Oct tracker note already treated move display and quote/incomplete-drop as done. Remaining brain pain is the workstreams above. GPT-Live, avatar, hosted agents, Sarvam-as-default, and a full streaming-guard service stay out.
