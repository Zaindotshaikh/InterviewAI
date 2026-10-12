"""Live check of the turn analyst on realistic code-mixed utterances.

Run from agent/:  python -m eval.probe_analyst [model ...]
Prints what the analyst extracted/graded and how long each call took. Needs OPENAI_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

from config import get_settings  # noqa: E402
from interview.analysis import TurnAnalysis, TurnAnalyzer, heuristic_analysis  # noqa: E402
from interview.blueprint import Blueprint  # noqa: E402
from interview.flow import InterviewFlow  # noqa: E402
from interview.flow_state import FlowState  # noqa: E402
from interview.plan import InterviewPlan  # noqa: E402

BLUEPRINT = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"


def plan() -> InterviewPlan:
    return InterviewPlan(
        interview_id="probe", language="hi-IN", stt_mode="codemix", target_minutes=20, company_name="Kreeda Labs",
        interviewer_name="Aven", role_title="Staff Nurse", criteria=[], keyterms=[], glossary_hints=[], steps=[],
        system_prompt="", candidate_name="Priya", resume_text="Staff nurse, 3 years ICU at Apollo Hospital Pune.",
    )


def flow_in(stage: str, **setup) -> InterviewFlow:
    bp = Blueprint.from_api(json.loads(BLUEPRINT.read_text(encoding="utf-8")))
    f = InterviewFlow(plan(), bp, FlowState(language="hi-IN"))
    f.state.stage = stage
    if stage == "clinical":
        f.state.experience_level = "experienced"
        f.state.area_order = [setup.get("area", "emergency_response")]
        f.state.current_area = f.state.area_order[0]
        prog = f.state.area_progress(f.state.current_area)
        prog.status, prog.level = "active", setup.get("level", 1)
        f.state.focus = {"type": "clinical", "area": f.state.current_area, "level": prog.level}
    elif setup.get("focus"):
        f.state.focus = setup["focus"]
    for k, v in (setup.get("claims") or {}).items():
        f.state.claims.append(v)
    return f


CASES = [
    ("screening: city+phone in Hinglish, digits spoken as words", "screening", {"focus": {"type": "slots", "ids": ["city"]}},
     "Which city are you applying for?", "haan ji main Pune mein apply kar rahi hoon, mera number nine eight seven six five four three two one zero hai"),
    ("screening: body measurements in feet", "screening", {"focus": {"type": "slots", "ids": ["height_cm", "weight_kg"]}},
     "Tell me your height and weight.", "meri height paanch foot do inch hai aur weight lagbhag pachpan kilo"),
    ("screening: phone read-back confirmed", "screening", {"focus": {"type": "confirm", "field": "phone", "ids": ["phone"]}},
     "I heard 98765, 43210. Is that correct?", "haan haan bilkul sahi hai"),
    ("care: flat refusal of diaper", "screening", {"focus": {"type": "care", "items": ["diaper_care", "hygiene_bathing"]}},
     "How comfortable are you with bed baths and changing diapers?", "sister bed bath toh theek hai par yeh diaper wagairah mujhse nahi hoga, main nahi karungi"),
    ("care: willing after explanation (Tanglish)", "screening", {"focus": {"type": "care", "items": ["diaper_care"]}},
     "It's a routine part of nursing. Can you do it?", "ohh okay madam, apdina seri, naan try pannuren, training kudutha pannuven"),
    ("clinical emergency L1: partial, Hinglish", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "sabse pehle toh main doctor ko bulati hoon aur patient ka breathing check karti hoon"),
    ("clinical emergency L1: unsafe", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "hum CPR nahi karte, doctor ke aane ka wait karte hain, humara kaam nahi hai woh"),
    ("clinical emergency L1: strong, Tanglish", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "first naan scene safe-a nu paapen, patient-a tap panni kuppiduven, response illana help ku code blue kuppiduven, pulse breathing check panni ten second-kulla, illana CPR start pannuven, AED kondu vara solluven"),
    ("clinical: I don't know", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "madam yeh mujhe nahi pata, kabhi kiya nahi"),
    ("clinical: asks to repeat", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "sorry madam, aap phir se bol sakti hain? samajh nahi aaya"),
    ("noise: garbled transcript", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "ka ki the in ... hospital ... uh"),
    ("contradiction vs earlier claim", "clinical", {"claims": {"a": "worked 3 years in ICU at Apollo Pune"}},
     "How do you suction a ventilated patient?", "madam actually mai ICU mein kabhi kaam hi nahi kiya, sirf ward mein tha, ventilator maine dekha nahi"),
    ("nervous", "clinical", {},
     "You find a patient on the floor not responding. What do you do first?", "sorry madam mujhe bahut dar lag raha hai, nervous hoon... main doctor ko bulaungi"),
]


async def main(models: list[str]) -> None:
    s = get_settings()
    bp = Blueprint.from_api(json.loads(BLUEPRINT.read_text(encoding="utf-8")))
    for model in models:
        print(f"\n===================== model: {model} =====================")
        analyzer = TurnAnalyzer(bp, api_key=s.openai_api_key, model=model, timeout_s=15)
        for title, stage, setup, last_q, utterance in CASES:
            flow = flow_in(stage, **setup)
            payload = flow.analysis_payload(utterance, last_q, [])
            t0 = time.perf_counter()
            fb = heuristic_analysis(utterance)
            a: TurnAnalysis = await analyzer.analyze(payload, clinical=stage == "clinical", fallback=fb)
            ms = (time.perf_counter() - t0) * 1000
            bits = [f"{a.source} {ms:.0f}ms", f"clarity={a.intelligibility}", f"intent={a.intent}"]
            if a.nervous:
                bits.append("NERVOUS")
            if a.slot_updates:
                bits.append("slots=" + ", ".join(f"{u.field}={u.value}({u.confidence:.1f})" for u in a.slot_updates))
            if a.confirmation != "none":
                bits.append(f"confirm={a.confirmation}")
            if a.care_updates:
                bits.append("care=" + ", ".join(f"{u.item}:{u.stance}" for u in a.care_updates))
            if a.clinical:
                c = a.clinical
                bits.append(f"grade={c.quality} covered={len(c.covered)} missing={len(c.missing)} flags={c.red_flags}")
            if a.contradictions:
                bits.append(f"CONTRADICTION={a.contradictions[0]['note'][:60]}")
            print(f"\n- {title}\n    {utterance[:90]}\n    -> " + " | ".join(bits))
        print(f"\nfailures: {analyzer.failures}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["gpt-4o-mini", "gpt-4o"]))
