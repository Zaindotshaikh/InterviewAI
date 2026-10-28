# `/elevenlabs-interviewer` — client expectations, QA gaps, and voice-agent checklist

**Scope:** Cascade demo only — `client/src/App.tsx` → `V2TestPage` with `ttsProvider="elevenlabs"`. Brain = Director analyzes, InterviewFlow owns the next move, ElevenLabs speaks. Language = join-screen `LanguagePicker` (no spoken language question).  
**Out of scope:** `/gpt-live-interviewer`, v1 `/i/:token`, avatar route, unrelated server v2 paths except plan/start that feed this route.  
**Method:** Code inventory of the EL path + client join/rejoin + nursing blueprint; skim of client/POC docs for expected behavior; primary-source web research (2024–2026) for Part C.  
**Date:** 28 Oct 2026. No secrets. Analysis only — no product code changes in this note.

## Plan adopted

Quality work after this analysis is in `docs/poc-implementation-plan.md` (STS verdict + five workstreams) and `docs/phase-2-quality-tracker.md` (P2-01–P2-10, Not started). Phase 1 cascade/language/rejoin stays Done in `docs/phase-1-tracker.md`. Demo remains `/elevenlabs-interviewer`. Keep Director + InterviewFlow; do not move the demo to ElevenAgents, Eleven Realtime, Speech Engine, or GPT-Live. Do not duplicate this gaps file into those trackers — implement from the tracker ids.

---

## Architecture snapshot (this route)

| Layer | Role | Primary files |
| --- | --- | --- |
| Join / rejoin | Language pick, start, Krisp-friendly mic, 120s rejoin | `client/src/v2/V2TestPage.tsx`, `LanguagePicker.tsx`, `rejoin.ts`, `useLiveKitInterview.ts`, `LiveInterview.tsx`, `PreflightCheck.tsx` |
| Transport / ears / mouth | LiveKit room; Scribe STT; EL TTS; Krisp BVC | `agent/main.py`, `agent/providers/factory.py`, `elevenlabs_voices.py` |
| Turn / listen | Adaptive interruption, endpointing, noise floor, silence/drop | `turns.py`, `listen.py`, `liveness.py` |
| Brain | Analyze utterance → typed `Move` | `director.py`, `analysis.py`, `flow.py`, `flow_state.py`, `blueprint.py` + `server/v2/lib/blueprints/nursing.json` |
| Realizer / voice color | Directive → speech; acks / expressiveness | `prompts.py`, `fillers.py`, `expressiveness.py`, `main.py` `speak_move` / `on_user_turn_completed` |
| Parsers | Phone / height-weight (not qualification) | `phone_speech.py`, `normalize.py` |
| Scorecard | Post-call tier + evidence | `server/v2/routes/interviewV2.ts`, `classification.js` |

Design intent (POC + architecture note): **Flow decides; voice model only words the directive.** Failures on this demo are usually leaks (realizer invents content, fillers/silence race Flow, STT/endpointing falsifies the turn), not “wrong LLM brand.”

---

## PART A — Client expectations vs implementation

Sources for expectations: `docs/client-requirements.md` §4; Phase 1 language/rejoin goals in `docs/phase-1-tracker.md` / `docs/poc-implementation-plan.md`.

