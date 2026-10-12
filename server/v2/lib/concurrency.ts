/**
 * Simple in-process queue to avoid bursting Sarvam WebSocket connects.
 * Starter plan rejects fast connection bursts even below concurrent ceilings.
 */

let chain: Promise<void> = Promise.resolve();
let active = 0;

export type ConcurrencyStats = { active: number; waiting: number };

let waiting = 0;

export function getV2ConcurrencyStats(): ConcurrencyStats {
  return { active, waiting };
}

export async function withV2StartSlot<T>(fn: () => Promise<T>, gapMs = 350): Promise<T> {
  waiting += 1;
  const run = chain.then(async () => {
    waiting -= 1;
    active += 1;
    try {
      const result = await fn();
      await new Promise((r) => setTimeout(r, gapMs));
      return result;
    } finally {
      active -= 1;
    }
  });
  // Keep chain alive even if one start fails
  chain = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}
