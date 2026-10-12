import type { V2Scorecard } from "../types";
import { summarizeIntegrityEvents } from "../../lib/integrity";

const TIER_STYLE: Record<string, string> = {
  tier_1: "bg-emerald-100 text-emerald-900",
  tier_2: "bg-sky-100 text-sky-900",
  tier_3: "bg-amber-100 text-amber-900",
  not_eligible: "bg-red-100 text-red-900",
  needs_review: "bg-stone-200 text-stone-800",
};

const OUTCOME_STYLE: Record<string, string> = {
  strong: "text-emerald-700",
  adequate: "text-sky-700",
  weak: "text-amber-700",
  unsafe: "text-red-700",
  unknown: "text-stone-500",
};

const LABELS: Record<string, string> = {
  city: "City",
  phone: "Phone",
  qualification: "Qualification",
  qualification_year: "Year of passing",
  height_cm: "Height (cm)",
  weight_kg: "Weight (kg)",
  experience_years: "Experience (years)",
  experience_settings: "Settings worked in",
  experience_level: "Experience level",
};

function prettyKey(k: string): string {
  return LABELS[k] ?? k.replace(/_/g, " ");
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-stone-500">{title}</p>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

export default function ScorecardView({ scorecard }: { scorecard: V2Scorecard }) {
  const screening = Object.entries(scorecard.screening ?? {}).filter(([k]) => k !== "care_duties");
  const care = (scorecard.screening?.care_duties ?? {}) as Record<string, string>;

  return (
    <div className="mt-6 space-y-4 rounded-xl border border-stone-200 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {scorecard.tier && (
          <span className={`rounded-full px-3 py-1 text-sm font-medium ${TIER_STYLE[scorecard.tier] ?? ""}`}>
            {scorecard.tier_name ?? scorecard.tier}
          </span>
        )}
        {scorecard.overall_score != null && <span className="text-sm text-stone-600">Score {scorecard.overall_score}/10</span>}
        {scorecard.tier_confidence != null && (
          <span className="text-xs text-stone-500">
            confidence {Math.round(scorecard.tier_confidence * 100)}%
            {scorecard.tier_method === "rule" ? " (rule-based)" : ""}
          </span>
        )}
      </div>

      <Section title="Why">
        <p>{scorecard.tier_reasoning ?? scorecard.recommendation}</p>
      </Section>

      {!!scorecard.flags?.length && (
        <Section title="Flags">
          <ul className="list-disc pl-5">
            {scorecard.flags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </Section>
      )}

      {scorecard.integrity && (
        <Section title="Camera / proctoring">
          {!scorecard.integrity.available ? (
            <p className="text-stone-600">Camera checks were not available for this session.</p>
          ) : summarizeIntegrityEvents(scorecard.integrity.events).length === 0 ? (
            <p className="text-stone-600">No integrity concerns detected.</p>
          ) : (
            <ul className="list-disc pl-5">
              {summarizeIntegrityEvents(scorecard.integrity.events).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {screening.length > 0 && (
        <Section title="Screening">
          <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
            {screening.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-stone-500">{prettyKey(k)}</dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
            {Object.entries(care).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-stone-500">{prettyKey(k)}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}

      {!!scorecard.clinical_areas?.length && (
        <Section title="Clinical areas">
          <ul className="space-y-2">
            {scorecard.clinical_areas.map((a) => (
              <li key={a.id}>
                <span className="font-medium">{a.title}</span>{" "}
                <span className={OUTCOME_STYLE[a.outcome] ?? ""}>{a.outcome}</span>
                {a.red_flags.length > 0 && <span className="text-red-700"> - {a.red_flags.join("; ")}</span>}
                {a.missing.length > 0 && <p className="text-xs text-stone-500">Missed: {a.missing.join("; ")}</p>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.tier_evidence?.length && (
        <Section title="Evidence">
          <ul className="space-y-1">
            {scorecard.tier_evidence.map((e, i) => (
              <li key={i}>
                <span className="text-stone-500">{e.area}: </span>
                {e.point}
                <blockquote className="border-l-2 border-stone-300 pl-2 text-stone-600">
                  "{e.quote}" {!e.verified && <span className="text-xs text-amber-700">(not found verbatim in transcript)</span>}
                </blockquote>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.strengths?.length && (
        <Section title="Strengths">
          <ul className="list-disc pl-5">
            {scorecard.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.gaps?.length && (
        <Section title="Gaps">
          <ul className="list-disc pl-5">
            {scorecard.gaps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