| # | Expectation | Status | Evidence | Gap | Good-demo bar |
| --- | --- | --- | --- | --- | --- |
| 1 | Multiple Indian languages (en, hi, te, ta, kn, ml, bn, mr + relevant) | **Present** | `LanguagePicker` loads `/api/v2/interview/languages` (fallback omits bn/mr/gu/pa/od until API returns). `agent/interview/language.py` `PROFILES` covers en/hi/ta/te/kn/ml/mr/bn/gu/pa/od. Phase 1 matrix marked Done; EL voice map + Scribe hints in `elevenlabs_voices.py`. | Client FALLBACK list is incomplete if languages API fails. Voice quality / Scribe accuracy still uneven by language (product risk, not wiring). | Join → pick any claimed language → hear matching persona → Scribe accepts a short answer without silent OpenAI fallback. |
| 2 | Multi-language conversations (Hinglish, Tanglish mid-call) | **Partial** | Join language is authoritative (POC rule). Scribe gets primary + `en` (+ `hi` for non-hi) via `scribe_language_hints`. OpenAI STT path (fallback) prompts for code-mix. `detect_script_language` + `switch_language` tool exist. Prompts allow register mix. | No durable mid-call *policy* language switch driven by STT alone; Flow/state stay on join language. Code-switch ASR quality is STT-dependent; Indic scripts can garble English nursing terms. | Candidate can answer in Hinglish/Tanglish without the agent “correcting” to pure Hindi/Tamil or inventing a language question. |
| 3 | Regional accents, slang, colloquial, imperfect pronunciation without harming knowledge assessment | **Partial** | Analyst instructions (`analysis.py`) tell the model not to penalize recoverable mispronunciation; clinical `quality` separate from intelligibility. Native-script reminders in prompts. | No accent-robust ASR tuning beyond Scribe hints/keyterms. Bad STT → wrong slots → soft-skip or “unclear” that *does* harm screening facts. Clinical grade still LLM-on-transcript. | Clear clinical content in accented/colloquial speech is graded on content; screening facts recovered or confirmed, not silently dropped. |
| 4 | High background noise + recognize unclear audio and ask to repeat | **Partial** | Agent Krisp (`NOISE_PROVIDER=krisp`); client `noiseSuppression: false` (`useLiveKitInterview.ts`). `listen.is_candidate_speech`, noise discard in `main.py`, `flow._unclear` / patient first miss, `TurnWatchdog` missing-transcript recovery, preflight noise warn. | Premature “did not hear” still QA-hot (Part B §4). Ward noise can false-interrupt or empty-transcript → ask_repeat. Double ladder: Flow unclear + silence nudge + watchdog. | Agent stays silent on hum/TV; asks to repeat only when speech was intended but unusable; recovers without advancing. |
| 5 | Dynamic clinical assessment (incomplete/incorrect/partial → follow-ups) | **Present** (policy) / **Broken-risk** (runtime) | `flow._clinical`: clarify / probe / challenge / deepen / finish by grade. Blueprint limits (`max_probes_per_area`, etc.). | Wrong/missing `ClinicalGrade` from analyst → advances early (QA §7 family). Realizer may ignore “ONE follow-up” and soft-advance topic. | Partial answer gets one targeted probe referencing what they said; incorrect gets one challenge; not a scripted list walk. |
| 6 | Conversation context (contradictions → probe) | **Partial** | Analyst emits `contradictions`; Flow has `contradiction` focus + `max_contradiction_probes`. Claims absorbed into state. | Under-firing (strict “both sides spoken”) or over-firing on rephrase. Soft-skip after retries abandons probe. Resume mismatches are separate (`resume_mismatch`). | Clear self-contradiction gets one natural probe, then continues without looping. |
| 7 | Candidate behaviour (nervous, long pauses, IDK, interruptions, repeat/rephrase) | **Partial** | Nervous: Flow one-shot reassurance + tone. Silence: `SilenceMonitor` + `flow.silence` hold→nudge→check→end. IDK / refusal / repeat / rephrase intents in `apply`. Interruptions: `turns.build_turn_handling` adaptive mode. | Empathetic **fillers** fire from crude text heuristics (Part B §3). Silence “can you hear me?” repeats (Part B §8). Endpointing still cuts slow Indic answers. | Human-like: wait through thinking pauses; one calm reassurance max; IDK moves on; barge-in only on real speech. |
| 8 | Clinical interviewer capability (knowledge, not screening-only) | **Partial** | Stages `screening → clinical → closing`; area rubrics in `nursing.json`; probes deepen level. Scorecard uses clinical evidence. | POC Phase 1 explicitly deferred brain tuning. Demo often dies in screening/audio issues before clinical depth shows. Realizer must not teach answers (prompted). | At least 1–2 clinical areas with adaptive depth visible on transcript + scorecard evidence. |
| 9 | Candidate classification with profile + answer quality + evidence | **Present** (post-call) / **Partial** (demo story) | Server scorecard path: precheck + model tier + verified evidence (`interviewV2.ts`). Blueprint `tiers`. Flow stores clinical `evidence` quotes. | Live page emphasizes call continuity more than tier narrative. Hallucinated quotes guarded somewhat (Phase 3 tracker). Classification quality unused if screening slots empty. | After a complete call, tier + 2–3 verified quotes matching transcript. |
| 10 | Audio/network interruptions: recover without losing context | **Present** | Client `rejoin.ts` + UI; server rejoin; agent `ConnectionGuard` + `flow.resume()`; persisted `FlowState`. Drop past grace → incomplete, not scored as finished. | Rejoin window (~120s) then dead. Mid-utterance STT loss still loses that answer. Refresh UX depends on localStorage. | Hard refresh mid-call → Rejoin → same interview id → last question continued. |

