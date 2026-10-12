import { Router } from "express";
import OpenAI from "openai";
import { getInterview, saveIntegrity, saveSummary } from "../lib/store.js";
import { buildScorecardPrompt } from "../prompts/scorecard.js";

const router = Router();

router.post("/:id/integrity", async (req, res) => {
  try {
    const interview = await getInterview(req.params.id);
    if (!interview) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }

    const body = req.body as {
      available?: boolean;
      events?: Array<{
        type: "no_face" | "multiple_faces" | "looked_away";
        startTime: string;
        endTime: string;
        durationSeconds: number;
      }>;
    };

    const integrity = {
      available: Boolean(body.available),
      events: Array.isArray(body.events) ? body.events : [],
    };

    await saveIntegrity(req.params.id, integrity);
    res.json(integrity);
  } catch (err) {
    console.error("Integrity save error:", err);
    res.status(500).json({ error: "Failed to save integrity events" });
  }
});

router.post("/:id/summary", async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "OPENAI_API_KEY not configured" });
    return;
  }

  try {
    const interview = await getInterview(req.params.id);
    if (!interview) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }

    const body = req.body as {
      transcript?: { role: string; text: string }[];
      integrity?: {
        available?: boolean;
        events?: Array<{
          type: "no_face" | "multiple_faces" | "looked_away";
          startTime: string;
          endTime: string;
          durationSeconds: number;
        }>;
      };
    };

    if (body.integrity) {
      await saveIntegrity(req.params.id, {
        available: Boolean(body.integrity.available),
        events: Array.isArray(body.integrity.events) ? body.integrity.events : [],
      });
    }

    const transcript = body.transcript ?? interview.transcript;

    if (!transcript.length) {
      res.status(400).json({ error: "No transcript available to score" });
      return;
    }

    const prompt = buildScorecardPrompt({
      roleTitle: interview.roleTitle,
      candidateName: interview.candidateName,
      criteria: interview.criteria,
      transcript,
    });

    const openai = new OpenAI({ apiKey });
    const model = process.env.CHAT_MODEL || "gpt-4o";

    const completion = await openai.chat.completions.create({
      model,
      temperature: 0.3,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content:
            "You score completed job interviews. Return ONLY valid JSON matching the requested schema.",
        },
        { role: "user", content: prompt },
      ],
    });

    const raw = completion.choices[0]?.message?.content ?? "{}";
    const summary = JSON.parse(raw) as Record<string, unknown>;

    const refreshed = await getInterview(req.params.id);
    const integrity = refreshed?.integrity ?? body.integrity ?? { available: false, events: [] };

    const payload = {
      ...summary,
      integrity,
    };

    await saveSummary(req.params.id, payload);
    res.json(payload);
  } catch (err) {
    console.error("Summary error:", err);
    res.status(500).json({ error: "Failed to generate scorecard" });
  }
});

export default router;
