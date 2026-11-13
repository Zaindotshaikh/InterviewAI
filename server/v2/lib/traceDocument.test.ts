import assert from "node:assert/strict";
import { test } from "node:test";
import { applyTraceChange, emptyTrace } from "./traceDocument.js";

test("a call file keeps the decision, the spoken line, and the timings on one turn", () => {
  let doc = applyTraceChange("interview-1", null, {
    op: "open",
    language: "hi-IN",
    startedAt: "2026-11-12T10:30:00.000Z",
    build: "local",
    models: {
      screening: "gpt-5.4-mini",
      clinical: "gpt-4o",
      wording: "gpt-4o-mini",
      wordingFallback: "gpt-4.1-mini",
      speechToText: "elevenlabs_scribe",
      textToSpeech: "eleven_v4_turbo",
      voiceLanguage: "hi-IN",
      secret: "nope",
    },
  });
  doc = applyTraceChange("interview-1", doc, {
    op: "turn",
    index: 1,
    stage: "screening",
    focus: "slot:phone",
    move: "confirm",
    line: "fixed",
    heard: "9876543210",
    commit: "short_answer",
    attempt: 1,
    analyst: { source: "llm", model: "gpt-5.4-mini", intent: "answer" },
  });
  doc = applyTraceChange("interview-1", doc, {
    op: "turn",
    index: 1,
    timeline: { fromSessionStartMs: { speechEnd: 12040, scribeFinal: 12410, replyAudio: 13980, ignored: 1 } },
    latencyMs: { director: 710.4, replyAfterSpeech: 1940, nope: 5 },
  });
  doc = applyTraceChange("interview-1", doc, {
    op: "spoken",
    index: 1,
    spoken: "Aapka number nine eight seven hai.",
  });
  doc = applyTraceChange("interview-1", doc, {
    op: "close",
    at: "2026-11-12T10:40:00.000Z",
    reason: "completed",
    outcome: "completed",
    stage: "ended",
    durationMs: 600000,
    slots: [
      { field: "phone", value: "9876543210", status: "confirmed", confidence: 0.94, attempts: 1 },
      { field: "city", value: null, status: "empty", attempts: 0 },
    ],
    summary: {
      turns: 1,
      director_ms: { n: 1, p50: 710.2, p95: 710.2, max: 710.2, mean: 710.2 },
      reply_from_vad_ms: { n: 1, p50: 1940, p95: 1940, max: 1940 },
    },
  });

  assert.deepEqual(doc, {
    interviewId: "interview-1",
    language: "hi-IN",
    startedAt: "2026-11-12T10:30:00.000Z",
    build: "local",
    models: {
      screening: "gpt-5.4-mini",
      clinical: "gpt-4o",
      wording: "gpt-4o-mini",
      wordingFallback: "gpt-4.1-mini",
      speechToText: "elevenlabs_scribe",
      textToSpeech: "eleven_v4_turbo",
      voiceLanguage: "hi-IN",
    },
    turns: [
      {
        index: 1,
        stage: "screening",
        focus: "slot:phone",
        move: "confirm",
        line: "fixed",
        heard: "9876543210",
        spoken: "Aapka number nine eight seven hai.",
        commit: "short_answer",
        attempt: 1,
        analyst: { source: "llm", model: "gpt-5.4-mini", intent: "answer" },
        timeline: { fromSessionStartMs: { speechEnd: 12040, scribeFinal: 12410, replyAudio: 13980 } },
        latencyMs: { director: 710, replyAfterSpeech: 1940 },
      },
    ],
    summary: {
      turns: 1,
      directorMs: { count: 1, median: 710, p95: 710, max: 710 },
      replyAfterSpeechMs: { count: 1, median: 1940, p95: 1940, max: 1940 },
    },
    closed: {
      at: "2026-11-12T10:40:00.000Z",
      reason: "completed",
      outcome: "completed",
      stage: "ended",
      durationMs: 600000,
      slots: [{ field: "phone", value: "9876543210", status: "confirmed", confidence: 0.94, attempts: 1 }],
    },
  });
  assert.equal(emptyTrace("interview-1").turns.length, 0);
});
