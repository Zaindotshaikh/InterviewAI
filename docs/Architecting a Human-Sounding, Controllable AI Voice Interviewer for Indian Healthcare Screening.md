# Architecting a Human-Sounding, Controllable AI Voice Interviewer for Indian Healthcare Screening

**Bottom line:** Keep your deterministic InterviewFlow as the only component allowed to decide what happens next. Make the voice LLM a tightly scoped "realizer" that turns one directive per turn into one or two spoken sentences. Put a fast deterministic output guard between the LLM and TTS. Most hallucination, drift and double-reply bugs in stacks like yours come from more than one component being allowed to start speech, not from the model choice. For voice, stay on ElevenLabs v4 Turbo but A/B test Sarvam Bulbul for Hindi/Marathi. Add naturalness through deterministic post-processing, not free-form LLM audio tags. For turn-taking, use LiveKit's adaptive interruption plus per-question endpointing, which beats trying a full-duplex model.

## TL;DR

- **Control:** Use a hybrid "process calling" architecture, as in Rasa CALM, Pipecat Flows, LiveKit AgentTask/TaskGroup and Sierra's supervisors-plus-deterministic-guards. The state machine picks the move; the LLM only words it, using node-scoped prompts and tools.\[1\] A streaming regex/allowlist guard blocks salary, outcome and promise language before TTS. Out-of-scope questions get deterministic deflection templates.
- **Naturalness:** The biggest wins are native-sounding voices, short varied phrasing and sparse, rule-based acknowledgments and fillers at turn starts, not heavy audio tags. The best Hindi/Marathi evidence is vendor-reported. Sarvam's Bulbul v3 led at 8 kHz telephony in a blind study it commissioned. For full-band audio, MIT Sloan Management Review Middle East reports that Sarvam "acknowledged that ElevenLabs' v3 alpha led in overall audio quality", although Sarvam's current TTS page now claims Bulbul v3 was preferred in both categories. That matters for you because browser WebRTC is full-band. The realistic route to a native accent on ElevenLabs is a consented Instant Voice Clone of a real Hindi/Marathi-speaking recruiter. Professional Voice Cloning works only on your own verified voice and needs the Creator plan or above.
- **Turn-taking:** Use one speech arbiter, adaptive interruption (min_duration ≥0.5 s, false-interruption resume), the LiveKit audio turn detector with per-question endpointing (longer max_delay for open questions), Krisp BVC voice isolation, and LLM-level "side-talk / unclear audio → stay silent or re-ask" rules. Full-duplex models are not production-ready for Hindi/Marathi screening.

## Key Findings

1. Everyone in industry has converged on the same pattern: **language from the LLM, logic from deterministic code, policies enforced by supervisors and non-model guards.** Rasa: "The LLM interprets what the user wants. The logic decides what happens next."\[2\] Pipecat: "monolithic prompts with many tools lead to hallucinations and lower accuracy."\[3\] Sierra: "Deterministic guards: Non-model checks that can't be talked out of doing their job."\[4\]
2. Your architecture split (Voice LLM = wording, InterviewFlow = policy, Director = analysis) is already right. Failures usually come from leaks: the voice LLM sees the whole blueprint, the Director can trigger speech, there's no output validation, or the LLM gets an open-ended "continue the interview" instruction.
3. Eleven v4 Turbo launched Sep 28, 2026, with 90+ languages and inline audio tags. ElevenLabs' v4 page says it "has a median inference latency of ~100 ms, time to first speech of ~150 ms". In the same ElevenLabs-run WebSocket comparison, datanorth.ai reports Cartesia Sonic 3.6 at 262 ms and OpenAI GPT-4o mini TTS at 814 ms. SSML `<break>` is not supported; use `[pause]`/`[long pause]` or punctuation instead. No independent latency tests exist yet.
4. Turn-detection models now cover Hindi and Marathi, but Marathi lags and the training data is mostly synthetic. Daily reports Pipecat Smart Turn v3 at 93.44% on Hindi (1,295 test samples) but 87.60% on Marathi (774 samples). The indic-smart-turn repo says Smart Turn v3.2's Indic data is "about 82% synthetic TTS". That community fine-tune was trained on 51,917 IndicVoices clips (AI4Bharat) of "real two-person phone conversations… not synthetic TTS". It reports 3–14 point gains over Smart Turn v3.2 int8 across Indian languages.
5. At about 100 twelve-minute interviews a day, infrastructure (STT + TTS + LiveKit) costs only a few hundred dollars a month. The LLM, especially with a second Director model on every turn, is likely your largest variable cost.

---

## Problem 1 — Hallucination and control of the agent "brain"

### Main approaches in industry

| Approach | How it works | Who uses it | Strengths | Weaknesses |
|---|---|---|---|---|
| Pure LLM-driven flow (one big prompt + tools) | The LLM reads the whole blueprint and decides the next move | Most hobby agents; the default in many no-code builders | Most fluent and adaptive | Drift, invented questions, skipped steps, promise-making; hard to test |
| Node/graph flows | Each node has its own focused prompt and tool set; transitions happen through function calls | Pipecat Flows, LiveKit AgentTask/TaskGroup, ElevenLabs Agent Workflows, Vapi/Retell-style flow builders | The LLM only sees the current task; steps are auditable | The LLM still chooses transitions unless you make them deterministic |
| Process calling / CALM | The LLM emits *commands* (e.g., "set slot", "candidate asked off-topic question"); a deterministic engine runs the business logic | Rasa CALM | Strongest guarantees; cheap; debuggable | Less "magic"; needs flow design work |
| Goals + guardrails + supervisors | An LLM drives within declared policies; supervisor models check inputs and outputs; deterministic guards enforce hard rules | Sierra (Agent SDK, supervisors), PolyAI (Raven 3.5 out-of-domain token) | Handles open-ended conversations well | Built for customer service, not fixed scripts; supervisors add latency\[5\] |
| Domain-tuned LLM | A model post-trained for voice customer-service behavior | PolyAI Raven | Fast, tuned for voice | Proprietary; not available for your stack\[6\] |

