# Crowd / overlap recovery (Phase 2 follow-up)

**Date:** 2 November 2026  
**Demo:** `/elevenlabs-interviewer`  
**Status:** Implemented locally (not claimed as true speaker diarization)

## Problem

When more than one person spoke, or the room was noisy, Scribe still produced tokens. Flow treated that as an unusable turn and **replayed `last_question` every time** (`ask_repeat`). Watchdog could add a second “please repeat.” The call felt stuck.

Krisp BVC is unchanged: it isolates a voice; it does **not** count people.

## What we shipped

After **three unusable turns** on the **same focus**, the agent speaks **one** room-too-busy line, then **waits**. It does **not** restate the screening question on that line.

Example copy:

| Language | Line |
| --- | --- |
| Hindi | मुझे एक से ज़्यादा आवाज़ें आ रही हैं। कृपया केवल उम्मीदवार ही बोलें। |
| English | I can hear more than one voice. Please have only the candidate speak. |

Other Indic join languages have a matching one-liner in `CROWD_HELP_LINES`.

This is **policy**, not people-counting. Overlap, TV, and garbled one-speaker STT all look the same to Flow.

## Behaviour

| Turn on this question | Spoken move |
| --- | --- |
| 1st unclear / overlap | `ask_repeat` (invite / could-not-hear, still may include the last question) |
| 2nd | `ask_repeat` |
| 3rd | `crowd_help` — verbatim crowd line only. **Forbidden:** last question |
| Next ~10 s (`CROWD_COOLDOWN_S`) | No extra TTS: watchdog skip, silence nudge skip, further `ask_repeat` / `crowd_help` dropped |
| 4th still unusable | Soft-skip the stuck field and continue (existing `MAX_FOCUS_RETRIES`) |
| Clear candidate answer | Captured as usual; cooldown ends on a non-recovery move |

Empty / non-word noise is still ignored (`is_candidate_speech`) and does not increment this ladder.

## Files

| File | Change |
| --- | --- |
| `agent/interview/flow.py` | `crowd_help` / `crowd_hold`, `CROWD_HELP_LINES`, `RECOVERY_SPEECH_KINDS`, `CROWD_COOLDOWN_S`. Third unclear → crowd line, not `noise_help` + re-ask |
| `agent/interview/turns.py` | Watchdog `recovery_blocked` callback; skip extra repeat |
| `agent/main.py` | Cooldown after `crowd_help`; drop recovery TTS during cooldown; silence skip; skip fillers while blocked |
| `agent/interview/voice_tone.py` | Tones for `crowd_help`, `crowd_hold`, `noise_help` |
| `agent/tests/test_flow.py` | 3× unclear → crowd line, no question replay; 4th → soft-skip |
| `agent/tests/test_turns.py` | Watchdog silent when recovery already spoken |

## How to check

1. Restart the agent (`python main.py dev` from `agent/.venv`).
2. Join `http://localhost:5173/elevenlabs-interviewer`.
3. On one screening question, have two people talk (or noisy overlap) three times.
4. Expect **one** crowd line, then quiet — not the same city/phone question on a loop.
5. One clear speaker should continue the same question (or the next field after a soft-skip).

Logs to look for: `move=crowd_help`, event `audio.crowd_help`, `crowd cooldown 10s`, `watchdog skip repeat`, `crowd cooldown skip move=`.

## Out of scope

- Real multi-speaker diarization (pyannote, Krisp “N speakers”)
- Changing Krisp BVC / turning browser `noiseSuppression` on
- `/gpt-live-interviewer` as the scored demo (same Flow kinds apply if that worker runs this code)
