# Production ops and cost

Target: Apollo first-round nurse screening, about **100 completed interviews a day**, after a paid POC. The current free demo (Render free web + LiveKit Build) cannot carry that.

## What runs where

| Piece | Production home | Notes |
| --- | --- | --- |
| UI + API | One always-on web service (today: one Docker image on Render) | Frontend and API deploy together |
| Voice agent | LiveKit Cloud, region **ap-south** | Separate deploy (`lk agent deploy`). A git push does not update it |
| Session state | Postgres (or equivalent) | JSON files on the web box are wiped on redeploy |
| Models | OpenAI, ElevenLabs, LiveKit | Audio leaves India. Name these vendors in the DPA and the candidate notice |

One voice path for the POC and the first production cut. ElevenLabs cascade for southern languages. GPT-Live only if English/Hindi speed wins the shadow test. HR does not A/B two agents.

## Capacity

- Assume ~15 minutes per interview → **~1,500 agent-minutes/day**, **~33,000 minutes/month** at 22 working days.
- Size for the **peak**, not the average. A morning slot can mean **10–25 rooms at once**.
- When full, the candidate sees a wait state. A silent failure is an incident.
- Pin media and the agent in India. US-only media shows up as lag and bad turn-taking.
- Load-test ~20 parallel sessions before the first HR week: join, agent audio, scorecard.

## Cost (reprice from current rate cards before the contract)

Order of magnitude until one real week is metered.

| Item | Planning figure |
| --- | --- |
| Models per completed interview | **$1–$6**. Cascade (Scribe + director LLM + dialogue LLM + ElevenLabs) is the one you can cap. GPT-Live meters audio both ways for the whole call and sits at the top of the band |
| Models at 100/day | **~$2k–$13k / month** |
| ElevenLabs | Starter character cap dies in a handful of calls. Need Scale or Enterprise, a monthly ceiling, and an alert at 70% |
| LiveKit | Paid plan sized for 20–30 concurrent sessions and ~33k agent-minutes. Build (~1,000 min/month, 5 concurrent) is demo-only |
| Web + database | Small next to model spend. Must stay awake. Free tier sleeps and drops disk |

Agree **who pays API overage** and set a hard monthly ceiling before HR starts.

## Compliance (India, hiring)

- Apollo is the data fiduciary. You are the processor. Sign a DPA: purpose, retention, deletion, subprocessors, breach contact.
- Personal data in play: voice, phone, city, qualification, height, weight, employment history. Collect only fields HR can defend.
- Consent **before the mic opens**, in the candidate’s language: recording, AI scoring, named vendors, retention, and that a human decides.
- Cross-border processing (OpenAI, ElevenLabs, LiveKit) is the usual legal blocker. Get Apollo legal sign-off on those vendors.
- Do not ask for patient names or MRNs. Scrub them if a nurse volunteers a real case.
- Tiers are a recommendation. A person passes, fails, or re-interviews. No auto-reject. Log overrides. Plan a small check for accent, gender, and language skew.
- Nursing leadership signs the rubric and the care gate. HR does not own clinical pass/fail alone.
- A cloned voice needs that person’s written consent, an “this is an AI interviewer” line in every call, and a ban on using the clone outside this product.
- Contract line: screening aid, not a licence-to-practice judgement.

## Security

- Invite links only. One candidate, expiry, no public test route.
- HR access via SSO or real accounts. Audit who opened a scorecard or recording.
- Decide before go-live: full audio, or transcript + scorecard only. Encrypt what you keep.
- Production keys are new. Keys that lived on laptops do not move with Apollo audio.
- Kill switch: end a session and delete that candidate’s data inside the retention window you agreed.

## Product shell HR needs on day one

- HR list: status, tier with evidence, English scorecard, original-language transcript, export. ATS push can follow; CSV is enough for the POC.
- Candidate phone page: mic check that fails clearly, rejoin rule written down (same interview vs start over).
- Frozen language list agreed with Apollo. Scorecard in English beside the original transcript.
- Greeting, company name, and gate copy are Apollo’s.

## POC then production

- Shadow **20–30** calls with HR and a nurse lead, then ~**50** candidates, before talking about 100/day. Human rubric sits beside the AI tier.
- Success bar written first: completion rate, time to scorecard, agreement with the nurse lead, language list, cost per interview.
- One tagged build for the POC week. No deploys mid-week.
- Named person watches the first live mornings. One failure path for HR.
- End of POC: export or delete Apollo audio. It does not stay on a personal account.

## Paperwork easy to miss

- DPAs and security questionnaires from OpenAI, ElevenLabs, and LiveKit.
- Pitch language stays “first-round screen.”
- MSA: confidentiality, IP (their rubric vs your engine), recording licence, subprocessors, liability cap.
- A non-voice path for a candidate who cannot use the mic.
