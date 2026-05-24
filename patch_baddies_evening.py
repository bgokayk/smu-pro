#!/usr/bin/env python3
"""BaddiesTR slot 1-6'yi akşam saatlerine taşır (PosterLoop ile eş zamanlı)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEDULE_PATH = ROOT / "schedules" / "2026-05-21_smu_schedule.json"

EVENING_TIMES = [
    "2026-05-21 22:44",
    "2026-05-21 22:59",
    "2026-05-21 23:14",
    "2026-05-21 23:29",
    "2026-05-21 23:44",
    "2026-05-21 23:59",
]

data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
slots = data["slots"]

baddies_slots = sorted(
    [s for s in slots if s["channel"] == "sahnebaddiestr" and s.get("file")],
    key=lambda s: s["slot"]
)

print(f"Baddies filled slots: {len(baddies_slots)}")
targets = baddies_slots[:6]

for i, slot in enumerate(targets):
    old_time = slot["publishAtLocal"]
    slot["publishAtLocal"] = EVENING_TIMES[i]
    print(f"  Slot {slot['slot']} ({slot.get('id','')[:20]}): {old_time} -> {EVENING_TIMES[i]}")

tmp = SCHEDULE_PATH.with_name(".sched_baddies_tmp.json")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(SCHEDULE_PATH)
print("Schedule saved.")
