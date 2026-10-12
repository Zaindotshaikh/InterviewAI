type Props = {
  /** Overall diameter in px. Default 96. */
  size?: number;
};

/**
 * Flat accent-colored core with three particles on independent orbits.
 * CSS-only. No JS animation loop.
 */
export function OrbitingLoader({ size = 96 }: Props) {
  const core = Math.round(size * 0.22);
  const particle = Math.max(6, Math.round(size * 0.08));
  const radii = [0.32, 0.42, 0.52].map((r) => Math.round(size * r));
  const durations = ["2.4s", "3.6s", "5.2s"];
  const opacities = [0.95, 0.7, 0.5];

  return (
    <div
      className="orbiting-loader relative mx-auto"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <span
        className="orbiting-loader__core absolute top-1/2 left-1/2 rounded-full bg-[var(--color-accent)]"
        style={{
          width: core,
          height: core,
          marginLeft: -core / 2,
          marginTop: -core / 2,
        }}
      />
      {radii.map((radius, i) => (
        <span
          key={i}
          className="orbiting-loader__orbit absolute top-1/2 left-1/2"
          style={{
            width: radius * 2,
            height: radius * 2,
            marginLeft: -radius,
            marginTop: -radius,
            animationDuration: durations[i],
          }}
        >
          <span
            className="absolute top-0 left-1/2 rounded-full bg-[var(--color-accent)]"
            style={{
              width: particle,
              height: particle,
              marginLeft: -particle / 2,
              opacity: opacities[i],
            }}
          />
        </span>
      ))}
    </div>
  );
}
