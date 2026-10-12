export type SessionCredentials = {
  client_secret: string;
  model: string;
  expires_at: number | null;
};

export async function fetchEphemeralSession(
  instructions?: string,
): Promise<SessionCredentials> {
  const res = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(instructions ? { instructions } : {}),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to mint session (${res.status}): ${body}`);
  }
  return res.json() as Promise<SessionCredentials>;
}

/**
 * Connect to OpenAI Realtime over WebRTC using an ephemeral client secret.
 * Returns peer connection, data channel, and local mic stream.
 */
export async function connectRealtimeWebRTC(options: {
  ephemeralKey: string;
  model: string;
  instructions: string;
  onRemoteTrack: (stream: MediaStream) => void;
  onDataChannel: (channel: RTCDataChannel) => void;
}): Promise<{
  pc: RTCPeerConnection;
  dc: RTCDataChannel;
  localStream: MediaStream;
}> {
  const pc = new RTCPeerConnection();

  pc.ontrack = (event) => {
    const stream = event.streams[0] ?? new MediaStream([event.track]);
    options.onRemoteTrack(stream);
  };

  const localStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });

  for (const track of localStream.getTracks()) {
    pc.addTrack(track, localStream);
  }

  const dc = pc.createDataChannel("oai-events");
  options.onDataChannel(dc);

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const baseUrl = "https://api.openai.com/v1/realtime/calls";
  const url = `${baseUrl}?model=${encodeURIComponent(options.model)}`;

  const sdpResponse = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${options.ephemeralKey}`,
      "Content-Type": "application/sdp",
    },
    body: offer.sdp ?? "",
  });

  if (!sdpResponse.ok) {
    const errText = await sdpResponse.text();
    localStream.getTracks().forEach((t) => t.stop());
    pc.close();
    throw new Error(`Realtime SDP exchange failed (${sdpResponse.status}): ${errText}`);
  }

  const answerSdp = await sdpResponse.text();
  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

  return { pc, dc, localStream };
}

export type TranscriptionContext = {
  roleTitle?: string;
  keywords?: string[];
};

export function buildTranscriptionPrompt(ctx?: TranscriptionContext): string {
  // Keep this SHORT. Resume/keyword prompts cause ASR to paste CV text into captions.
  const role = ctx?.roleTitle?.trim();
  const base =
    "Live spoken job interview. Transcribe only words the speaker actually said. Never invent, complete, or paste resume text, professional summaries, job descriptions, CV headers, or documents.";
  if (!role) return base;
  return `${base} Role discussed: ${role}.`;
}

export const REALTIME_MAX_OUTPUT_TOKENS = 512;

function responseCreatePayload(instructions: string) {
  return {
    type: "response.create",
    response: {
      instructions,
      max_output_tokens: REALTIME_MAX_OUTPUT_TOKENS,
    },
  };
}

/**
 * Configure session after connect.
 * Voice is set once on the server-minted client secret. Never send `audio.output.voice`
 * here after assistant audio has started (API: cannot_update_voice).
 */
export function sendSessionUpdate(
  dc: RTCDataChannel,
  instructions: string,
  transcriptionContext?: TranscriptionContext,
): void {
  const event = {
    type: "session.update",
    session: {
      type: "realtime",
      instructions,
      max_output_tokens: REALTIME_MAX_OUTPUT_TOKENS,
      audio: {
        input: {
          turn_detection: {
            type: "server_vad",
            // Manual response.create only after a substantive transcript
            create_response: false,
            // Interviews: finish the spoken question. Don't stop on coughs/echo/noise
            interrupt_response: false,
            silence_duration_ms: 3200,
            // Higher = fewer false "speech started" from room noise / speaker bleed
            threshold: 0.78,
            prefix_padding_ms: 280,
          },
          transcription: {
            model: "gpt-4o-transcribe",
            // No hard language lock; follows candidate speech
            prompt: buildTranscriptionPrompt(transcriptionContext),
          },
        },
      },
    },
  };
  dc.send(JSON.stringify(event));

  // Separate update so a rejected truncation field cannot wipe VAD config
  dc.send(
    JSON.stringify({
      type: "session.update",
      session: {
        type: "realtime",
        truncation: { type: "retention_ratio", retention_ratio: 0.8 },
      },
    }),
  );
}

export function requestCancelResponse(dc: RTCDataChannel): void {
  if (dc.readyState !== "open") return;
  try {
    dc.send(JSON.stringify({ type: "response.cancel" }));
  } catch {
    /* ignore */
  }
}

export function requestInitialGreeting(
  dc: RTCDataChannel,
  candidateName: string,
  options?: { demo?: boolean; interviewerName?: string },
): void {
  const name = candidateName.trim() || "the candidate";
  const self = options?.interviewerName?.trim();
  const instructions = `This is your FIRST spoken turn only. Greet ${name} by that exact name. ${
    self ? `Say you are ${self}. ` : ""
  }Then ask ONLY for a quick introduction about themselves (who they are and what they do). Forbidden this turn: behavioral questions, STAR questions, resume questions, "tell me about a time…", "what excites you about this position/role", "let's jump right in" plus a content question, difficult problems, challenges, strengths, why this role. One or two short sentences. English.`;

  dc.send(JSON.stringify(responseCreatePayload(instructions)));
}

/**
 * Continue after a verified substantive candidate answer.
 * Do not auto-skip — only advance if they actually addressed the current question.
 */
export function requestAssistantResponse(dc: RTCDataChannel): void {
  if (dc.readyState !== "open") return;
  dc.send(
    JSON.stringify(
      responseCreatePayload(`The candidate just spoke. Use your session interview sequence, but do NOT skip ahead.
- If their reply did NOT really answer the CURRENT unanswered question (too short, vague, "I don't know" with no attempt, off-topic, a fragment, or just stalling): do NOT go to the next question. In one short sentence, restate the SAME question.
- If they DID answer the current question with a real example or explanation: then continue the sequence (next intro follow-up, or one resume follow-up, or the next written resume question). After the third resume question and its follow-up, thank them and end.
Never invent "what excites you about this position" or "tell me about a time you solved a difficult problem". Keep your turn to 1-2 short sentences.`),
    ),
  );
}

/** Candidate audio was noise/filler. Restate the same unanswered question; do not advance. */
export function requestRestateCurrentQuestion(dc: RTCDataChannel): void {
  if (dc.readyState !== "open") return;
  dc.send(
    JSON.stringify(
      responseCreatePayload(
        `The latest candidate audio was NOT a real answer (noise, cough, filler, incomplete, or too short). Do NOT move to the next question. In one short sentence, politely restate your CURRENT unanswered interview question with the same meaning. Do not invent a new question.`,
      ),
    ),
  );
}
