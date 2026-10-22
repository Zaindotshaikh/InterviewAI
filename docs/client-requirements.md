# Client requirements

## 1. Purpose

This note captures how the client’s interviewers talk with nursing candidates, and what the product has to do before the next call. It is a requirements record, then a readiness check of this repo against that record.

The client wants a better sense of the questions they ask and how their interviewers interact with candidates. The product should understand the candidate, adapt to the conversation, and conduct the interview like a human interviewer.

## 2. Screening round

The initial screening round broadly covers:

- City the candidate is applying for
- Phone number
- Qualification and year of passing
- Height and weight
- Nursing experience / relevant exposure
- Comfort with essential patient-care responsibilities, including diaper care

The AI must not be limited to a fixed questionnaire.

**Diaper-care example and gate.** If a nurse says they are not comfortable with diaper care, the AI should naturally explain that this is an essential part of nursing and attempt to address the concern. If the candidate still refuses, they should not proceed to the clinical assessment.

## 3. Clinical round

In the clinical round, the candidate’s response should determine what the AI asks next. It should be able to probe, clarify, challenge an answer where required, and adjust the depth of assessment rather than simply moving to the next question in a predefined list.

The eventual objective is to evaluate whether AI can potentially perform the role of a clinical interviewer.

## 4. Next-call exploration areas

This is not an exhaustive list. These are the areas the client particularly wants to explore on the next call.

### 4.1 AI interviewer experience

A visible face or avatar for the candidate to interact with, rather than only a screen or voice-based interaction.

### 4.2 Multiple Indian languages

English, Hindi, Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, and other relevant Indian languages.

### 4.3 Multi-language conversations

Ability to understand and respond when candidates switch between languages, such as Hinglish or Tanglish.

### 4.4 Regional language and speech

Understanding regional accents, slang, colloquial language, and imperfect pronunciation without affecting the assessment of the candidate’s actual knowledge.

### 4.5 High background noise

Ability to conduct and accurately assess an interview in highly noisy environments, including recognising when a response was not heard clearly and asking the candidate to repeat.

### 4.6 Dynamic clinical assessment

Handling incomplete, incorrect, or partially correct answers through relevant follow-up questions rather than moving on.

### 4.7 Conversation context

Identifying contradictions or inconsistencies in responses and probing them appropriately.

### 4.8 Candidate behaviour

Handling nervous candidates, long pauses, “I don’t know” responses, interruptions, and requests to repeat or rephrase a question.

### 4.9 Clinical interviewer capability

Demonstrating how the AI can assess actual clinical knowledge and potentially replace the interviewer, not just conduct screening.

### 4.10 Candidate classification

Using both the candidate’s profile and the quality and content of their answers to classify them into the appropriate tier, with clear reasoning and evidence behind the assessment.

### 4.11 Audio and network interruptions

Recovering from interruptions without losing the context of the conversation.

## 5. Guiding principle

The list above is not exhaustive. The product should understand the candidate, adapt to the conversation, and conduct the interview like a human interviewer, rather than follow a templatized question flow.

## 6. Current product surfaces

The team is working against two live routes. Both are client entry points onto the same v2 interview (blueprint, director, and scoring). They differ in the voice path. Architecture detail lives elsewhere.

- https://interviewai-418h.onrender.com/gpt-live-interviewer — full-duplex GPT-Live voice (`voiceProvider=gpt_live`). The interviewer is a presence orb, not a face.
- https://interviewai-418h.onrender.com/elevenlabs-interviewer — cascade speech path with ElevenLabs text-to-speech forced for that route. The interviewer is a presence orb, not a face.

A third local route, `/avatar-interviewer`, turns on a Tavus face. It is not one of the two surfaces above.

## 7. Readiness against this repo

Status is what the code and the checked-in env **names** support today. Configured names (no secret values):

