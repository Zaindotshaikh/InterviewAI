import { Router, type Request, type Response, type NextFunction } from "express";
import { verifyV2Signature } from "../lib/hmac.js";
import {
  appendV2Event,
  appendV2Transcript,
  completeV2Interview,
  getV2Interview,
  updateV2Controller,
} from "../lib/v2Store.js";
import type { V2ControllerState } from "../lib/types.js";

const router = Router();

function requireInternalAuth(req: Request, res: Response, next: NextFunction): void {
  const rawBody = typeof req.body === "string" ? req.body : JSON.stringify(req.body ?? {});
  const timestamp = req.header("x-v2-timestamp") ?? undefined;
  const signature = req.header("x-v2-signature") ?? undefined;

  // Dev fallback: allow shared secret bearer when HMAC headers absent
  const bearer = req.header("authorization");
  const secret = process.env.V2_INTERNAL_SECRET || "dev-v2-internal-secret-change-me";
  if (bearer === `Bearer ${secret}`) {
    next();
    return;
  }

  const bodyForSig = JSON.stringify(req.body ?? {});
  if (!verifyV2Signature({ body: bodyForSig, timestamp, signature })) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }
  void rawBody;
  next();
}

router.use(requireInternalAuth);

router.get("/interviews/:id/plan", async (req, res) => {
  try {
    const record = await getV2Interview(req.params.id);
    if (!record) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }
    res.json({
      plan: record.extras.plan,
      controller: record.extras.controller,
      // Last turns, so a restarted agent can pick the conversation back up.
      recentTranscript: record.interview.transcript.slice(-8).map((t) => ({ role: t.role, text: t.text })),
      roomName: record.extras.roomName,
      providerMode: record.extras.providerMode,
      recordingConsent: record.extras.recordingConsent,
      avatar: Boolean(record.extras.avatar),
      ttsProvider: record.extras.ttsProvider || undefined,
    });
  } catch (err) {
    console.error("[v2/internal] plan error:", err);
    res.status(500).json({ error: "Failed to load plan" });
  }
});

router.post("/interviews/:id/transcript", async (req, res) => {
  try {
    const body = req.body as {
      role?: "user" | "assistant";
      text?: string;
      timestamp?: string;
      turnIndex?: number;
    };
    if (body.role !== "user" && body.role !== "assistant") {
      res.status(400).json({ error: "role must be user or assistant" });
      return;
    }
    if (!body.text?.trim()) {
      res.status(400).json({ error: "text is required" });
      return;
    }

    await appendV2Transcript(req.params.id, {
      role: body.role,
      text: body.text.trim(),
      timestamp: body.timestamp || new Date().toISOString(),
      turnIndex: body.turnIndex,
    });
    res.json({ ok: true });
  } catch (err) {
    console.error("[v2/internal] transcript error:", err);
    res.status(500).json({ error: "Failed to append transcript" });
  }
});

router.post("/interviews/:id/event", async (req, res) => {
  try {
    const body = req.body as { type?: string; data?: Record<string, unknown>; ts?: string };
    if (!body.type) {
      res.status(400).json({ error: "type is required" });
      return;
    }
    await appendV2Event(req.params.id, {
      ts: body.ts || new Date().toISOString(),
      type: body.type,
      data: body.data,
    });
    res.json({ ok: true });
  } catch (err) {
    console.error("[v2/internal] event error:", err);
    res.status(500).json({ error: "Failed to append event" });
  }
});

router.post("/interviews/:id/controller", async (req, res) => {
  try {
    const patch = req.body as Partial<V2ControllerState>;
    const controller = await updateV2Controller(req.params.id, patch);
    res.json({ controller });
  } catch (err) {
    console.error("[v2/internal] controller error:", err);
    res.status(500).json({ error: "Failed to update controller" });
  }
});

router.post("/interviews/:id/complete", async (req, res) => {
  try {
    await completeV2Interview(req.params.id);
    await appendV2Event(req.params.id, {
      ts: new Date().toISOString(),
      type: "interview.completed",
      data: (req.body as { data?: Record<string, unknown> })?.data,
    });
    res.json({ ok: true });
  } catch (err) {
    console.error("[v2/internal] complete error:", err);
    res.status(500).json({ error: "Failed to complete interview" });
  }
});

export default router;