---

## PART B — QA remarks vs code

For each issue: likely root in **this** stack (not vague “LLM”), whether prompts/Flow already claim to prevent it, and why it can still fire.

| # | QA issue | Likely root cause(s) | Guardrails that claim to prevent it | Why it still fires |
| --- | --- | --- | --- | --- |
| 1 | Repeated questions already asked | **Flow + realizer + listen.** `last_question` / `_facts_line` (“do not ask again”) are soft text. Soft-skip / unclear / silence / `_restate_current_question` legitimately re-ask. Realizer paraphrases into a *new* question. Partial STT commit (`_revises_previous`) can restate. | STYLE_FOOTER + facts line; LISTEN HOLD / focus lock in `main.py`; prompts “Never invent… questions”. | No hard “already captured slots must not appear in spoken text” output check. Realizer free-forms from directive. Multiple speech starters (Director path, `SilenceMonitor.speak_move`, fillers) can re-surface a question. |
| 2 | Unnatural communication flow | **Fillers + expressiveness + endpointing + silence ladder + realizer.** Pre-rendered acks (`fillers.py`) before Director; EL expressiveness tags/pauses; dynamic endpointing vs slow answers; silence nudges. | Architecture + prompts: 1–2 short sentences, vary acks, patient silence_hold first. | Ack bucket wrong → empathy mid-flow. Endpointing ends turn early → agent jumps. Realizer adds meta (“now we will discuss”). Latency → awkward gaps then double speech. |
| 3 | Unnecessary “Haan, dheere se, koi jaldi nahi hai” mid-conversation | **Fillers (primary) + nervous wrap (secondary).** `ACKS_EMPATHETIC["hi-IN"]` includes `हाँ, ठीक है धीरे से` / `ठहरिए, कोई जल्दी नहीं`. `filler_bucket_from_text` marks empathetic on `_EMPATHY_WORDS` (includes `नहीं`, `don't`, `uncomfortable`, …) or sticky `_previous_empathy`. Flow `_wrap` only injects nervous reassurance when `nervous_events == 0`, but **fillers run before Director** and are not gated by that counter. | Flow comment: one reassurance per call; silence directives forbid pace reassurances; analyst: nervous only if explicit. | Filler path ignores Flow’s one-shot. Heuristic treats many normal answers (“मैं नहीं कर सकती diaper…”, “I don’t know”) as empathy → plays pace line. Sticky previous_empathy prolongs it. |
| 4 | Premature “did not hear” during height/weight (noise + interruptions) | **Listen / turns / unclear ladder / STT.** Body is `patient_answer_focus`, but first unclear still becomes invite/continue or later “could not hear”. False barge-in dumps scrap → `noise`/`ask_repeat`. `TurnWatchdog` salvage-or-repeat on speech-without-transcript. Silence level ≥2 asks if they can hear. | `patient_answer_focus` soft first miss; ignore non-words; adaptive interruption; discard post-false-interrupt weak audio. | Mid-dictation pause → endpoint commit empty/partial → unclear. Noise as “speech”. Watchdog and Flow both ask to repeat. Height/weight spoken slowly looks unfinished then garbled. |
| 5 | Total work experience not asked or verified (regressed) | **Flow experience ask design + slot absorb + soft-skip.** `_experience_ask` with resume prefers “one concrete resume fact” over explicit **total years**. Slots `experience_years` / `experience_settings` can soft-skip to `unknown` after retries. Post-care **experience_probe** bank can run without verifying total years if years never captured. Analyst may miss years in a long dump. | Blueprint asks years + settings; `_experience_captured` gates some paths; resume-tied probes. | Ask text no longer forces “how many years in total” when resume present. Soft-skip / unclear streak marks unknown and advances. Probe queue ≠ verification of total tenure. |
| 6 | Nursing qualification recognition failure despite clear answer | **Analysis extraction + STT + no domain parser.** Qualification is plain `kind: text` / year; `normalize.py` has phone/height/weight parsers only — **no GNM/B.Sc/ANM canonicalizer**. LLM slot_updates must catch it. Scribe may mangle “B.Sc Nursing”. Soft-skip after MAX_FOCUS_RETRIES. | Analyst schema includes slot_updates; max field attempts; reask_invalid for bad values. | Mis-hear → empty update → re-ask or give up. Homophones / English-in-Indic. No confirm step on qualification (unlike phone). |
| 7 | No wait after bed-care question; immediately next question | **Endpointing + care absorb + clinical/screening advance.** Care intro asks many duties at once; short “haan” / dump can set stances via `recover_care_updates` / analyst. Endpointing cuts before full answer → next `ask_care_item` or `_screening_next`. Thin answer graded enough to leave focus. | Care persuasion loop for gate item; MAX_CARE_ASKS; don’t clear diaper from experience-dump हाँ (commented intent). | Early commit. False accept on noisy हाँ. Realizer packs next question in same breath when not `verbatim`. Probe/finish_area after weak clinical grade. |
| 8 | Repeated “can you hear me?” after silence and after confirmation | **Liveness silence ladder.** `flow.silence(2)` = check they can hear you; `silence(3)` = still there. `SilenceMonitor` loops with spacing after each spoken nudge; `silence_level` resets on any `apply` then can climb again. Confirmation turn then quiet → new ladder. Separate from “ask_repeat” hearing apologias. | Level 1 is `silence_hold` (no speech) after QA on pace lines. Forbidden phrases on pace in nudge text. | Levels 2–3 are still hearing/presence checks by design. Spacing (~nudge + 6s) feels like nagging. Post-confirm silence restarts. Overlap with unclear “could not hear”. |
| 9 | Irrelevant salary statement mid-call | **Realizer hallucination + salary_holdout branch + missing TTS guard.** `_salary_or_holdout` / `_answer_question` intentionally speak “recruitment shares salary” when intent is compensation. Prompts forbid inventing figures / unsolicited pay. **No pre-TTS output guard** (`guards.py` only sanitizes candidate injection). | Prompts + salary_holdout “Never invent a figure”; architecture note recommends deterministic salary templates + output scan. | Realizer invents pay/offer language without candidate asking. `_mentions_comp` / off_topic gist false positive → holdout. Aside path. Soft timeout / filler oddities less likely than free-form generation. |

