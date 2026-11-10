# One cascade call — sample cost

`/elevenlabs-interviewer` only. List prices checked 10 November 2026. This is a planning sample, not a metered bill. A real call should be repriced from `turn.latency` plus provider usage.

Not covered here: GPT-Live, Sarvam, avatar. Monthly capacity and who pays overage: `docs/production-ops.md`.

## Sample call

15 minutes connected. 25 candidate turns. About 6,000 characters sent to TTS (agent speech only; cached fillers are not in that count). Scribe receives the 15 minutes of candidate audio, with plan keyterms. The analyst is `gpt-4o` on every turn. The spoken wording is `gpt-4o-mini`. Prompt caching is off, so each turn pays full input price.

| Piece | Model | Meter | Sample usage | USD |
| --- | --- | --- | --- | --- |
| Speech to text | `scribe_v2_realtime` | $0.39 / hour | 15 min | 0.10 |
| Keyterms | same | +$0.08 / hour | 15 min | 0.02 |
| Analyst (screening and clinical) | `gpt-4o` | $2.50 / 1M in, $10 / 1M out | 75k in, 9k out | 0.28 |
| Spoken wording | `gpt-4o-mini` | $0.15 / 1M in, $0.60 / 1M out | 100k in, 2k out | 0.02 |
| Speech | `eleven_v4_turbo` | $0.04 / 1,000 characters | 6,000 characters | 0.24 |
| Agent session | LiveKit Cloud | $0.01 / min after included minutes | 15 min | 0.15 |
| Near-field isolation | Krisp BVC via LiveKit | $0.0012 / min after included minutes | 15 min | 0.02 |
| Turn detector | LiveKit, on Cloud | included | — | 0 |
| **Spoken call** | | | | **0.83** |

A heavier analyst prompt (larger schema, longer recent turns) can move the `gpt-4o` line toward about $0.50 and the call toward about $1.10. The $1–$6 band in `docs/production-ops.md` is that uncertainty plus longer calls, not a second product.

LiveKit and Krisp show the overage rate. Calls inside the plan’s included minutes bill $0 for those two rows. The monthly plan fee is separate (Build $0, Ship from $50).

Prices: [ElevenLabs API](https://elevenlabs.io/pricing/api), [OpenAI](https://developers.openai.com/api/docs/pricing), [LiveKit](https://livekit.com/pricing). Tax excluded.

## Same candidate, not the spoken minute

| Piece | Model | When | Sample |
| --- | --- | --- | --- |
| Resume questions | `gpt-4o` (`CHAT_MODEL`) | once, before join | a few cents |
| Scorecard classify | `gpt-4o` (`CLASSIFIER_MODEL` or `CHAT_MODEL`) | once, after the call | a few cents |

## Server ops (pointer only)

One always-on web service and a database. That is a monthly host bill, typically tens of dollars, and it does not change the $0.83 sample. Reprice from the host you actually run. At a busy day of interviews it stays small next to model spend.
