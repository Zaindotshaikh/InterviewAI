# Voice lock and height read-back

**Date:** 3 November 2026  
**Demo:** `/elevenlabs-interviewer`  
**Not in this change:** item 2 (`ELEVENLABS_VOICE_BY_LANG` left as-is)

## Problems

1. Mid-call the interviewer could **sound like a different person** (gender/accent). Language switch retuned ElevenLabs `voice_id`, and Hinglish / English job words could trigger `switch_language`.
2. Height is stored as **cm** (correct for the form) but was often **spoken** as centimetres even when the candidate said feet (e.g. “5 feet 11” → “173 centimeters”).

## What we shipped

| Item | Change |
| --- | --- |
| **1** | Pin the join ElevenLabs `voice_id`. Language updates must not pick a new library voice. |
| **3** | On the ElevenLabs demo, `switch_language` only if the candidate **clearly asked** to change language. “GNM / ICU” is not a switch. |
| **4** | ElevenLabs failure still **does not** fall back to Google/OpenAI TTS on this route. |
| **5** | Store cm. **Speak** feet/inches unless they clearly said cm. |
| **6** | Parse messy feet: `5 11`, `5.11`, `पाँच फीट ग्यारह`, etc. |
| **7** | Body confirm is a **fixed sentence**. If TTS would say centimetres after a feet answer, the output guard replaces it with the feet line. |

## Behaviour

**Voice**

- Join Hindi → same speaker through Hinglish answers.
- Explicit “please speak English” / “हिंदी में बोलिए” may change **language** (STT / EL locale) but **keeps** the same `voice_id`.
- Log: `language switch refused (EL lock)` on accidental tool calls; `ElevenLabs TTS voice pinned=` on a real switch.

**Height**

- Slot `height_cm` stays centimetres for the profile.
- Confirm uses `body_confirm_line` + `spoken_height_phrase`.
- They said cm → read-back in centimetres. Otherwise Indian screening read-back is feet.

## Files

| File | Role |
| --- | --- |
| `agent/providers/elevenlabs_voices.py` | `pinned_elevenlabs_voice_id` |
| `agent/interview/language.py` | `explicit_language_switch_request` |
| `agent/main.py` | TTS pin, EL-lock switch gate, no Chirp fallback, pre-TTS cm guard |
| `agent/interview/normalize.py` | Feet parse, `spoken_height_phrase`, `height_said_in_cm` |
| `agent/interview/flow.py` | Body confirm verbatim; no unit conversion in the spoken line |
| `agent/interview/output_guard.py` | `forbid_centimetres` |
| `agent/tests/test_language.py` | Pin + switch-request tests |
| `agent/tests/test_normalize_blueprint.py` | Height parse / phrase |
| `agent/tests/test_output_guard.py` | cm spoken blocked |
| `agent/tests/test_flow.py` | Feet in confirm verbatim |

## How to check

1. Restart the agent (`python main.py dev` from `agent/.venv`).
2. Join `http://localhost:5173/elevenlabs-interviewer` in Hindi.
3. Mix English job words — **voice must not change**.
4. Say height as **5 feet 11** (or “five eleven”) and weight — confirm must be **feet**, not 180 cm.
5. Optional: say **160 cm** — confirm may use centimetres.

## Out of scope

- Emptying or rewriting `ELEVENLABS_VOICE_BY_LANG` (item 2)
- New ElevenLabs personas
- Changing how height is **stored** (still cm)