Sierra describes a layered pipeline: "A supervisor agent screens the input. The agent draws on the relevant content and applies the relevant policies. Another supervisor reviews the proposed response. A deterministic guard scans the output for sensitive data."\[4\] PolyAI says Raven 3.5 "flags it in its output with a special token" when a caller asks something outside the agent's scope.\[5\] Both are vendor descriptions, not independent evaluations.

### Why your agent still invents questions

Common root causes in hybrid stacks:

- **The voice LLM sees the full blueprint or full history** and "helpfully" asks the next question early, or rephrases a question into a different one.
- **The directive is open-ended** ("continue the interview naturally") rather than a single concrete move.
- **No output contract.** Free text goes straight to TTS, so nothing checks that the utterance actually contains the required question.
- **More than one component can start speech.** The Director, timeouts, and the on_user_turn handler can each call `generate_reply()` or `say()`. This also causes double replies (see Problem 3).

### Recommended architecture for your use case

**1. InterviewFlow owns every move.** For each turn, it emits a typed directive:

```
Directive {
  move: ASK_QUESTION | FOLLOW_UP | ACK_AND_ADVANCE | CLARIFY | REASSURE_AND_REASK | DEFLECT | CONFIRM_VALUE | CLOSE
  question_id, canonical_text_hi, canonical_text_mr, canonical_text_en
  must_include: ["<key concept/phrase>"]     # validated after generation
  ack_style: brief | empathetic | none
  language: hi | mr | en | mixed
  max_sentences: 2
  forbidden_topics: [salary_amount, selection_outcome, shift_guarantee, ...]
}
```

**2. The voice LLM is a realizer, not a planner.** Its prompt contains only the persona, style rules, the current directive and the last 2–4 turns. It does not see the full blueprint or the list of future questions. Ask it for structured output, e.g. `{"ack": "...", "utterance": "...", "language": "hi"}`, using JSON-schema/structured outputs, and stream only the `utterance` field to TTS. For the highest-risk moves (salary, outcome, consent, closing), skip the LLM and speak **pre-approved templates**. Rotate between 3–5 variants per language to avoid repetition.

**3. Use node-scoped tools.** Following Pipecat Flows and LiveKit TaskGroup, give the voice LLM at most 2–3 tools per state, e.g. `record_answer`, `candidate_asked_question`, `unclear_audio`.\[3\] These tools report *what the candidate did*. They never choose the next state; InterviewFlow does that from the tool result. This is the CALM "commands, not decisions" pattern.\[7\]

**4. The Director/analyst runs asynchronously and never speaks.** It reads transcripts and writes to shared state, e.g. "answer to Q7 is vague → recommend FOLLOW_UP:probe_example" or "candidate seems anxious". InterviewFlow reads that state at the next turn boundary and may accept or ignore the recommendation. This keeps the Director's latency off the critical path. LiveKit's "supervisor pattern" docs and Sierra's supervisors are relevant references, but in your case the Director should *advise the policy*, not interrupt speech.\[8\]\[9\]

**5. Put a streaming output guard before TTS.** It is a deterministic filter on the LLM text stream, implemented in LiveKit's `llm_node`/`tts_node` pipeline hooks or as a sentence-buffered wrapper:
- Block currency amounts and digits near salary words (₹, rupaye, salary, vetan/वेतन/पगार, "per month", "lakh"); outcome words (selected, hired, "aapka selection", "pakka", guarantee/गारंटी, "confirm ho gaya"); and commitments (promise, "we will give", "milega hi").
- Check `must_include` coverage for ASK_QUESTION moves, using keyword or fuzzy match against the canonical question.
- On violation, drop the sentence and speak the canonical template instead. Log the event as a regression test case.
- Buffer sentence by sentence. TTS already needs sentence-level chunks, so the guard adds almost no latency.

**6. Use a deterministic deflection pattern for out-of-scope questions.** When the realizer calls `candidate_asked_question(topic)`, InterviewFlow classifies the topic (salary, location, shift, joining date, outcome, other). For anything you're not allowed to answer, it returns a DEFLECT directive with a template such as:
- Hindi: "Achha sawaal hai — maine note kar liya hai. HR team aapko iske baare mein detail mein bata degi. Chaliye, aage badhte hain…"
- English: "Good question — I've noted it, and the HR team will get back to you on that. Let's continue…"

Log the question so HR actually follows up. Answer only facts that are in an approved FAQ table, rendered verbatim, never generated.

**7. Adaptive follow-ups within a budget.** Give each question a follow-up budget (e.g., at most 1 probe and 1 clarify) and an enumerated set of follow-up types: *clarify unclear answer, ask for an example, ask for duration/years, confirm a number*. The Director or a cheap classifier picks the type, InterviewFlow approves it against the budget, and the realizer words it. This gives you adaptiveness without letting the model invent new topics.

**8. Persuasion and reassurance ("accept as many candidates as possible").** Model it as a bounded sub-state, not as free-form LLM persuasion:

