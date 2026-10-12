import { Router } from "express";

const router = Router();

type MintSession = {
  type: "realtime";
  model: string;
  instructions?: string;
  max_output_tokens?: number;
  truncation?: { type: string; retention_ratio: number };
  audio: { output: { voice: string } };
};

async function mintClientSecret(apiKey: string, session: MintSession) {
  return fetch("https://api.openai.com/v1/realtime/client_secrets", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session }),
  });
}

/**
 * Mint an ephemeral OpenAI Realtime client secret.
 * Real OPENAI_API_KEY never leaves the server.
 */
router.post("/", async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "OPENAI_API_KEY not configured" });
    return;
  }

  const model = process.env.REALTIME_MODEL || "gpt-realtime";
  const instructions =
    typeof req.body?.instructions === "string" && req.body.instructions.trim()
      ? req.body.instructions
      : undefined;

  const base: MintSession = {
    type: "realtime",
    model,
    ...(instructions ? { instructions } : {}),
    audio: {
      output: {
        voice: process.env.REALTIME_VOICE || "cedar",
      },
    },
  };

  try {
    let response = await mintClientSecret(apiKey, {
      ...base,
      // inf reserves the whole TPM budget per turn and the session dies after a few questions
      max_output_tokens: 512,
      truncation: { type: "retention_ratio", retention_ratio: 0.8 },
    });

    if (!response.ok) {
      const firstError = await response.text();
      console.warn("Session mint with token caps failed, retrying without caps:", response.status, firstError);
      response = await mintClientSecret(apiKey, base);
      if (!response.ok) {
        const text = await response.text();
        console.error("Failed to mint client secret:", response.status, text);
        res.status(response.status).json({
          error: "Failed to mint ephemeral session key",
          details: text,
        });
        return;
      }
    }

    const data = (await response.json()) as {
      value?: string;
      client_secret?: { value?: string };
      expires_at?: number;
    };

    const ephemeralKey = data.value ?? data.client_secret?.value;
    if (!ephemeralKey) {
      console.error("Unexpected client_secrets response:", data);
      res.status(500).json({ error: "No ephemeral key in response", raw: data });
      return;
    }

    console.info(`[session] minted model=${model} instructions=${instructions?.length ?? 0}c`);
    res.json({
      client_secret: ephemeralKey,
      model,
      expires_at: data.expires_at ?? null,
    });
  } catch (err) {
    console.error("Session mint error:", err);
    res.status(500).json({ error: "Internal error minting session" });
  }
});

export default router;
