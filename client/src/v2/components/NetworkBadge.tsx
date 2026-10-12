type Props = {
  quality: "excellent" | "good" | "poor" | "unknown";
  phase: string;
};

export default function NetworkBadge({ quality, phase }: Props) {
  const color =
    quality === "excellent" || quality === "good"
      ? "bg-emerald-100 text-emerald-800"
      : quality === "poor"
        ? "bg-amber-100 text-amber-900"
        : "bg-stone-100 text-stone-600";

  return (
    <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs ${color}`}>
      <span className="font-medium capitalize">{phase}</span>
      <span>·</span>
      <span>Network: {quality}</span>
    </div>
  );
}
