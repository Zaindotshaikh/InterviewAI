import { createHmac, timingSafeEqual } from "crypto";

export function getV2InternalSecret(): string {
  return process.env.V2_INTERNAL_SECRET || "dev-v2-internal-secret-change-me";
}

export function signV2Payload(body: string, timestamp: string, secret = getV2InternalSecret()): string {
  return createHmac("sha256", secret).update(`${timestamp}.${body}`).digest("hex");
}

export function verifyV2Signature(opts: {
  body: string;
  timestamp: string | undefined;
  signature: string | undefined;
  maxSkewMs?: number;
}): boolean {
  const { body, timestamp, signature, maxSkewMs = 5 * 60 * 1000 } = opts;
  if (!timestamp || !signature) return false;
  const ts = Number(timestamp);
  if (!Number.isFinite(ts)) return false;
  if (Math.abs(Date.now() - ts) > maxSkewMs) return false;

  const expected = signV2Payload(body, timestamp);
  try {
    const a = Buffer.from(expected, "hex");
    const b = Buffer.from(signature, "hex");
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}
