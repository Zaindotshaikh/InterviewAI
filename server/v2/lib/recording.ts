/**
 * Optional LiveKit egress recording for v2 interviews (audio-only).
 * Requires LIVEKIT_* plus S3-compatible credentials when enabled.
 */

import { EgressClient, EncodedFileOutput, EncodedFileType, S3Upload } from "livekit-server-sdk";
import { getLiveKitConfig } from "./livekit.js";

export function isRecordingConfigured(): boolean {
  return Boolean(
    process.env.V2_RECORDING_ENABLED === "true" &&
      process.env.AWS_BUCKET_NAME &&
      process.env.AWS_ACCESS_KEY_ID &&
      process.env.AWS_SECRET_ACCESS_KEY,
  );
}

export async function startInterviewRecording(opts: {
  roomName: string;
  interviewId: string;
}): Promise<{ egressId?: string } | null> {
  if (!isRecordingConfigured()) return null;
  const cfg = getLiveKitConfig();
  if (!cfg) return null;

  const httpUrl = cfg.url.replace(/^wss:/, "https:").replace(/^ws:/, "http:");
  const egress = new EgressClient(httpUrl, cfg.apiKey, cfg.apiSecret);

  const fileOutput = new EncodedFileOutput({
    fileType: EncodedFileType.OGG,
    filepath: `interviews/${opts.interviewId}.ogg`,
    output: {
      case: "s3",
      value: new S3Upload({
        bucket: process.env.AWS_BUCKET_NAME!,
        region: process.env.AWS_REGION || "ap-south-1",
        accessKey: process.env.AWS_ACCESS_KEY_ID!,
        secret: process.env.AWS_SECRET_ACCESS_KEY!,
      }),
    },
  });

  try {
    const info = await egress.startRoomCompositeEgress(opts.roomName, { file: fileOutput }, { audioOnly: true });
    return { egressId: info.egressId };
  } catch (err) {
    console.warn("[v2] egress start failed:", err);
    return null;
  }
}
