# Client expectations vs current v2 coverage

Short status against the client note (screening fields, adaptive clinical, languages, avatar, noise, tiers, recovery).

## Initial screening fields


| Client ask                                 | Status  | Notes                          |
| ------------------------------------------ | ------- | ------------------------------ |
| City applying for                          | Covered | Screening slot                 |
| Phone number                               | Covered | With confirmation read-back    |
| Qualification + year                       | Covered |                                |
| Height + weight                            | Covered |                                |
| Nursing experience / exposure              | Covered | Years + settings; fresher path |
| Comfort with essential care (incl. diaper) | Covered | Gate item                      |


## Core behaviour they called out


| Client ask                                                    | Status                                    | Notes                                                                                           |
| ------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Not a fixed questionnaire                                     | Covered                                   | Flow + LLM wording; director steers next move                                                   |
| Diaper refuse → explain / persuade → if still no, no clinical | Covered                                   | 2 persuasions then `gate_failed` / screened out; clear “yes after hesitate” recovery added      |
| Clinical round adapts (probe / clarify / challenge / depth)   | Partial - Needs SME knowledge to complete | Rubric + follow-ups by answer quality; still area-scaffolded, not a free-form human interviewer |
                



## Next-call exploration items


| Client ask                                                    | Status      | Notes                                                                                                                                       |
| ------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Visible face / avatar                                         | Not Covered | Tavus on `/avatar-interviewer`; voice-only default on `/v2/test`                                                                            |
| Multiple Indian languages (EN, HI, TE, TA, KN, ML, BN, MR, …) | Covered     | Profiles wired for those (+ GU/PA/OD); quality varies by STT/TTS; default TTS is Chirp, ElevenLabs A/B on `/elevenlabs-interviewer`         |
| Multi-language / code-mix (Hinglish, Tanglish)                | Covered     | Prompted + STT language list; mid-call language switch exists; not exhaustively tuned per dialect                                           |
| Regional accents, slang, imperfect pronunciation              | Covered     | Handled as “judge meaning not fluency”; real-world accuracy still STT-dependent (OpenAI live STT default; Sarvam available but not primary) |
| High background noise + ask to repeat if unclear              | Covered     | Krisp NC + unclear/noise/repeat intents; not stress-tested as “ward-level noise” product claim                                              |
| Dynamic clinical follow-ups on incomplete / wrong / partial   | Covered     | Quality grades drive clarify / deepen / move on                                                                                             |
| Conversation context / contradictions                         | Covered     | Analyst flags contradictions; flow can probe                                                                                                |
| Nervous / long pauses / IDK / interrupt / repeat-rephrase     | Covered     | Warm handling, silence nudges, IDK move-on (except diaper gate), interruption + rephrase intents                                            |
| Clinical knowledge assessment                                 | Covered     | Blueprint areas + key points + scorecard                                                                                                    |
| Candidate classification into tiers + reasoning/evidence      | Covered     | `tier_1`–`tier_3`, `not_eligible`, `needs_review` with reasoning                                                                            |
| Audio/network interruption recovery without losing context    | Covered     | Reconnect grace + persisted flow state / recent transcript                                                                                  |




## TTS A/B (internal, for quality)

- **Chirp** (`/v2/test`) and **ElevenLabs v4 turbo** (`/elevenlabs-interviewer`) both work.
- Native Indic library voices (e.g. Sujata) need a **paid ElevenLabs** plan; free API uses premade voices (Sarah EN / Alice Indic).



