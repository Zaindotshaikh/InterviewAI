# Listening harness (Phase 4)

Render fixed lines per tone for human review of `eleven_v4_turbo` tags.

```bash
cd agent
.\.venv\Scripts\python.exe -m eval.audio_ab_render
```

Outputs WAVs under `eval/audio_ab/out/`.

**Checklist**
- [ ] Tag is *not* read aloud as words
- [ ] Tone is audibly distinct across whitelist tags
- [ ] Compare with/without VoiceSettings if supported on v4 turbo
- [ ] Drop or replace any tag that fails

Reviewed filler languages: `hi-IN`, `mr-IN`, `en-IN`. Others fall back to hi/en forms.
