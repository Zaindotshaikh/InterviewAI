import { useEffect, useState } from "react";
import type { V2LanguageOption } from "../types";

type Props = {
  value: string;
  onChange: (code: string) => void;
};

const FALLBACK: V2LanguageOption[] = [
  { code: "en-IN", label: "English (India)", sttMode: "transcribe", ttsSpeaker: "ishita" },
  { code: "hi-IN", label: "Hindi / Hinglish", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "ta-IN", label: "Tamil / Tanglish", sttMode: "codemix", ttsSpeaker: "ishita" },
  { code: "te-IN", label: "Telugu", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "kn-IN", label: "Kannada", sttMode: "codemix", ttsSpeaker: "ishita" },
  { code: "ml-IN", label: "Malayalam", sttMode: "codemix", ttsSpeaker: "pooja" },
];

export default function LanguagePicker({ value, onChange }: Props) {
  const [langs, setLangs] = useState<V2LanguageOption[]>(FALLBACK);

  useEffect(() => {
    void fetch("/api/v2/interview/languages")
      .then((r) => r.json())
      .then((data: { languages?: V2LanguageOption[] }) => {
        if (Array.isArray(data.languages) && data.languages.length) setLangs(data.languages);
      })
      .catch(() => undefined);
  }, []);

  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-stone-700">Interview language</span>
      <select
        className="rounded-lg border border-stone-300 bg-white px-3 py-2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {langs.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
