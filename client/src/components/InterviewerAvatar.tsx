type Props = {
  speaking: boolean;
  listening: boolean;
  thinking: boolean;
};

export default function InterviewerAvatar({ speaking, listening, thinking }: Props) {
  const label = speaking ? "Speaking" : thinking ? "Thinking" : listening ? "Listening" : "Ready";

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative grid h-40 w-40 place-items-center">
        <div
          className={`absolute inset-0 rounded-full transition-all duration-500 ${
            speaking
              ? "animate-pulse bg-[var(--color-accent)]/25 blur-xl scale-110"
              : thinking
                ? "bg-[var(--color-warn)]/15 blur-xl"
                : "bg-[var(--color-accent)]/10 blur-lg"
          }`}
        />
        <div
          className={`absolute inset-3 rounded-full border transition-all duration-300 ${
            speaking
              ? "border-[var(--color-accent)] shadow-[0_0_40px_rgba(107,184,47,0.4)]"
              : "border-[var(--color-line)]"
          }`}
        />
        <div
          className={`h-24 w-24 rounded-full bg-gradient-to-br from-[var(--color-avatar-from)] via-[var(--color-avatar-via)] to-[var(--color-avatar-to)] transition-transform duration-300 ${
            speaking ? "scale-105" : "scale-100"
          }`}
        />
        <div
          className={`absolute h-3 w-3 rounded-full ${
            speaking
              ? "bg-[var(--color-accent)]"
              : thinking
                ? "bg-[var(--color-warn)] animate-pulse"
                : listening
                  ? "bg-[var(--color-fg)]/70"
                  : "bg-[var(--color-muted)]"
          }`}
        />
      </div>
      <p className="text-xs tracking-[0.18em] text-[var(--color-muted)] uppercase">{label}</p>
    </div>
  );
}
