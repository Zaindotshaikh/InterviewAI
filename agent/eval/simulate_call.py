"""Text-mode run of a whole interview: scripted candidate lines -> live analyst -> flow -> next directive.

Run from agent/:  python -m eval.simulate_call [happy|refuses|noisy]
Needs OPENAI_API_KEY. No audio, no LiveKit; it shows what the interviewer would be told to do on each turn.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

from config import get_settings  # noqa: E402
from interview.analysis import TurnAnalyzer  # noqa: E402
from interview.blueprint import Blueprint  # noqa: E402
from interview.director import Director  # noqa: E402
from interview.flow import InterviewFlow  # noqa: E402
from interview.flow_state import FlowState  # noqa: E402
from interview.plan import InterviewPlan  # noqa: E402

BLUEPRINT = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"

SCRIPTS: dict[str, list[str]] = {
    "happy": [
        "Haan ji, main Pune ke liye apply kar rahi hoon",
        "mera number hai nine eight seven six five four three two one zero",
        "haan sahi hai",
        "GNM kiya hai, 2019 mein pass hua",
        "height paanch foot chaar inch hai aur weight pachpan kilo",
        "teen saal ICU mein kaam kiya hai Apollo mein, ventilator patients dekhe hain",
        "haan bathing aur bedpan sab kar leti hoon, diaper change bhi koi problem nahi",
        "haan lifting aur turning bhi karti hoon, ICU mein roz karte the",
        "pehle patient ka consciousness check karungi, phir BP pulse temperature SpO2 lungi aur record karungi",
        "normal BP 120/80 hota hai, pulse 60 se 100, SpO2 95 se upar",
        "agar BP bahut low aaye to patient ko leta dungi, legs upar, doctor ko inform karungi",
        "medicine dene se pehle five rights check karti hoon, patient name, drug, dose, route, time",
        "agar galat dose de diya to turant doctor ko batati hoon aur incident report bharti hoon",
        "pata nahi, mujhe iske baare mein zyada nahi pata",
        "haan ek question hai, salary kitni milegi?",
        "nahi, bas itna hi",
    ],
    "refuses": [
        "Chennai ke liye apply kiya hai",
        "9 8 7 6 5 4 3 2 1 0",
        "haan",
        "B.Sc nursing 2021",
        "five two, fifty kilo",
        "do saal ward mein",
        "diaper change nahi karungi, wo nursing ka kaam nahi hai",
        "nahi, mujhe accha nahi lagta, main nahi karungi",
        "nahi, bilkul nahi",
    ],
    "noisy": [
        "",
        "ghh... krr... hmm",
        "ghh krrr",
        "Mumbai",
    ],
}


async def main(name: str) -> None:
    settings = get_settings()
    bp = Blueprint.from_api(json.loads(BLUEPRINT.read_text(encoding="utf-8")))
    plan = InterviewPlan(
        interview_id="sim", language="hi-IN", stt_mode="codemix", target_minutes=17, company_name="Kreeda Labs",
        interviewer_name="Aven", role_title="Staff Nurse", criteria=[], keyterms=[], glossary_hints=[], steps=[],
        system_prompt="", candidate_name="Priya",
    )
    flow = InterviewFlow(plan, bp, FlowState(language="hi-IN"))
    analyzer = TurnAnalyzer(
        bp,
        api_key=settings.openai_api_key,
        model=settings.director_model,
        clinical_model=settings.clinical_director_model,
        timeout_s=settings.director_timeout_seconds,
    )
    director = Director(flow, analyzer)
    await analyzer.prewarm()

    move = flow.opening()
    print(f"[{flow.stage}] AGENT <{move.kind}>: {move.directive.splitlines()[0][:230]}\n")
    for line in SCRIPTS[name]:
        if flow.done:
            break
        print(f"CANDIDATE: {line!r}")
        move = await director.decide(line)
        director.note_user(line)
        first = move.directive.splitlines()[0]
        print(f"[{flow.stage}] AGENT <{move.kind}> ({analyzer.last_latency_ms:.0f}ms): {first[:230]}\n")
        if move.completed:
            break

    st = flow.state
    print("---- final state ----")
    print("outcome:", st.outcome, "| stage:", st.stage, "| turns:", st.turns)
    print("slots:", {k: v.value for k, v in st.slots.items() if v.status in ("captured", "confirmed")})
    print("care:", {k: (v.stance, v.persuasions) for k, v in st.care.items()})
    print("areas:", {k: (v.outcome, v.level) for k, v in st.areas.items() if v.status != "pending"})
    print("claims:", st.claims[:5], "| contradictions:", len(st.contradictions))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "happy"))
