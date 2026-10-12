import json
import pathlib

root = pathlib.Path(r"c:\Users\dell\Desktop\Zain\InterviewAI\server\data")
files = sorted(root.glob("*.v2.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
for p in files:
    d = json.loads(p.read_text(encoding="utf-8"))
    interview = d.get("interview") or {}
    extras = d.get("extras") or {}
    ctrl = extras.get("controller") or {}
    flow = (ctrl.get("flow") if isinstance(ctrl, dict) else None) or {}
    if not flow and isinstance(extras.get("controller"), dict):
        # sometimes flow nested differently
        flow = extras["controller"].get("flow") or {}
    # also check top-level flow under extras
    if not flow:
        flow = extras.get("flow") or {}
    transcript = interview.get("transcript") or []
    events = extras.get("events") or []
    care = flow.get("care") or {}
    keys = ("diaper", "डायपर", "incontinence", "care", "clinical", "bed bath", "hygiene")
    diaper_hits = sum(
        1
        for t in transcript
        if any(x in (t.get("text") or "").lower() for x in ("diaper", "डायपर", "incontinence"))
    )
    ev = [e.get("type") for e in events if any(k in (e.get("type") or "") for k in ("care", "gate", "stage"))]
    print("====", p.name, "====")
    print(
        "name=",
        interview.get("candidateName"),
        "created=",
        interview.get("createdAt"),
        "turns=",
        len(transcript),
        "mtime=",
        p.stat().st_mtime,
    )
    print(
        "stage=",
        flow.get("stage"),
        "care_intro=",
        flow.get("care_intro_done"),
        "gate=",
        flow.get("gate_failed"),
    )
    for k, v in care.items():
        print(
            f"  {k}: stance={v.get('stance')} persuasions={v.get('persuasions')} asked={v.get('asked')}"
        )
    print("diaper_mentions=", diaper_hits)
    print("events=", ", ".join(ev[-25:]))
    for t in transcript:
        txt = t.get("text") or ""
        low = txt.lower()
        if any(x in low for x in keys) or "डायपर" in txt:
            print(t.get("role"), ":", txt[:180])
    print()
