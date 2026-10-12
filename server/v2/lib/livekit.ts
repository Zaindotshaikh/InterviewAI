import { AccessToken, AgentDispatchClient, RoomAgentDispatch, RoomConfiguration, RoomServiceClient } from "livekit-server-sdk";

export type LiveKitConfig = {
  url: string;
  apiKey: string;
  apiSecret: string;
  agentName: string;
};

export function getLiveKitConfig(): LiveKitConfig | null {
  const url = process.env.LIVEKIT_URL?.trim();
  const apiKey = process.env.LIVEKIT_API_KEY?.trim();
  const apiSecret = process.env.LIVEKIT_API_SECRET?.trim();
  if (!url || !apiKey || !apiSecret) return null;
  return {
    url,
    apiKey,
    apiSecret,
    agentName: process.env.V2_AGENT_NAME?.trim() || "interview-v2",
  };
}

export function isLiveKitConfigured(): boolean {
  return getLiveKitConfig() !== null;
}

function interviewJobMeta(opts: {
  interviewId: string;
  avatar?: boolean;
  ttsProvider?: string;
}): Record<string, unknown> {
  return {
    interviewId: opts.interviewId,
    avatar: Boolean(opts.avatar),
    ...(opts.ttsProvider ? { ttsProvider: opts.ttsProvider } : {}),
  };
}

export async function createCandidateToken(opts: {
  roomName: string;
  identity: string;
  interviewId: string;
  metadata?: Record<string, unknown>;
  avatar?: boolean;
  ttsProvider?: string;
}): Promise<{ token: string; url: string; agentName: string }> {
  const cfg = getLiveKitConfig();
  if (!cfg) {
    throw new Error("LiveKit is not configured (set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)");
  }

  const jobMeta = interviewJobMeta(opts);
  const at = new AccessToken(cfg.apiKey, cfg.apiSecret, {
    identity: opts.identity,
    name: opts.identity,
    metadata: JSON.stringify({
      ...jobMeta,
      ...(opts.metadata ?? {}),
    }),
    ttl: "2h",
  });

  at.addGrant({
    roomJoin: true,
    room: opts.roomName,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  at.roomConfig = new RoomConfiguration({
    agents: [
      new RoomAgentDispatch({
        agentName: cfg.agentName,
        metadata: JSON.stringify(jobMeta),
      }),
    ],
  });

  const token = await at.toJwt();
  return { token, url: cfg.url, agentName: cfg.agentName };
}

export async function ensureRoomAndDispatch(opts: {
  roomName: string;
  interviewId: string;
  avatar?: boolean;
  ttsProvider?: string;
}): Promise<void> {
  const cfg = getLiveKitConfig();
  if (!cfg) return;

  const jobMeta = interviewJobMeta(opts);
  const httpUrl = cfg.url.replace(/^wss:/, "https:").replace(/^ws:/, "http:");
  const rooms = new RoomServiceClient(httpUrl, cfg.apiKey, cfg.apiSecret);
  try {
    await rooms.createRoom({
      name: opts.roomName,
      emptyTimeout: 60 * 10,
      maxParticipants: opts.avatar ? 8 : 4,
      metadata: JSON.stringify({
        ...jobMeta,
        pipeline: "v2",
      }),
    });
  } catch {
    // Room may already exist — fine
  }

  try {
    const dispatch = new AgentDispatchClient(httpUrl, cfg.apiKey, cfg.apiSecret);
    // A candidate rejoining after a drop must not summon a second interviewer into the same room.
    const existing = await dispatch.listDispatch(opts.roomName).catch(() => []);
    if (existing.some((d) => d.agentName === cfg.agentName)) return;
    await dispatch.createDispatch(opts.roomName, cfg.agentName, {
      metadata: JSON.stringify(jobMeta),
    });
  } catch (err) {
    console.warn("[v2] explicit agent dispatch failed (token dispatch may still work):", err);
  }
}

export function roomNameForInterview(interviewId: string): string {
  return `interview-v2-${interviewId}`;
}
