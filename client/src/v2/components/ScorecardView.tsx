import type { ReactNode } from "react";
import type { V2Scorecard } from "../types";
import { summarizeIntegrityEvents } from "../../lib/integrity";

const TIER_STYLE: Record<string, string> = {
  tier_1: "bg-emerald-600 text-white",
  tier_2: "bg-sky-700 text-white",
  tier_3: "bg-amber-600 text-white",
  not_eligible: "bg-red-700 text-white",
  needs_review: "bg-stone-700 text-white",
};

const TIER_BAR: Record<string, string> = {
  tier_1: "bg-emerald-500",
  tier_2: "bg-sky-500",
  tier_3: "bg-amber-500",
  not_eligible: "bg-red-500",
  needs_review: "bg-stone-400",
};

const OUTCOME_LABEL: Record<string, string> = {
  strong: "Strong",
  adequate: "Adequate",
  weak: "Needs support",
  unsafe: "Safety concern",
  unknown: "Not assessed",
};

const OUTCOME_STYLE: Record<string, string> = {
  strong: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  adequate: "bg-sky-50 text-sky-800 ring-sky-200",
  weak: "bg-amber-50 text-amber-800 ring-amber-200",
  unsafe: "bg-red-50 text-red-800 ring-red-200",
  unknown: "bg-stone-100 text-stone-600 ring-stone-200",
};

const CALL_OUTCOME: Record<string, string> = {
  completed: "Interview completed",
  screened_out: "Did not proceed — essential duty",
  time: "Stopped at the time limit",
  withdrew: "Candidate withdrew",
  incomplete_silence: "Ended — no response",
  incomplete_disconnect: "Ended — call dropped",
};

const STANCE_LABEL: Record<string, string> = {
  willing: "Willing",
  comfortable: "Comfortable",
  willing_with_training: "Willing, with training",
  unwilling: "Not willing",
  refused: "Not willing",
  refuses: "Not willing",
  hesitant: "Hesitant",
  unknown: "Not discussed",
};

const STANCE_STYLE: Record<string, string> = {
  willing: "bg-emerald-50 text-emerald-800",
  comfortable: "bg-emerald-50 text-emerald-800",
  willing_with_training: "bg-sky-50 text-sky-800",
  unwilling: "bg-red-50 text-red-800",
  refused: "bg-red-50 text-red-800",
  refuses: "bg-red-50 text-red-800",
  hesitant: "bg-amber-50 text-amber-900",
  unknown: "bg-stone-100 text-stone-600",
};

const LABELS: Record<string, string> = {
  city: "City applied for",
  phone: "Mobile number",
  qualification: "Qualification",
  qualification_year: "Year of passing",
  height_cm: "Height",
  weight_kg: "Weight",
  experience_years: "Years of experience",
  experience_settings: "Where they have worked",
  experience_level: "Experience level",
  diaper_care: "Diaper / incontinence care",
  bed_bath: "Bed bath and hygiene",
  bedpan: "Bedpan / toileting help",
  turning: "Turning and lifting",
  fresher: "Fresher",
  experienced: "Experienced",
  junior: "Under 3 years",
  icu: "ICU experience",
  ward: "Ward experience",
};

const GENDER_LABEL: Record<string, string> = {
  female: "Female",
  male: "Male",
  unspecified: "Not specified",
};

const LANG_LABEL: Record<string, string> = {
  "en-IN": "English",
  "hi-IN": "Hindi",
  "mr-IN": "Marathi",
  "gu-IN": "Gujarati",
  "ta-IN": "Tamil",
  "te-IN": "Telugu",
  "kn-IN": "Kannada",
  "ml-IN": "Malayalam",
  "bn-IN": "Bengali",
  "pa-IN": "Punjabi",
  "od-IN": "Odia",
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
  if (value == null || value === "" || value === "not provided") return "Not captured";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key === "height_cm") return `${value} cm`;
    if (key === "weight_kg") return `${value} kg`;
    return String(value);
  }
  const s = String(value);
  if (key === "phone") {
    const digits = s.replace(/\D/g, "");
    if (digits.length === 10) return `${digits.slice(0, 5)} ${digits.slice(5)}`;
  }
  if (STANCE_LABEL[s]) return STANCE_LABEL[s];
  if (LABELS[s]) return LABELS[s];
  const after = s.match(/^(\w+)\s*\(after\s+(\d+)\s+explanation/);
  if (after) {
    const stance = STANCE_LABEL[after[1]!] ?? prettyKey(after[1]!);
    return `${stance}, after ${after[2]} explanation${after[2] === "1" ? "" : "s"}`;
  }
  return s;
}