```
REQUIRED_TASK_Q (e.g., "Are you comfortable with night shifts / patient lifting / diaper change?")
  └─ answer=NO or HESITANT
       → REASSURE_AND_REASK (once): acknowledge the concern + one factual reassurance from an approved list
         ("training is provided", "you'll work alongside a senior caregiver at first")
         + soft re-ask ("Training ke baad, kya aap yeh karne mein comfortable honge?")
       → answer=YES → record "yes_after_reassurance"
       → answer=NO again → record "declined_after_reassurance", thank them warmly, MOVE ON (no third ask)
```

Rules that keep this ethical and defensible: at most one re-ask; reassurances must be true and pre-approved by HR; no pressure language; always record both the original and final answer so HR can see the candidate first declined. This raises acceptance without becoming coercive, and gives reviewers an audit trail.

**Concrete settings:** temperature 0.3–0.5 for the realizer (variety comes from template rotation, not sampling); max output of about 60 tokens per turn; system prompt under about 800 tokens. Test a smaller, faster model (e.g., GPT-4o-mini-class or GPT-4.1-mini-class) as the realizer, since its job is now narrow. Keep the larger model for the Director.

---

## Problem 2 — Robotic, non-human voice

### What actually drives perceived naturalness (in order of impact)

1. **Voice and accent fit.** A voice that sounds native to Hindi/Marathi speakers matters more than any prosody trick. Your GPT-Live-1 experience (foreign-sounding Indian accents) is consistent with this.
2. **Spoken-style text.** Short sentences, contractions, Hinglish where candidates use it, no list-like enumerations, numbers written in words. OpenAI's realtime prompting guide notes the model "closely follows sample phrases" and recommends an explicit variety rule ("Do not repeat the same sentence twice. Vary your responses") to avoid sounding robotic.\[10\]\[11\]
3. **Timing.** Fast first audio and correct turn-taking (Problem 3). A late or overlapping reply sounds more robotic than a flat voice.
4. **Micro-behaviors.** Acknowledgment tokens ("Achha", "Theek hai", "Hmm, samjha"), occasional fillers, a breath or pause before a hard question.

### Evidence on disfluencies and fillers

- An arXiv study (2412.12710) that inserted disfluencies into LLM output with a fine-tuned Llama-2 and Bark TTS found they "significantly increase the perceived spontaneity" but made speech slightly harder to follow.\[12\]
- LREC 2022 work on filler insertion found fillers help only when the TTS can voice them naturally. With read-speech TTS, the effect flipped.\[13\]
- Earlier embodied-agent work (Pfeifer & Bickmore) found mixed reactions: some users expect a machine to speak fluently.\[14\]
- **Implication:** use fillers sparingly, mostly at turn starts and before reflective questions, never inside critical information such as dates, numbers or instructions. For candidates with lower literacy who are listening on a phone speaker, clarity matters more than spontaneity.

### LLM-inline tags vs deterministic post-processing

**Recommendation: deterministic post-processing, with an optional constrained-LLM "hint" field.**

- Let InterviewFlow and a small post-processor decide *where* expressiveness goes: prepend an acknowledgment variant, add `[pause]` before a sensitive question, use a warmer tag on the closing. Draw from an allowlist and rate-limit it (e.g., at most 1 tag per utterance, at most 1 filler per 3 turns, no repeats within 5 turns).
- If you let the LLM suggest emotion, have it output an enum (`tone: neutral|warm|empathetic|upbeat`) that you map to tags. Never let it write free-form bracket text. ElevenLabs' own guidance says tags "MUST describe something auditory" and should be placed "immediately before the dialogue segment they modify." Third-party guides report tags sometimes being spoken aloud instead of performed, which is unacceptable in a live interview.\[15\]\[16\]\[17\]
- Stability settings: guides report that the most stable/"Robust" mode suppresses tag responsiveness.\[18\] For an interviewer, favor consistency (mid-to-high stability) and few tags over drama.
- v4/v3 do not support SSML `<break>`. Use `[pause]`, `[long pause]`, ellipses and sentence structure.\[15\]\[19\] The speed setting ranges from 0.7 to 1.2.\[15\] For Hindi/Marathi phone listening, try 0.9–0.95.
- **Pre-render your fixed audio.** Greeting, consent, deflection templates and the closing can be pre-generated with the best model (eleven_v4, not Turbo), QA'd by native listeners and cached. That gives you zero latency and guaranteed quality for about 30–40% of agent speech.

### Voice cloning: does it help for Hindi/Marathi?

| | Instant Voice Clone (IVC) | Professional Voice Clone (PVC) |
|---|---|---|
| Plan | Starter and above | Creator and above |
| Audio needed | Short sample (under ~2 min; with v4, Windows Report says IVC can capture a voice "with high fidelity from just 10 seconds of audio") | Minimum 30 min; ElevenLabs recommends closer to 2–3 hours |
| Whose voice | Any voice you are authorized to use (consent confirmation) | **Only your own voice**, verified with a live voice-captcha |
| Method | Conditioning at inference time, no training | Fine-tuning |
| Notes | ElevenLabs historically recommended IVC/designed voices over PVC for v3 tag performance, but the v4 FAQ says "Professional Voice Clones are supported again", so that advice may be out of date | Highest fidelity; can be shared in the Voice Library |

