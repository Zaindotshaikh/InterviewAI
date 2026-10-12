import { useEffect, useMemo, useRef } from "react";
import type { Caption } from "../hooks/useRealtimeSession";
import { isResumeLeak } from "../lib/resumeLeak";

type Props = {
  captions: Caption[];
  variant?: "panel" | "hud";
  interviewerName?: string;
  resumeText?: string;
};

/** Skip empty / failed / resume-dump caption segments. Never hide a long spoken answer. */
export function isRenderableCaption(text: string, resumeText?: string): boolean {
  const t = text.trim();
  if (!t || t.length < 2) return false;

  if (/^(null|undefined|\[inaudible\]|\(inaudible\)|\.\.\.)$/i.test(t)) return false;

  if (isResumeLeak(t, resumeText)) return false;

  const letters = (t.match(/[\p{L}\p{N}]/gu) ?? []).length;
  if (letters < 2) return false;

  if (/(.)\1{6,}/.test(t)) return false;

  return true;
}

export default function LiveCaptions({
  captions,
  variant = "panel",
  interviewerName,
  resumeText,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const visible = useMemo(
    () => captions.filter((c) => isRenderableCaption(c.text, resumeText)),
    [captions, resumeText],
  );

  // HUD: keep only the latest turn so the video face stays visible
  const shown = variant === "hud" ? visible.slice(-1) : visible;
  const interviewerLabel = interviewerName?.trim() || "Interviewer";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [shown]);

  if (variant === "hud") {
    const current = shown[0];
    const hudText = current
      ? current.text.length > 160
        ? `${current.text.slice(0, 157).trimEnd()}…`
        : current.text
      : null;

    return (
      <div className="min-h-[2.75rem] max-h-16 overflow-hidden px-0.5">
        {!current ? (
          <p className="text-[11px] tracking-wide text-white/45">Awaiting audio…</p>
        ) : (
          <p className="line-clamp-2 text-[12px] leading-snug break-words sm:text-[13px]">
            <span
              className={
                current.role === "assistant"
                  ? "mr-1.5 font-semibold tracking-wide text-[var(--color-accent)] uppercase"
                  : "mr-1.5 font-semibold tracking-wide text-white/70 uppercase"
              }
            >
              {current.role === "assistant" ? interviewerLabel : "You"}
            </span>
            <span className={current.partial ? "text-white/50" : "text-white/90"}>{hudText}</span>
          </p>
        )}
        <div ref={bottomRef} />
      </div>
    );
  }

  return (
    <div className="h-36 w-full overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)]/70 px-4 py-3 sm:h-40">
      {visible.length === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">Live captions will appear here…</p>
      ) : (
        <ul className="space-y-2.5">
          {visible.map((c) => (
            <li key={c.id} className="text-sm leading-relaxed">
              <span
                className={
                  c.role === "assistant"
                    ? "mr-2 font-semibold text-[var(--color-accent)]"
                    : "mr-2 font-semibold text-[var(--color-fg)]/80"
                }
              >
                {c.role === "assistant" ? interviewerLabel : "You"}
              </span>
              <span className={c.partial ? "text-[var(--color-muted)]" : "text-[var(--color-caption)]"}>
                {c.text}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