function stanceKey(value: string): string {
  const word = value.split(" ")[0] ?? value;
  return STANCE_LABEL[word] ? word : "unknown";
}

function prettyFlag(f: string): string {
  return FLAG_CLEAN[f] ?? f.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function prettyOutcome(o: string): string {
  return OUTCOME_LABEL[o] ?? prettyKey(o);
}

function Card({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
        {hint ? <p className="text-xs text-stone-400">{hint}</p> : null}
      </div>
      <div className="mt-3 text-sm text-stone-700">{children}</div>
    </section>
  );
}

export default function ScorecardView({ scorecard }: { scorecard: V2Scorecard }) {
  const screening = Object.entries(scorecard.screening ?? {}).filter(([k]) => k !== "care_duties");
  const captured = screening.filter(([, v]) => v != null && v !== "" && v !== "not provided");
  const missing = screening.filter(([, v]) => v == null || v === "" || v === "not provided");
  const care = (scorecard.screening?.care_duties ?? {}) as Record<string, string>;
  const tierLabel = scorecard.tier_name ?? (scorecard.tier ? prettyKey(scorecard.tier) : "Needs review");
  const tierKey = scorecard.tier ?? "needs_review";
  const reasoning = (scorecard.tier_reasoning ?? scorecard.recommendation ?? "").trim();
  const gender = scorecard.profile?.gender;
  const language = scorecard.language ? LANG_LABEL[scorecard.language] ?? scorecard.language : null;
  const callOutcome = scorecard.outcome ? CALL_OUTCOME[scorecard.outcome] ?? prettyKey(scorecard.outcome) : null;
  const areas = (scorecard.clinical_areas ?? []).filter(
    (a) =>
      a.outcome !== "unknown" ||
      a.red_flags.length > 0 ||
      a.covered.length > 0 ||
      a.evidence.some((e) => e.quote || e.summary),
  );
  const evidence = (scorecard.tier_evidence ?? []).filter((e) => e.verified !== false && e.quote?.trim());
  const openContradictions = (scorecard.contradictions ?? []).filter((c) => !c.resolved);
  const resolvedContradictions = (scorecard.contradictions ?? []).filter((c) => c.resolved);

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
        <div className={`h-1.5 ${TIER_BAR[tierKey] ?? "bg-stone-400"}`} />
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Hiring decision</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ${TIER_STYLE[tierKey] ?? TIER_STYLE.needs_review}`}>
                {tierLabel}
              </span>
              {callOutcome && (
                <span className="rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
                  {callOutcome}
                </span>
              )}
            </div>
            {reasoning && <p className="mt-3 text-sm leading-relaxed text-stone-700">{reasoning}</p>}
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-stone-500">
              {gender && <span>Gender on form: {GENDER_LABEL[gender] ?? gender}</span>}
              {gender && language ? <span aria-hidden>·</span> : null}
              {language && <span>Spoken in {language}</span>}
            </div>
            {!!scorecard.flags?.length && (
              <ul className="mt-3 flex flex-wrap gap-2">
                {scorecard.flags.map((f) => (
                  <li key={f} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900">
                    {prettyFlag(f)}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-3 rounded-2xl bg-stone-50 px-4 py-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Score</p>
              {scorecard.overall_score != null ? (
                <p className="text-3xl font-semibold tabular-nums text-stone-900">
                  {scorecard.overall_score}
                  <span className="text-base font-medium text-stone-400"> / 10</span>
                </p>
              ) : (
                <p className="text-sm font-medium text-stone-700">Withheld for review</p>
              )}
            </div>
          </div>
        </div>
      </section>

      {(captured.length > 0 || missing.length > 0 || Object.keys(care).length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="What we captured" hint="From this interview">
            {captured.length > 0 ? (
              <dl className="grid gap-3 sm:grid-cols-2">
                {captured.map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-stone-500">{prettyKey(k)}</dt>
                    <dd className="mt-0.5 font-medium text-stone-900">{prettyValue(k, v)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-stone-500">No screening facts were confirmed on this call.</p>
            )}
            {missing.length > 0 && (
              <p className="mt-3 text-xs leading-relaxed text-stone-500">
                Not captured: {missing.map(([k]) => prettyKey(k).toLowerCase()).join(", ")}
              </p>
            )}
          </Card>

          <Card title="Essential care" hint="Role requirement">
            {Object.keys(care).length > 0 ? (
              <ul className="space-y-2">
                {Object.entries(care).map(([k, v]) => {
                  const key = stanceKey(String(v));
                  return (
                    <li key={k} className="flex items-center justify-between gap-3">
                      <span className="text-stone-800">{prettyKey(k)}</span>
                      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STANCE_STYLE[key] ?? STANCE_STYLE.unknown}`}>
                        {prettyValue(k, v)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-stone-500">Care duties were not discussed.</p>
            )}
          </Card>
        </div>
      )}

      <Card title="Clinical judgement" hint={areas.length ? `${areas.length} area${areas.length === 1 ? "" : "s"} discussed` : undefined}>
        {areas.length > 0 ? (
          <ul className="grid gap-3 sm:grid-cols-2">
            {areas.map((a) => (
              <li key={a.id} className="rounded-xl bg-stone-50 px-3 py-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium text-stone-900">{a.title}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${OUTCOME_STYLE[a.outcome] ?? OUTCOME_STYLE.unknown}`}>
                    {prettyOutcome(a.outcome)}
                  </span>
                </div>
                {a.red_flags.length > 0 && (
                  <p className="mt-2 text-sm text-red-700">Concern: {a.red_flags.join("; ")}</p>
                )}
                {a.evidence.some((e) => e.summary) && (
                  <p className="mt-2 text-sm text-stone-600">
                    {a.evidence.map((e) => e.summary).filter(Boolean).slice(0, 1).join(" ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-stone-500">The clinical round was not reached on this call.</p>
        )}
      </Card>

      {(!!scorecard.strengths?.length || !!scorecard.gaps?.length) && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="Strengths">
            {scorecard.strengths?.length ? (
              <ul className="space-y-2">
                {scorecard.strengths.map((s) => (
                  <li key={s} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-stone-500">None recorded.</p>
            )}
          </Card>
          <Card title="Gaps to probe">
            {scorecard.gaps?.length ? (
              <ul className="space-y-2">
                {scorecard.gaps.map((s) => (
                  <li key={s} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-stone-500">None recorded.</p>
            )}
          </Card>
        </div>
      )}

      {evidence.length > 0 && (
        <Card title="Evidence from the call" hint="Quotes checked against the transcript">
          <ul className="space-y-3">
            {evidence.map((e, i) => (
              <li key={i} className="rounded-xl bg-stone-50 px-3 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-stone-500">{e.area}</p>
                <p className="mt-1 text-sm text-stone-800">{e.point}</p>
                <blockquote className="mt-2 border-l-2 border-stone-300 pl-3 text-sm italic text-stone-600">
                  “{e.quote}”
                </blockquote>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {(openContradictions.length > 0 || resolvedContradictions.length > 0) && (
        <Card title="Consistency">
          <ul className="space-y-3">
            {openContradictions.map((c, i) => (
              <li key={`open-${i}`}>
                <p className="text-xs font-medium text-amber-800">Unresolved</p>
                <p className="mt-1 text-stone-800">
                  {[c.claim_a, c.claim_b].filter(Boolean).join(" · ") || c.note || "Statements did not match."}
                </p>
              </li>
            ))}
            {resolvedContradictions.map((c, i) => (
              <li key={`done-${i}`}>
                <p className="text-xs font-medium text-stone-500">Resolved</p>
                <p className="mt-1 text-stone-700">{c.resolution || c.note || "Cleared on the call."}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {scorecard.integrity && (
        <Card title="Camera check">
          {!scorecard.integrity.available ? (
            <p className="text-stone-600">Camera checks were not available for this session.</p>
          ) : summarizeIntegrityEvents(scorecard.integrity.events).length === 0 ? (
            <p className="text-stone-600">No integrity concerns detected.</p>
          ) : (
            <ul className="space-y-1">
              {summarizeIntegrityEvents(scorecard.integrity.events).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}