**Practical recommendation:**
- The fastest route to a native accent is a **consented IVC of a real Hindi/Marathi-speaking recruiter or voice artist** recording 1–2 minutes of *conversational* (not read) speech in the target register. The clone copies the speaking style of the samples, so record warm, interview-style speech.\[20\]
- If the person is a team member, they can create a PVC themselves (on their own account) and share it.\[21\]
- Get a signed consent and licensing agreement covering AI use, scope, duration and revocation. Under India's DPDP Act 2023 a voice recording is personal data, so treat this as a legal review item.
- **Fine-tuning ElevenLabs on your own Indian-language corpus:** I found no public self-serve option beyond PVC, which fine-tunes on a single speaker's voice. A PVC of a native Marathi speaker is the closest available equivalent.
- Before cloning, try library voices filtered for Hindi plus Indian accent. A good library voice is often enough, and cloning only helps if the source speaker is better than the library.

### Indian-language TTS alternatives (evidence quality flagged)

- **Sarvam Bulbul v3 (and newer v4):**
  - Trained from scratch on Indian speech in 11 languages, with LLM-inferred prosody and code-mixed and Indian-number handling.\[22\]\[23\]
  - Sarvam reports a blind study by Josh Talks: 20,000+ votes from 500+ annotators, 50–70 per language. In it, Bulbul v3 was most preferred at 8 kHz telephony. For full-band audio, MIT Sloan Management Review Middle East reports that "the company acknowledged that ElevenLabs' v3 alpha led in overall audio quality". This conflicts with Sarvam's current TTS page, which now says Bulbul V3 "was the most-preferred model in both full-band (48 kHz) and telephony (8 kHz) categories". Sarvam also reports the lowest word-skip and mispronunciation rates.
  - *Caveat:* vendor-published, and Eleven v4 was not in the comparison.
  - **For your browser (full-band WebRTC) use case, the gap is narrower than the telephony headline suggests.**
  - Price: ₹30 per 10K characters (docs).\[24\]
- **Other "benchmarks"** from caller.digital, autointerviewai and growwstacks (e.g., Hindi MOS 4.5 vs 4.2) are SEO or competitor content with unclear methodology.\[25\]\[26\]\[27\] Ignore them for decisions.
- **AI4Bharat Indic Parler-TTS / IndicF5:** open-source and self-hostable, but less production-ready for low-latency streaming. Good for research or fallback.
- **Cartesia Sonic-3, Deepgram Aura, Rime, Hume, Google Chirp 3 HD, Azure neural, Smallest.ai:** I found no independent Hindi/Marathi naturalness evidence. Cartesia Sonic-3 was rated below Bulbul v3 in Sarvam's study.\[28\]
- **Recommendation:** run your own blind test. Take 40 real interview utterances (Hindi, Marathi and Hinglish, including numbers and names), synthesize them on ElevenLabs v4 Turbo with 2–3 candidate voices and on Bulbul, and have 10–15 native listeners, ideally from your candidate demographic, rate them on a phone speaker. Weigh Marathi heavily; it is where global models are weakest.

---

## Problem 3 — Live-call conversation handling

### Failure → cause → fix

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent talks twice / double reply | More than one code path calls `generate_reply`/`say` (Director, timeout handler, tool result); preemptive generation plus a late transcript; tool call followed by an automatic reply | **Single speech arbiter**: only InterviewFlow schedules speech, and it checks `agent_state` and any active `SpeechHandle` first. Make tools return data, not speech. Set `min_consecutive_speech_delay` (e.g., 0.3–0.5 s). Log every speech_created with its source. |
| Agent replies mid-answer | Endpointing too eager; VAD-only on pauses; Hindi/Marathi pause patterns | Use the audio turn detector (`inference.TurnDetector()`). Raise `max_delay` for open questions and use dynamic endpointing (below). |
| Agent stops for background noise | VAD-mode interruption; TV or traffic noise | `interruption.mode="adaptive"`, `min_duration` 0.5–0.8 s, `min_words` 1–2 (needs STT), Krisp BVC voice isolation, `resume_false_interruption=True` |
| Candidate's "haan/hmm" stops the agent | Backchannels treated as barge-in | Adaptive interruption is built for exactly this. Krisp Interrupt Prediction v1 is an alternative (Pipecat integration). |
| Agent answers someone in the room / TV | Secondary voices reach STT | Krisp BVC removes secondary voices. Add an LLM rule: if the utterance isn't addressed to the agent or is off-context, call `side_talk()` → stay silent, or after 2 occurrences say a gentle "Main aapka intezaar kar rahi hoon, aap tayyar hon toh batayein." OpenAI's guidance lists "silence, background noise, hold music, TV audio, or side conversation" as cases needing explicit handling.\[11\] |
| Long thinking pauses get cut off | `max_delay` too short | Per-question endpointing (below), plus a gentle prompt after about 6–8 s of silence ("Aaram se sochiye…"), driven by InterviewFlow, not the LLM. |

### LiveKit configuration (starting point)

LiveKit's own recommended starting configuration for noisy environments is: audio turn detector, fixed endpointing `min_delay 0.5 / max_delay 3.0`, adaptive interruption with `min_duration 0.5`, `min_words 0`, preemptive generation on and preemptive TTS off. Documented defaults include `false_interruption_timeout = 2.0 s`, `resume_false_interruption = True`, `preemptive_generation.max_speech_duration = 10 s` and `max_retries = 3`.\[29\] With the audio turn detector, LiveKit's endpointing defaults are 0.3/2.5 s.\[30\] Adapted for your interview:

