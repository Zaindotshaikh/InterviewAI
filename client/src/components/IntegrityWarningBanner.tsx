import { AnimatePresence, motion } from "framer-motion";
import type { IntegrityFlagType } from "../lib/integrity";

const WARNING_COPY: Record<
  IntegrityFlagType,
  { title: string; body: string; severity: "critical" | "high" }
> = {
  no_face: {
    title: "CAMERA ALERT: FACE NOT VISIBLE",
    body: "Return to the frame immediately. Leaving the camera may be flagged on your scorecard.",
    severity: "critical",
  },
  multiple_faces: {
    title: "CAMERA ALERT: MULTIPLE PEOPLE IN FRAME",
    body: "Only you should be visible. Clear others from the camera now. This is recorded for the hiring team.",
    severity: "critical",
  },
  looked_away: {
    title: "ATTENTION: LOOK AT THE CAMERA",
    body: "You’ve been looking away. Face the camera and stay engaged for the rest of this question.",
    severity: "high",
  },
};

/** Priority if several flags are active at once */
const PRIORITY: IntegrityFlagType[] = ["no_face", "multiple_faces", "looked_away"];

type Props = {
  warnings: IntegrityFlagType[];
};

export default function IntegrityWarningBanner({ warnings }: Props) {
  const primary = PRIORITY.find((t) => warnings.includes(t));
  const copy = primary ? WARNING_COPY[primary] : null;
  const critical = copy?.severity === "critical";

  return (
    <AnimatePresence>
      {copy && primary && (
        <motion.div
          key={primary}
          initial={{ opacity: 0, y: -16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.98 }}
          transition={{ duration: 0.22 }}
          className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center px-3 pt-3 sm:pt-4"
          role="alert"
          aria-live="assertive"
        >
          <motion.div
            animate={
              critical
                ? {
                    boxShadow: [
                      "0 0 0 0 rgba(239, 107, 107, 0.55)",
                      "0 0 0 14px rgba(239, 107, 107, 0)",
                      "0 0 0 0 rgba(239, 107, 107, 0.55)",
                    ],
                  }
                : {
                    boxShadow: [
                      "0 0 0 0 rgba(240, 180, 41, 0.45)",
                      "0 0 0 12px rgba(240, 180, 41, 0)",
                      "0 0 0 0 rgba(240, 180, 41, 0.45)",
                    ],
                  }
            }
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
            className={`w-[min(96vw,520px)] overflow-hidden rounded-xl border-2 ${
              critical
                ? "border-[var(--color-danger)] bg-[var(--color-danger-surface)]"
                : "border-[var(--color-warn)] bg-[var(--color-warn-surface)]"
            }`}
          >
            <div
              className={`flex items-stretch gap-3 px-4 py-3.5 sm:px-5 sm:py-4 ${
                critical ? "bg-[var(--color-danger)]/15" : "bg-[var(--color-warn)]/12"
              }`}
            >
              <motion.div
                animate={{ scale: [1, 1.12, 1], opacity: [1, 0.75, 1] }}
                transition={{ duration: 0.9, repeat: Infinity }}
                className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg text-lg font-black ${
                  critical
                    ? "bg-[var(--color-danger)] text-[var(--color-on-danger)]"
                    : "bg-[var(--color-warn)] text-[var(--color-on-warn)]"
                }`}
                aria-hidden
              >
                !
              </motion.div>
              <div className="min-w-0 flex-1">
                <p
                  className={`text-[11px] font-bold tracking-[0.14em] uppercase sm:text-xs ${
                    critical ? "text-[var(--color-danger)]" : "text-[var(--color-warn)]"
                  }`}
                >
                  Proctoring warning
                </p>
                <p className="mt-1 text-sm font-semibold leading-snug text-[var(--color-fg)] sm:text-base">
                  {copy.title}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-[var(--color-fg)]/75 sm:text-sm">
                  {copy.body}
                </p>
              </div>
            </div>
            <motion.div
              className={`h-1 origin-left ${
                critical ? "bg-[var(--color-danger)]" : "bg-[var(--color-warn)]"
              }`}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.45, ease: "easeOut" }}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
