import type { ReactNode } from "react";
import type { V2Scorecard } from "../types";
import { summarizeIntegrityEvents } from "../../lib/integrity";

const TIER_STYLE: Record<string, string> = {
  tier_1: "bg-emerald-100 text-emerald-900",
  tier_2: "bg-sky-100 text-sky-900",
  tier_3: "bg-amber-100 text-amber-900",
  not_eligible: "bg-red-100 text-red-900",
  needs_review: "bg-stone-200 text-stone-800",
};

const OUTCOME_LABEL: Record<string, string> = {
  strong: "Strong",
  adequate: "Adequate",
  weak: "Needs improvement",
  unsafe: "Unsafe / concerning",
  unknown: "Not assessed",
};

const OUTCOME_STYLE: Record<string, string> = {
  strong: "text-emerald-700",
  adequate: "text-sky-700",
  weak: "text-amber-700",
  unsafe: "text-red-700",
  unknown: "text-stone-500",
};

const STANCE_LABEL: Record<string, string> = {
  willing: "Willing",
  comfortable: "Comfortable",
  unwilling: "Not willing",
  refused: "Refused",
  hesitant: "Hesitant",
  unknown: "Not discussed",
};

const LABELS: Record<string, string> = {
  city: "City applied for",
  phone: "Phone number",
  qualification: "Qualification",
  qualification_year: "Year of passing",
  height_cm: "Height",
  weight_kg: "Weight",
  experience_years: "Years of experience",
  experience_settings: "Work settings",
  experience_level: "Experience level",
  diaper_care: "Diaper / incontinence care",
  bed_bath: "Bed bath & hygiene",
  bedpan: "Bedpan / toileting help",
  turning: "Turning & lifting patients",
  fresher: "Fresher",
  experienced: "Experienced",
  icu: "ICU experience",
  ward: "Ward experience",
};

const FLAG_CLEAN: Record<string, string> = {
  gate_failed: "Did not accept a required care duty",
  incomplete_silence: "Ended early due to no response",
  withdrew: "Candidate withdrew",
  time: "Time limit reached",
};

function prettyKey(k: string): string {
  return LABELS[k] ?? k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function prettyValue(key: string, value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key === "height_cm") return `${value} cm`;
    if (key === "weight_kg") return `${value} kg`;
    return String(value);
  }
  const s = String(value);
  if (STANCE_LABEL[s]) return STANCE_LABEL[s];
  if (LABELS[s]) return LABELS[s];
  // "willing (after 1 explanation(s))" → human phrasing
  const after = s.match(/^(\w+)\s*\(after\s+(\d+)\s+explanation/);
  if (after) {
    const stance = STANCE_LABEL[after[1]!] ?? prettyKey(after[1]!);
    return `${stance} (after ${after[2]} explanation${after[2] === "1" ? "" : "s"})`;
  }
  return s;
}

function prettyFlag(f: string): string {
  return FLAG_CLEAN[f] ?? f.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function prettyOutcome(o: string): string {
  return OUTCOME_LABEL[o] ?? prettyKey(o);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-stone-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
      <div className="mt-2 text-sm text-stone-700">{children}</div>
    </section>
  );
}

export default function ScorecardView({ scorecard }: { scorecard: V2Scorecard }) {
  const screening = Object.entries(scorecard.screening ?? {}).filter(([k]) => k !== "care_duties");
  const care = (scorecard.screening?.care_duties ?? {}) as Record<string, string>;
  const tierLabel = scorecard.tier_name ?? (scorecard.tier ? prettyKey(scorecard.tier) : null);

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-stone-200 bg-stone-50 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Result</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {tierLabel && (
            <span
              className={`rounded-full px-3 py-1 text-sm font-medium ${TIER_STYLE[scorecard.tier ?? ""] ?? "bg-stone-200 text-stone-800"}`}
            >
              {tierLabel}
            </span>
          )}
          {scorecard.overall_score != null && (
            <span className="text-sm text-stone-700">Score {scorecard.overall_score} / 10</span>
          )}
        </div>
        {(scorecard.tier_reasoning || scorecard.recommendation) && (
          <p className="mt-3 text-sm leading-relaxed text-stone-700">
            {scorecard.tier_reasoning ?? scorecard.recommendation}
          </p>
        )}
      </section>

      {!!scorecard.flags?.length && (
        <Section title="Notes for recruiter">
          <ul className="list-disc space-y-1 pl-5">
            {scorecard.flags.map((f) => (
              <li key={f}>{prettyFlag(f)}</li>
            ))}
          </ul>
        </Section>
      )}

      {(screening.length > 0 || Object.keys(care).length > 0) && (
        <Section title="Screening details">
          <dl className="space-y-2">
            {screening.map(([k, v]) => (
              <div key={k} className="flex gap-3 border-b border-stone-100 pb-2 last:border-0">
                <dt className="w-40 shrink-0 text-stone-500">{prettyKey(k)}</dt>
                <dd className="font-medium text-stone-900">{prettyValue(k, v)}</dd>
              </div>
            ))}
            {Object.entries(care).map(([k, v]) => (
              <div key={k} className="flex gap-3 border-b border-stone-100 pb-2 last:border-0">
                <dt className="w-40 shrink-0 text-stone-500">{prettyKey(k)}</dt>
                <dd className="font-medium text-stone-900">{prettyValue(k, v)}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}

      {!!scorecard.clinical_areas?.length && (
        <Section title="Clinical assessment">
          <ul className="space-y-3">
            {scorecard.clinical_areas.map((a) => (
              <li key={a.id} className="rounded-lg bg-stone-50 px-3 py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-stone-900">{a.title}</span>
                  <span className={`text-sm font-medium ${OUTCOME_STYLE[a.outcome] ?? ""}`}>
                    {prettyOutcome(a.outcome)}
                  </span>
                </div>
                {a.red_flags.length > 0 && (
                  <p className="mt-1 text-sm text-red-700">Concerns: {a.red_flags.join("; ")}</p>
                )}
                {a.missing.length > 0 && (
                  <p className="mt-1 text-xs text-stone-500">Not covered: {a.missing.join("; ")}</p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.strengths?.length && (
        <Section title="Strengths">
          <ul className="list-disc space-y-1 pl-5">
            {scorecard.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.gaps?.length && (
        <Section title="Gaps">
          <ul className="list-disc space-y-1 pl-5">
            {scorecard.gaps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Section>
      )}

      {!!scorecard.tier_evidence?.filter((e) => e.verified !== false).length && (
        <Section title="Evidence from the call">
          <ul className="space-y-3">
            {scorecard.tier_evidence
              .filter((e) => e.verified !== false)
              .map((e, i) => (
              <li key={i}>
                <p className="text-sm">
                  <span className="font-medium text-stone-800">{e.area}</span>
                  <span className="text-stone-600"> — {e.point}</span>
                </p>
                <blockquote className="mt-1 border-l-2 border-stone-300 pl-3 text-sm text-stone-600 italic">
                  “{e.quote}”
                </blockquote>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {scorecard.integrity && (
        <Section title="Camera checks">
          {!scorecard.integrity.available ? (
            <p className="text-stone-600">Camera checks were not available for this session.</p>
          ) : summarizeIntegrityEvents(scorecard.integrity.events).length === 0 ? (
            <p className="text-stone-600">No integrity concerns detected.</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              {summarizeIntegrityEvents(scorecard.integrity.events).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </Section>
      )}
    </div>
  );
}