---

## PART C — Ideal voice agent checklist (primary sources)

Research via WebSearch + WebFetch (Oct 2026). Citations are URLs actually fetched or used as primary docs.

### Sources consulted

| Topic | URL |
| --- | --- |
| LiveKit adaptive interruption | https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/ |
| LiveKit turn-taking tuning | https://docs.livekit.io/agents/logic/turns/tuning/ |
| LiveKit noise cancellation | https://docs.livekit.io/transport/media/noise-cancellation/ |
| LiveKit turn detection blog | https://livekit.com/blog/turn-detection-and-interruption-handling |
| OpenAI voice agents (cascade vs S2S) | https://developers.openai.com/api/docs/guides/voice-agents |
| OpenAI GPT-Live migration / guardrails timing | https://developers.openai.com/api/docs/guides/live-migration |
| ElevenLabs conversation flow (silence, soft timeout, interruptions, eagerness) | https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow |
| ElevenLabs Scribe commit strategies | https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies |
| ElevenLabs Twilio barge-in pattern | https://elevenlabs.io/blog/build-voice-agent-twilio-elevenlabs |
| Pipecat Flows | https://docs.pipecat.ai/pipecat/flows/quickstart |
| Pipecat interruptions | https://docs.pipecat.ai/pipecat/fundamentals/interruptions |
| Pipecat speech input / turn detection | https://docs.pipecat.ai/pipecat/learn/speech-input |

### Industry consensus (relevant to this POC)