```python
session = AgentSession(
    turn_handling=TurnHandlingOptions(
        turn_detection=inference.TurnDetector(),        # v1 on LiveKit Cloud (free there); falls back to v1-mini
        endpointing={"mode": "dynamic", "min_delay": 0.6, "max_delay": 3.5},
        interruption={
            "mode": "adaptive",
            "min_duration": 0.6,
            "min_words": 1,
            "false_interruption_timeout": 1.5,
            "resume_false_interruption": True,
        },
        preemptive_generation={"enabled": True, "preemptive_tts": False, "max_speech_duration": 6.0},
    ),
    min_consecutive_speech_delay=0.4,
    # stt=Scribe v2 Realtime with keyterms; tts=eleven_v4_turbo; llm=realizer
)
# room input: Krisp BVC (browser/WebRTC) voice isolation
```

**Per-question endpointing at runtime** (LiveKit supports updating endpointing mid-session):\[31\]
- Yes/no and short factual questions (age, district, phone number): `min_delay 0.4, max_delay 2.0`.
- Open questions ("Tell me about your last caregiving job"): `min_delay 0.8, max_delay 4.5–5.0`.
- Number capture (phone, Aadhaar-last-4, experience in years): long `max_delay` with digit-by-digit read-back confirmation.

**Make interruptions selectively non-interruptible.** Pass `allow_interruptions=False` for the consent statement and the critical sentence of each question (keep it short).\[32\] Allow interruptions everywhere else.