- Repo root `.env`: `OPENAI_API_KEY`, `REALTIME_MODEL`, `CHAT_MODEL`, `PORT`, `COMPANY_NAME`, `TARGET_MINUTES`.
- `agent/.env`: `PROVIDER_MODE=openai`, `STT_PROVIDER=elevenlabs_scribe`, `STT_SCRIBE_FALLBACK=openai`, `TTS_PROVIDER=openai`, `LLM_PROVIDER=openai`, `LLM_MODEL`, `OPENAI_STT_MODEL`, `GPT_LIVE_MODEL`, `GPT_LIVE_VOICE`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL`, `DIRECTOR_MODEL`, `CLINICAL_DIRECTOR_MODEL`, `NOISE_PROVIDER=krisp`, `VOICE_EXPRESSIVENESS=engine`. No `TAVUS_*` variables.
- `server/.env`: `PROVIDER_MODE=openai`, `STT_PROVIDER=openai`, `TTS_PROVIDER=openai`, `LLM_PROVIDER=openai`, `REALTIME_MODEL`, `REALTIME_VOICE`, plus `TAVUS_API_KEY`, `SARVAM_API_KEY`, and `ELEVENLABS_API_KEY` present as names. The agent process does not read the server file.

| Requirement | Status | Evidence | Gap |
| --- | --- | --- | --- |
| Screening topics (city, phone, qualification and year, height and weight, experience / exposure, essential care including diaper care) | Present | `server/v2/lib/blueprints/nursing.json` screening fields and care items; outline in `server/v2/lib/planBuilder.ts` | Spoken collection is implemented. Live accuracy on the two routes is not proven in this repo. |
| Diaper-care explanation, then stop before clinical if they still refuse | Present | Gate item `diaper_care` with two persuasion lines in `nursing.json`; persuasion and `gate_failed` in `agent/interview/flow.py`; `not_eligible` without a model call in `server/v2/lib/classification.ts` and `classification.test.ts` | None in code. Needs a live demo of refuse-after-explanation. |
| Clinical round follows the answer (probe, clarify, challenge, change depth), not a fixed list | Present | `agent/interview/flow.py` (`probe`, `clarify`, `challenge`, `probe_simpler`, level by experience); `agent/interview/director.py`; tests in `agent/tests/test_flow.py`. Plan steps are an outline only (`planBuilder.ts`). | Depth is capped (`max_probes_per_area`, `max_challenges_per_area`, `clinical_areas_target` in the blueprint). It is adaptive inside that map, not an open clinical interview. |
| Visible face / avatar | Partial | Tavus start in `agent/main.py` (`_start_tavus_avatar`); video element in `client/src/v2/components/LiveInterview.tsx`; route `/avatar-interviewer` in `client/src/App.tsx` | The two live routes do not pass `avatar`. They render `PresenceOrb`. `TAVUS_API_KEY` is on `server/.env` only. `agent/.env` has no `TAVUS_API_KEY`, `TAVUS_FACE_ID`, or `TAVUS_PAL_ID`. The agent is what starts the face. |
| Multiple Indian languages | Partial | Language list in `server/v2/lib/types.ts` and `agent/interview/language.py`: English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, plus Gujarati, Punjabi, Odia. Picker in `client/src/v2/components/LanguagePicker.tsx`. Per-language voice notes in `agent/interview/prompts.py`. | The GPT-Live route uses OpenAI realtime (`GPT_LIVE_MODEL`, `GPT_LIVE_VOICE`), not an Indic STT/TTS stack. Sarvam is implemented in `agent/providers/factory.py` but `PROVIDER_MODE` / `STT_PROVIDER` / `TTS_PROVIDER` are OpenAI (Scribe on the agent for the cascade path). |
| Hinglish / Tanglish and mid-conversation language switches | Partial | Prompts tell the model to follow mixed speech (`planBuilder.ts`, `prompts.py`). Scribe secondary languages in `factory.py` (`en`, and `hi` for non-Hindi Indic). Cascade-only tool `switch_language` in `agent/main.py`. Script detection logs `language.detected`. Phrase lists in `agent/interview/indic_phrases.py`. | GPT-Live has no tool channel, so it cannot call `switch_language`. Detected script is logged and does not retarget STT/TTS. Romanized Hinglish/Tanglish does not match native-script detection. GPT-Live voice is fixed after session start (`agent/config.py`). |
| Accents, slang, colloquial speech, imperfect pronunciation must not change the knowledge score | Partial | Scoring prompt in `server/v2/lib/classification.ts` says not to penalise accent, grammar, code-switching, or nervousness. Glossary slang hints in `server/v2/lib/glossary/*.json`, injected by `planBuilder.ts`. GPT-Live accent block in `prompts.py`. | Glossaries are short token lists. There is no measured check that accent or pronunciation errors leave the tier unchanged. |
| High background noise, including asking the candidate to repeat | Partial | `NOISE_PROVIDER=krisp` builds Krisp BVC in `agent/providers/factory.py` and is applied in both session paths in `agent/main.py`. Unclear audio becomes `ask_repeat` / `noise_help` in `flow.py`. False barge-in audio is discarded. | Plugin availability can fall through to no cancellation. There is no in-repo proof that a noisy interview is still scored accurately. |
| Incomplete, incorrect, or partial clinical answers get follow-ups | Present | Same flow moves as the clinical round; unit tests cover partial → probe and wrong → challenge (`agent/tests/test_flow.py`). | Probe and challenge counts are capped, then the flow moves on. |
| Contradictions probed | Present | `probe_contradiction` in `flow.py`; open contradictions affect tier flags in `classification.ts`; tests in `test_flow.py`. | Capped at `max_contradiction_probes` (2). |
| Nervous candidates, pauses, “I don’t know”, interruptions, repeat / rephrase | Present | Nervous wrap and intents in `flow.py`; silence ladder in `flow.silence` and `agent/interview/liveness.py` (`SilenceMonitor`); repeat/rephrase/don’t-know tests in `test_flow.py` and `agent/tests/test_indic_phrases.py`. | Behaviour is directive-driven. Empathy tone is off unless `DIRECTOR_EMPATHY_TONE` is set (it is not in `agent/.env`). |
| Assess clinical knowledge well enough to stand in for a clinical interviewer | Partial | Clinical areas, levels, key points, and red flags in `nursing.json`. Director uses `CLINICAL_DIRECTOR_MODEL` on clinical turns (`director.py`, `agent/main.py`). | The interview still targets about four areas inside a fixed blueprint and a time cap. That is a structured clinical screen, not evidence the AI can replace a human clinical interviewer. |
| Tier from profile plus answer quality, with reasoning and evidence | Present | Tiers in `nursing.json` (`tier_1`–`tier_3`, `not_eligible`, `needs_review`). Rules plus model in `server/v2/lib/classification.ts`; evidence quotes checked against the transcript; scorecard fields in `server/v2/routes/interviewV2.ts`. | Model tier quality depends on a live transcript. Unsafe or thin evidence is forced to `needs_review`. |
| Recover from audio or network drops without losing context | Partial | Flow state is persisted (`agent/main.py` `_persist`). `ConnectionGuard` in `agent/interview/liveness.py` waits `RECONNECT_GRACE_SECONDS` (default 120) and repeats the last question via `flow.resume`. Client shows `reconnecting` in `client/src/v2/hooks/useLiveKitInterview.ts`. | A full disconnect sets the client phase to ended. The test pages do not rejoin the same interview after a hard drop. Recovery is for a participant who returns to the same room inside the grace window. |
| Human interviewer, not a template | Partial | v2 system prompt: controller directive each turn, not a questionnaire (`planBuilder.ts`). Flow owns what to learn; the model only phrases it (`flow.py`). | The two live UIs are test join pages. Question choice is still bounded by the nursing blueprint. v1 `/i/*` realtime screens are a separate path and are not these requirements. |

## 8. Verdict and what must be true before moving ahead

**Verdict: partially ready.**

Screening, the diaper-care gate, adaptive clinical follow-ups, contradiction probes, behaviour handling, and tiering with evidence are implemented and covered by tests. The two live routes exist and share that flow.

They are not ready to carry the next call as specified. Before moving ahead, these need to be true on the routes that will actually be shown:

1. **A face on the demo surface.** `/gpt-live-interviewer` and `/elevenlabs-interviewer` are voice plus a presence orb. The Tavus path is a different route, and the agent env that starts the avatar does not set `TAVUS_API_KEY`, `TAVUS_FACE_ID`, or `TAVUS_PAL_ID`.
2. **Language switching on the voice path in use.** A language is chosen at join. GPT-Live cannot call `switch_language`. Hinglish and Tanglish on that route depend on the model prompt, not a retargeted speech stack. The configured providers are OpenAI / ElevenLabs Scribe, not the Sarvam Indic path the code also contains.
3. **A noisy-call check on those same routes.** Krisp and “please repeat” exist in code. Nothing in the repo shows that a loud environment is still assessed fairly.
4. **A live clinical-and-tier pass.** The blueprint can probe and classify. The next call still has to show, on one of the two URLs, that follow-ups track the answer and that the tier cites the candidate’s profile and what they actually said.