1. **Cascade (STT → policy → TTS) when policy must inspect text before speech** — OpenAI’s chained pipeline is for inspect/replace stages; speech-to-speech is lower latency but policy must sit on playback/actions because speech continues while checks run ([voice agents](https://developers.openai.com/api/docs/guides/voice-agents), [live migration](https://developers.openai.com/api/docs/guides/live-migration)). This repo correctly chose cascade for `/elevenlabs-interviewer`.
2. **Deterministic flow / tools own transitions; LLM realizes** — Pipecat Flows nodes + tool transitions ([Flows quickstart](https://docs.pipecat.ai/pipecat/flows/quickstart)); same idea as InterviewFlow `Move`s.
3. **Barge-in ≠ every VAD blip** — LiveKit adaptive interruption vs VAD; Pipecat min-words / mute / empty-user-turn; ElevenLabs interruption ignore-terms & patient eagerness for data collection.
4. **Noise: one canceller, agent-side preferred** — LiveKit: enhanced NC on agent; do not also run frontend noise models ([noise cancellation](https://docs.livekit.io/transport/media/noise-cancellation/)). Repo already turns browser NS off.
5. **Scribe: commit on silence / turn boundary; optional background filter; context on reconnect** — [commit strategies](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies).
6. **Fillers for LLM latency ≠ emotional coaching mid-answer** — ElevenLabs soft timeout fillers are “thinking” audio, once per turn ([conversation flow](https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow)).
7. **On interrupt: cancel LLM/TTS, flush queued audio, commit only spoken text** — [Pipecat interruptions](https://docs.pipecat.ai/pipecat/fundamentals/interruptions).
8. **Guardrails before the user hears speech** for high-stakes content — OpenAI: if every reply must pass a check, put it on the playback path.

### CRITICAL considerations × this repo

| # | Consideration | Why it matters | Repo status | Gap severity |
| --- | --- | --- | --- | --- |
| C1 | Single speech arbiter (one path starts TTS per turn) | Double replies / overlapping “hear me?” + question | Mostly Director/`speak_move`; **also** SilenceMonitor, fillers `session.say`, verbatim `say` | **High** |
| C2 | Adaptive barge-in + false-interrupt resume | Ward noise must not steal floor | Wired in `turns.py` (`interruption_mode=adaptive`); discard windows in `main.py` | **Med** (tuning / Cloud vs self-host) |
| C3 | Endpointing patient for open / numeric dictation | Height, phone, experience stories need longer silence | Dynamic endpointing; uncovered langs higher min_delay; `patient_answer_focus` only affects Flow unclear, **not** LiveKit delays per question | **High** |
| C4 | Agent-side voice isolation; browser NS off | Double NC ruins ASR | Krisp required in Phase 1; client NS false | **Low** (ops/config) |
| C5 | Unclear vs silence vs backchannel are different policies | Same spoken line for all three feels broken | Separate moves exist; QA shows conflation in practice | **High** |
| C6 | Code-switching ASR + language policy | Hinglish/Tanglish is the product | Join language + Scribe secondaries; no robust mid-call policy | **Med** |
| C7 | Domain entity recovery (phone, body, qualification, years) | Screening credibility | Strong phone/body parsers; **weak** qualification/years | **High** |
| C8 | Flow-owned next move; realizer cannot invent topics | Salary / repeat / skip | Flow+prompts strong; **no TTS allowlist/scan** | **High** |
| C9 | Fillers = latency ack only, not policy emotion | “Dheere se” mid-call | Empathetic ack list + sticky heuristic | **High** |
| C10 | Silence: hold → soft presence → end; never nag hearing | Demo trust | Level 2 is explicitly “can you hear” | **High** |
| C11 | Disconnect/rejoin preserves FlowState | Dropped Wi‑Fi | Present (120s) | **Low–Med** |
| C12 | Clinical grade → follow-up tools, not free chat | Interviewer credibility | `_clinical` present; depends on analyst | **Med–High** |
| C13 | Evaluate task outcome + timing separately | OpenAI Crawl/Walk/Run | Phase 1 matrix for voice; brain QA informal | **Med** |
| C14 | Preemptive generation off for controllable demos | Race ahead of turn end | POC plan: preemptive off | **Low** (keep off) |

---

## PART D — Rewrite vs repair (markdown recommendation only)

**Overall:** Prefer **surgical rewrite of broken outer loops** (fillers, silence wording, entity extractors, TTS guard) over deleting InterviewFlow. Flow is large but coherent and unit-tested; inventory does **not** show it unsalvageable. Full agent rewrite would throw away the correct cascade+policy split OpenAI/Pipecat recommend.

| Subsystem | Recommendation | Rationale |
| --- | --- | --- |
| InterviewFlow state machine | **Keep** (repair edges) | Stages, gates, clinical probes, soft-skip, facts line are the right control plane. Fix experience-ask wording, silence copy, care wait semantics — do not replace with free-form LLM planner. |
| Fillers / expressiveness | **Surgically rewrite** | Highest demo damage per LOC. Empathy bucket + sticky flag + ACKS_EMPATHETIC pace lines contradict Flow’s one-shot nervous policy. Rewrite: latency-only neutral acks; empathy only from Flow `Move.tone` / explicit nervous move; never pace coaching from STT heuristics. |
| Listen / turns | **Repair + tighten** | Keep LiveKit adaptive + ListenFloor. Add per-focus endpointing profiles (body/phone/experience longer). Collapse duplicate ask-repeat paths (Flow vs TurnWatchdog vs silence). |
| Prompts / realizer | **Repair** | Keep directive-only realizer. Add must-include / forbidden post-check before TTS (salary, hear-me spam, second question). Prefer `verbatim` / templates for salary, silence, phone (already partly done). |
| Analysis extraction | **Repair** (targeted) | Keep structured analyst. Add deterministic post-parsers / dictionaries for qualification + total years; tighten nervous/unclear; reduce false partials on body. |
| Phone / body parsers | **Keep** | `phone_speech.py` / `normalize.py` are the right pattern — **extend** same pattern to qualification & experience years rather than new architecture. |
| Liveness (silence / rejoin) | **Surgically rewrite silence copy + escalation** | Keep ConnectionGuard/rejoin. Rewrite silence ladder: no “can you hear me?” loops; presence check once; then incomplete close. |
| Director glue | **Keep** | Early analyze + decide is sound; do not merge policy into voice model. |

**One-liner:** Keep Flow/Director; surgically rewrite fillers + silence escalation + add output guard + strengthen screening entity parsers; do not full-rewrite the agent.

---

## PART E — Master-plan parts (R&D → plan → implement → test later)

Few combined workstreams — not a task laundry list.

### Part 1 — Speech arbitration & turn patience  
**Goal:** One arbiter; patient endpointing on body/phone/experience; no premature “did not hear” / cut-off after care.  
**Closes:** Client 4, 7 (pauses/interruptions); QA 2, 4, 7, 8.  
**Main files:** `turns.py`, `listen.py`, `liveness.py`, `main.py` (discard/watchdog), `config.py` endpointing settings.

### Part 2 — Filler / empathy / silence spoken policy  
**Goal:** Acks only for latency; emotion only when Flow says so; silence ladder without hearing-nag.  
**Closes:** Client 7; QA 2, 3, 8.  
**Main files:** `fillers.py`, `expressiveness.py`, `flow.silence` / `_wrap`, `main.py` filler-before-Director ordering.

### Part 3 — Screening entity truth (qualification + total experience)  
**Goal:** Reliable capture/confirm of qualification (+ year) and **total** nursing years before care/clinical; resume-tied probes deepen, not replace, tenure.  
**Closes:** Client 5 (screening honesty), 9 (profile inputs); QA 5, 6.  
**Main files:** `normalize.py`, `analysis.py`, `flow.py` (`_experience_ask`, absorb/soft-skip), `nursing.json` field asks/confirm flags.

### Part 4 — Realizer guardrails before TTS  
**Goal:** Block invented salary/outcome/second-question; force templates for salary_holdout / silence / high-risk moves.  
**Closes:** Client 8 (trust); QA 1, 9.  
**Main files:** new small output-guard module (or extend `guards.py`), `prompts.py`, `main.py` `speak_move` / `generate_reply` path, salary_holdout verbatim variants.

### Part 5 — Clinical adaptivity + scorecard evidence (after Parts 1–4 stabilize calls)  
**Goal:** Partial/incorrect → real probes; contradictions once; tier evidence matches transcript.  
**Closes:** Client 5, 6, 8, 9; residual QA 1/7 in clinical.  
**Main files:** `flow._clinical`, `analysis.py` clinical schema, `server/v2` classification/scorecard.

**Suggested order:** Part 2 + Part 1 in parallel (demo-earliest), then Part 3, then Part 4, then Part 5.

---

## Top demo-damage gaps (ranked)

1. **Empathetic fillers / “dheere se” mid-call** — breaks trust instantly; easy surgical fix.  
2. **Premature “did not hear” + hearing-nag silence ladder** — especially on height/weight and after confirm.  
3. **Screening entity misses (qualification, total experience)** — call “works” but product looks incompetent.  
4. **Realizer invents / repeats (salary, already-asked)** — no pre-TTS guard.  
5. **Turn patience / care cut-off** — endpointing advances before candidate finishes.

---

## Recommendation to the team

- **Rewrite vs repair:** Surgical rewrite of fillers + silence + TTS guard + entity parsers; **keep** InterviewFlow/Director.  
- **Next step:** Implementation has a plan. Start at **P2-01** in `docs/phase-2-quality-tracker.md` (speech arbiter). Do not re-run this gaps analysis unless new QA transcripts contradict the roots in Part B.