**Pin framework versions.** LiveKit GitHub issues show false-interruption behavior changing between releases (issue #4039: resume broken after upgrading 1.2.18 → 1.3.3; issue #7837: reply held while caller noise plays, a change from 1.6.6).\[33\]\[34\] Upgrade only behind your regression suite.

**Note on turn detection in STT mode:** if you ever use `turn_detection="stt"` (Scribe's endpointing), set `endpointing.min_delay=0`. Otherwise LiveKit's delay is added on top of the provider's.\[29\]\[35\]

### Turn-detection model options

- **LiveKit audio turn detector v1:** encodes audio directly (semantics plus prosody); free on LiveKit Cloud; Hindi is listed among supported languages with high-90s accuracy in LiveKit's own benchmark (vendor-reported).\[30\] Default choice for you.
- **Pipecat Smart Turn v3/v3.2:** open weights, data and training code; Whisper-Tiny base. Daily reports 12.6 ms CPU inference on an AWS c7a.2xlarge but 94.8 ms on an AWS t3.medium. Accuracy is 93.44% on Hindi and 87.60% on Marathi (Daily). v3.2 covers Hindi, Marathi and Bengali, but the data is about 82% synthetic TTS.
- **indic-smart-turn (adimyth):** a community fine-tune that loads in Pipecat's `LocalSmartTurnAnalyzerV3`. It was trained on 51,917 IndicVoices clips (AI4Bharat) of "real two-person phone conversations… not synthetic TTS", oversampled twice. Promising for Marathi, but unvetted. Benchmark it on your own calls before trusting it.
- **Krisp VIVA 2.0:** Turn Prediction v3 (multilingual, audio-only) and Interrupt Prediction v1 (backchannel vs. real barge-in). Integrated in Pipecat; proprietary. An older Daily comparison noted Krisp's earlier turn model was English-only, so verify Hindi/Marathi performance.\[36\]\[37\]\[38\]
- **Research context:** Voice Activity Projection (Ekstedt & Skantze) and TurnGPT underpin most of these. "Talking Turns" (arXiv 2503.01174) found audio foundation models misjudge timing, interrupt aggressively and rarely backchannel. Full-Duplex-Bench and TurnBench now measure this.\[39\] **Conclusion: full-duplex speech-to-speech models are not yet a safe choice for a scripted, policy-constrained Indic interview.** They also break your control architecture: Pipecat Flows explicitly doesn't support speech-to-speech models.\[3\]

### Backchanneling while listening ("mm-hmm")

I recommend **not** emitting live backchannels while the candidate is speaking in v1. On mobile browsers, agent audio can leak through echo cancellation into STT and VAD, create self-interruptions, and get transcribed as candidate speech. Instead, (a) start each reply with a varied acknowledgment token, and (b) after a long pause mid-answer (e.g., 2.5–3 s, while the turn detector says "not done"), play a short pre-rendered "hmm" or "achha", marked non-interruptible and excluded from STT. This is an engineering judgment, not a published benchmark. Test it with users.

---

## Secondary topics

### ASR and code-mixed input in the conversation layer

- **Scribe v2 Realtime:** ElevenLabs puts Hindi and Marathi in its "High Accuracy (>5% to ≤10% WER)" tier (vendor).\[40\] Coval's independent daily benchmark measures about 123 ms time-to-final-segment and 4.4% WER on its mixed public test set (not Indic-specific).\[41\] A third-party profile reports an April 2026 upgrade adding Indic-English code-switching and raising the keyterm limit from 100 to 1,000.\[42\]
- **Keyterm prompting** ($0.08/hour extra):\[43\] load role vocabulary (GNM, ANM, B.Sc Nursing, ICU, caregiver, patient transfer, bedsore, district and city names, hospital names) per interview.
- **Treat ASR output as uncertain.** In each state, have the realizer or a classifier return `answer_extracted` plus `confidence`. Below threshold, or when the value is critical (phone, age, years of experience, qualification), use a CONFIRM_VALUE directive: "Maine suna 'teen saal' — sahi hai?" Re-ask at most twice, then switch strategy (offer options: "Ek saal se kam, ek se teen saal, ya teen saal se zyada?"), then move on and flag for HR.
- **Language policy:** reply in the candidate's dominant language for the turn. Keep Hindi in Devanagari for TTS. Write English loanwords as candidates say them. Never switch language because of one ASR-misdetected word; require 2 consecutive turns.

### Prompting patterns for the voice realizer

- 1–2 sentences, at most ~25 words, one question per turn, no markdown, lists or emojis.
- Write numbers, dates and phone numbers as spoken words. ElevenLabs Agents offers a dedicated normalizer, which it calls "more reliable than LLM-based normalization."\[44\] Read phone numbers back digit by digit in groups.
- Add an explicit variety rule plus 3–5 sample phrases per moment (OpenAI guidance), together with a deterministic "last 5 acknowledgments" list passed in as "do not reuse."\[45\]
- Unclear audio: "If unintelligible, ask briefly to repeat; never guess; never repeat the same clarification twice" (OpenAI found "unintelligible" worked better than "inaudible").\[11\]
- A dedicated `# Guardrails` section (ElevenLabs guidance), listing forbidden topics and the deflection behavior.\[44\]

### Reference architectures and repos

- **livekit-examples/interview-agent-demo:** a screening agent (single prompt, post-call LLM evaluation to JSON). Useful as a baseline, but it is intentionally *not* structured; don't copy its control model.\[46\]
- **LiveKit Agents docs: Tasks and TaskGroups** (includes an interview-style `BehavioralTask`/`IntroTask`/`CommuteTask` example), Workflows, the Supervisor pattern and Turn-taking tuning.\[47\]
- **pipecat-ai/pipecat `examples/flows`:** `patient_intake.py`, `insurance_quote.py` and `podcast_interview.py` are the closest templates for a node-based interview.\[48\]
- **Rasa CALM docs:** the clearest written design for "LLM understands, flows decide."\[49\]
- **pipecat-ai/smart-turn, adimyth/indic-smart-turn:** turn detection.

### Evaluation and regression testing

Build your own harness first; buy a platform second.

1. **Golden audio set:** 200–300 real (consented) candidate utterances across Hindi, Marathi and Hinglish, with phone-mic noise (traffic, TV, children, kitchen) and human transcripts. Track WER/CER per language and per noise type on every STT or config change.
2. **Simulated interviews:** an LLM "candidate" with personas (hesitant, talkative, asks about salary, says no to night shifts, off-topic, talks to family mid-answer), voiced by TTS with noise overlays and fed through the real pipeline. Coval and Hamming sell this.\[50\]\[51\] An independent study ("Testing the Testers", arXiv 2511.04133) found these platforms' simulation and judging quality is uneven; contextqa reports Coval scored 62.7% evaluation accuracy in that benchmark.\[52\] Validate any LLM-judge against human labels.
3. **Deterministic checks (cheap, 100% coverage):** blueprint coverage (every required question asked once, in order); no forbidden content (reuse your output-guard rules offline); at most N follow-ups per question; zero double-speak events (two agent speech_created without a user turn in between); re-ask count.
4. **Latency:** user-end-of-speech → first agent audio, p50/p95 per turn. Targets: p50 under 1.0 s, p95 under 1.6 s for browser calls. Hamming's vendor guidance cites P95 under 800 ms, which is aggressive for a GPT-4o cascade from India.\[51\]
5. **Interruption metrics:** false-barge-in rate (agent stopped, no real user turn followed; use `agent_false_interruption` events), missed-barge-in rate, mid-answer cut-off rate (labelled from samples).\[53\]
6. **Weekly human review** of 20 random calls by a native Hindi/Marathi reviewer for naturalness (MOS-style 1–5) and policy compliance.

Hamming claims "40% of regressions come from upstream provider changes" (vendor claim).\[51\] Whatever the true figure, pin model versions (TTS, STT, LLM snapshot) and re-run the suite whenever a provider ships a change.

### Known limitations a first-time builder should expect

- Vendor latency and quality numbers (ElevenLabs, Sarvam, PolyAI, LiveKit, Krisp) are mostly self-reported; Indic-specific independent benchmarks are rare.
- Turn-detection training data for Marathi is largely synthetic.\[54\] Expect worse endpointing in Marathi than in Hindi or English.
- Audio tags can be spoken aloud or ignored, and they behave differently across voices.\[16\]\[55\] Tag-heavy output is a reliability risk in real time.
- Mobile browser audio: echo-cancellation quality, Bluetooth headsets, auto-gain and background-tab throttling vary a lot by Android device. Test on cheap Android phones.
- LLMs will still occasionally paraphrase a question into a different meaning. Only an output check against the canonical question catches this.
- Framework behavior around interruptions changes between minor versions.

### Cost and scaling (~100 interviews/day × 12 min, ≤10 concurrent)

Volume: about 1,200 call-minutes/day ≈ 36,000 min/month ≈ 600 hours/month (30 days). List prices checked Oct 19, 2026:

| Component | Unit price (official) | Assumption | Est. monthly |
|---|---|---|---|
| Scribe v2 Realtime STT | $0.39/hour, + $0.08/hour keyterms\[43\] | 600 h | ~$282 |
| ElevenLabs eleven_v4_turbo TTS | $0.04 per 1K chars\[43\] | ~6,000 chars per interview incl. cancelled/preemptive (~6 min agent speech) × 3,000 interviews = 18M chars | ~$720 |
| LiveKit Cloud agent session | $0.01/min after included minutes; Ship plan from $50/mo with 20 concurrent sessions\[56\] | 36,000 min (5,000 included) | ~$360 |
| Turn detector v1 | Free for agents deployed on LiveKit Cloud\[57\] | — | $0 |
| LLM (realizer + Director) | Depends on model | **Estimate only**: tens of thousands of input tokens per turn-set; can be the largest line if the Director runs a large model on every turn | Roughly $500–2,000+ |
| **Alt: Sarvam Bulbul v3 TTS** | ₹30 per 10K chars\[24\] | 18M chars | ~₹54,000 |
| **Alt: Sarvam STT** | ₹30/hour (docs); ₹0.41–0.49/min on tiered plans\[24\]\[58\] | 600 h | ~₹18,000 |

**Interpretation:** infrastructure comes to about $1,350/month (~$0.45 per interview) before the LLM. Your cost levers are (1) a smaller realizer model, (2) running the Director every N turns or only at question boundaries rather than every turn, (3) prompt caching of the static system prompt, and (4) pre-rendered audio for fixed lines. Ten concurrent sessions fit inside LiveKit's Ship tier (20 concurrent).\[56\] Note that ElevenLabs' own pages show inconsistent Turbo/Flash prices ($0.04 vs $0.05 per 1K); budget for the higher one.\[43\]\[59\]

---

## Recommendations (prioritized)

1. **This week:** introduce a single speech arbiter, remove every speech-triggering path except InterviewFlow, and log the source of every speech event. This should eliminate most double replies.
2. **Weeks 1–2:** convert the voice LLM to a directive-in, structured-JSON-out realizer with node-scoped tools. Add the streaming output guard and template-based deflection, salary and outcome lines. Make the Director async and advisory.
3. **Weeks 1–2:** apply the LiveKit config above with per-question endpointing and Krisp BVC; pin versions.
4. **Weeks 2–4:** build the golden audio set and simulated-candidate suite; gate every change on blueprint coverage, guard violations, double-speak count, p95 latency and per-language WER.
5. **Weeks 3–5:** run a blind native-listener test: ElevenLabs v4 Turbo (library voice vs. consented IVC of a Hindi/Marathi recruiter) vs. Sarvam Bulbul. Pick per language if needed; LiveKit lets you switch TTS per session.
6. **Ongoing:** move naturalness into deterministic post-processing (acknowledgment rotation, sparse fillers, `[pause]` before sensitive questions); pre-render fixed lines with eleven_v4.
7. **Later, only if needed:** evaluate indic-smart-turn or Krisp Turn/Interrupt Prediction against LiveKit's detector on your Marathi calls. Revisit full-duplex models in 12+ months.

## Caveats

- Several key figures are vendor-reported and not independently verified: ElevenLabs v4 Turbo latency, Sarvam's Josh Talks preference study, LiveKit turn-detector accuracy, PolyAI's "no hallucination" claims, Krisp and Hamming metrics. Coval's Scribe benchmark is independent but not Indic-specific.
- Eleven v4 launched three weeks ago; best practices for its tags in Hindi/Marathi are not yet documented beyond the v3-era guidance.
- LLM cost is an estimate; measure real token usage from a week of calls.
- Voice cloning, call recording and candidate data processing in India require explicit consent and should get legal review under the DPDP Act 2023. I did not research the final DPDP Rules in detail.
- The persuasion and re-ask pattern should be reviewed by HR/compliance so reassurances are factually true for every employer and role.

## Sources

1. [Process Calling: Agentic Tools Need State](https://rasa.com/blog/process-calling-agentic-tools-need-state)
2. [Rasa CALM](https://rasa.com/calm)
3. [Introduction to Pipecat Flows - Pipecat](https://docs.pipecat.ai/guides/features/pipecat-flows)
4. [Defense in depth in the age of agents](https://sierra.ai/uk/blog/defense-in-depth-in-the-age-of-agents)
5. [Raven 3.5 Beats GPT-5 for Customer Service](https://poly.ai/blog/PolyAI-Raven-35-beats-GPT5)
6. [Raven - PolyAI Platform](https://docs.poly.ai/behavior/models/raven)
7. [CALM Compliance Starter Pack - whitepaper - Rasa](https://info.rasa.com/hubfs/PDF_Content/CALM_Compliance_Starter_Pack_whitepaper_202401.pdf?hsLang=en)
8. [The Guide to AI Agents](https://sierra.ai/blog/ai-agents-guide)
9. [Supervisor pattern](https://docs.livekit.io/agents/logic/supervisor-pattern/)
10. [Seven tips for prompting voice agents with the Realtime API](https://cdn.openai.com/API/docs/realtime-prompting-guide.pdf)
11. [Prompting Realtime models](https://developers.openai.com/api/docs/guides/voice-prompting)
12. [Enhancing Naturalness in LLM-Generated Utterances through Disfluency Insertion](https://www.alphaxiv.org/abs/2412.12710)
13. [Evaluating Sampling-based Filler Insertion with ...](https://aclanthology.org/2022.lrec-1.210.pdf)
14. [Fillers in Spoken Language Understanding: Computational and Psycholinguistic Perspectives](https://arxiv.org/html/2301.10761v1)
15. [Best practices](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)
16. [Audio Tags 101: Directing emotional TTS in Eleven v3](https://elevenlabs.io/blog/v3-audiotags)
17. [ElevenLabs v3 Audio Tags User Guide: Mastering Emotional Voice Control - Do that with AI! AI Coaching & Mentorship to Help You Leverage AI](https://jonathanmast.com/elevenlabs-v3-audio-tags-user-guide-mastering-emotional-voice-control/)
18. [ElevenLabs V3 Tutorial: Best Settings, Audio Tags & Free GPT Tool](https://moelueker.com/blog/elevenlabs-v3-tutorial-best-settings-audio-tags-free-gpt-tool)
19. [Eleven v4 and Eleven v4 Turbo Text to Speech models](https://elevenlabs.io/v4)
20. [Text to Speech (product guide)](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech)
21. [Voices](https://elevenlabs.io/docs/overview/capabilities/voices)
22. [Text to Speech & AI Voice Generator for Indian Languages](https://www.sarvam.ai/text-to-speech)
23. [Sarvam AI Ships Bulbul V4 to Bring Emotional Voice to 11 Indian Languages](https://alphasignal.ai/news/sarvam-ai-ships-bulbul-v4-to-bring-emotional-voice-to-11-indian-languages)
24. [Sarvam AI Pricing - Transparent Rates for Indian Language AI APIs](https://docs.sarvam.ai/api-reference-docs/pricing)
25. [How Sarvam AI's Saaras V3 & Bulbul V3 Solve Real-World Voice AI Challenges](https://growwstacks.com/blog/sarvam-ai-saaras-v3-bulbul-v3-voice-ai)
26. [Indic TTS Benchmark 2026 — Bulbul vs ElevenLabs vs Google vs AI4Bharat](https://caller.digital/blog/indic-tts-benchmark-bulbul-elevenlabs-sarvam-google-ai4bharat-2026)
27. [Sarvam AI Review: Bulbul TTS, Saaras ASR, Shuka v1 Architecture, and Indic Voice Benchmarks in 2026](https://www.autointerviewai.com/blog/sarvam-ai-bulbul-saaras-indic-voice-models-review-2026)
28. [Bulbul V3: natural, expressive TTS](https://www.sarvam.ai/blogs/bulbul-v3)
29. [Turn-taking tuning | LiveKit Documentation](https://docs.livekit.io/agents/logic/turns/tuning/)
30. [LiveKit turn detector](https://docs.livekit.io/agents/logic/turns/turn-detector/)
31. [Turn handling options](https://docs.livekit.io/reference/agents/turn-handling-options/)
32. [Turns overview](https://docs.livekit.io/agents/logic/turns/)
33. [Resume false interruption behavior broken · Issue #4039 · livekit/agents · GitHub](https://github.com/livekit/agents/issues/4039)
34. [Option to start a reply on time when caller noise began while the agent was thinking (1.6.6 behavior) · Issue #7837 · livekit/agents · GitHub](https://github.com/livekit/agents/issues/7837)
35. [Configuring turn detection and interruptions in LiveKit Agents](https://livekit.com/blog/turn-detection-and-interruption-handling)
36. [Krisp VIVA - Pipecat](https://docs.pipecat.ai/pipecat/features/krisp-viva)
37. [Krisp Launches VIVA 2.0 Voice Infrastructure for AI Agents](https://techintelpro.com/news/ai/agentic-ai/krisp-launches-viva-20-voice-infrastructure-for-ai-agents)
38. [Announcing Smart Turn v3, with CPU inference in just 12ms](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/)
39. [TASTE2: Text-Aligned Speech Modeling and Deployment toward Full-Duplex Voice Interaction](https://arxiv.org/pdf/2609.08956)
40. [Speech to Text — Most Accurate Speech to Text Model](https://elevenlabs.io/speech-to-text)
41. [ElevenLabs Scribe v2 Realtime STT latency and accuracy benchmark](https://benchmarks.coval.ai/models/scribe_v2_realtime)
42. [ElevenLabs Scribe v2: model profile · Signal](https://opentranscription.io/blog/elevenlabs-scribe-v2-profile.html)
43. <https://elevenlabs.io/pricing/api>
44. [Prompting guide](https://elevenlabs.io/docs/eleven-agents/best-practices/prompting-guide)
45. [Realtime Prompting Guide for GPT Models](https://www.scribd.com/document/931653232/Voice-AI-Agents-Prompting-Guide)
46. [GitHub - livekit-examples/interview-agent-demo: Interview Agent Example · GitHub](https://github.com/livekit-examples/interview-agent-demo)
47. [Tasks and task groups](https://docs.livekit.io/agents/logic/tasks/)
48. [pipecat/examples/flows at main · pipecat-ai/pipecat · GitHub](https://github.com/pipecat-ai/pipecat/tree/main/examples/flows)
49. [Conversational AI with Language Models - Rasa Documentation](https://rasa.com/docs/learn/concepts/calm/)
50. [Voice AI Simulation in 2026: Future AGI vs Cekura, Hamming, Bluejay, Coval](https://futureagi.com/blog/voice-ai-simulation-cekura-hamming-bluejay-coval-2025/)
51. [Testing Voice Agents: Load, Regression, and A/B Evaluation for Production Reliability](https://hamming.ai/resources/testing-voice-agents-production-reliability)
52. [Top AI Voice Agent Testing Tools Compared (2026)](https://contextqa.com/blog/ai-voice-agent-testing-tools/)
53. [Events and error handling](https://docs.livekit.io/reference/agents/events/)
54. [GitHub - adimyth/indic-smart-turn: Pipecat Smart Turn v3 fine-tune for English + 11 Indian languages · GitHub](https://github.com/adimyth/indic-smart-turn)
55. [ElevenLabs Eleven v3 Model Guide 2026: Audio Tags, 70 Languages & What Changed](https://elevenlabsmagazine.com/elevenlabs-eleven-v3-model-complete-guide-2026/)
56. [LiveKit Pricing](https://livekit.com/pricing)
57. [Solving end-of-turn detection: LiveKit Turn Detector v1.0](https://livekit.com/blog/solving-end-of-turn-detection)
58. [Sarvam API Pricing | TTS, STT, LLM & More](https://www.sarvam.ai/api-pricing)
59. [ElevenAPI for Developers](https://join.elevenlabs.io/api/developer-api)
