# Future scope

How to update this file: append short pointers only. Do not paste architecture.

- Language choice: keep the existing join-screen LanguagePicker for Phase 1. Later options to revisit: detect language from the first hi/hello; ask a spoken language question before the interview; mid-call language switch. Decision for now is the picker locks Scribe + ElevenLabs voice before audio. Wrong pick means join again. Do not build those later options now.
- Resume upload: `.doc` and HEIC stay rejected on `/elevenlabs-interviewer`. Revisit if candidates send those files.
- Video proctoring extras (not wired): frozen/black frame, face-too-far, second-speaker audio, tab-blur. Would need new IntegrityFlagType + banner/scorecard copy; keep FaceDetector count + landmarker look-away as the live path for now.
