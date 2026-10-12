import { Router } from "express";
import { appendTranscriptTurn, getInterview } from "../lib/store.js";

const router = Router();

router.post("/:id/transcript", async (req, res) => {
  try {
    const interview = await getInterview(req.params.id);
    if (!interview) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }

    const { role, text, timestamp } = req.body as {
      role?: "user" | "assistant";
      text?: string;
      timestamp?: string;
    };

    if (!role || !text?.trim()) {
      res.status(400).json({ error: "role and text are required" });
      return;
    }

    const turn = {
      role,
      text: text.trim(),
      timestamp: timestamp || new Date().toISOString(),
    };

    await appendTranscriptTurn(req.params.id, turn);
    res.json({ ok: true, turn });
  } catch (err) {
    console.error("Transcript log error:", err);
    res.status(500).json({ error: "Failed to log transcript" });
  }
});

export default router;
