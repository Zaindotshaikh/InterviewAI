# Future scope

How to update this file: append short pointers only. Do not paste architecture.

- Language choice: keep the existing join-screen LanguagePicker for Phase 1. Later options to revisit: detect language from the first hi/hello; ask a spoken language question before the interview; mid-call language switch. Decision for now is the picker locks Scribe + ElevenLabs voice before audio. Wrong pick means join again. Do not build those later options now.
- Resume upload: `.doc` and HEIC stay rejected on `/elevenlabs-interviewer`. Revisit if candidates send those files.
- Video proctoring extras (not wired): frozen/black frame, face-too-far, second-speaker audio, tab-blur. Would need new IntegrityFlagType + banner/scorecard copy; keep FaceDetector count + landmarker look-away as the live path for now.
- ElevenLabs hosted STS / ElevenAgents / Eleven Realtime / Speech Engine: researched 28 Oct 2026. Marketing says Speech-to-Speech; ElevenLabs documents an advanced **cascade** (Realtime is explicitly not fused). Custom LLM cannot run in Realtime mode. Workflows would replace InterviewFlow. Speech Engine can sit in front of our text brain but owns turn-taking and is a transport rewrite. Not the demo path. Revisit only if Flow still approves every spoken line and LanguagePicker still locks language. Detail: `docs/poc-implementation-plan.md` section 2.
- GPT-Live as the demo: still no. Full duplex is a better phone-call feeling and a worse policy brain. Do not collect language, policy, or clinical feedback on `/gpt-live-interviewer`.
- Hello-detect language / spoken language question: still no. LanguagePicker lock stays.
- Avatar / Tavus on the demo: still out. Presence orb only. Client requirements §8 still lists a face; POC decision is voice-only.
- Architecture-note one diaper re-ask: keep code/POC two persuasions then `gate_failed`. One re-ask is an HR/compliance choice for later, not the quality round.
- Sarvam as default ears/mouth: still fallback-only after Scribe then OpenAI STT fail a language station. Do not flip the demo worker.
