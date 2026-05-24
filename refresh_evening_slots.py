#!/usr/bin/env python3
"""Akşam slotlarını şu anki zamana göre yenile — 3 dakika sonradan başlayarak."""
import json
import sys
import datetime as dt
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Istanbul")
    now = dt.datetime.now(tz=tz)
except Exception:
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)

ROOT = Path(__file__).resolve().parent
SCHEDULE_PATH = ROOT / "schedules" / "2026-05-21_smu_schedule.json"

# 3 dakika sonradan başla, 15 dk aralıkla, 6 slot
def build_times(start_offset_min=3, interval_min=15, count=6):
    base = now + dt.timedelta(minutes=start_offset_min)
    # dakikayı yuvarla (temiz görünsün)
    base = base.replace(second=0, microsecond=0)
    return [
        (base + dt.timedelta(minutes=i * interval_min)).strftime("2026-05-21 %H:%M")
        for i in range(count)
    ]

EVENING_TIMES = build_times()
print(f"Simdi (Istanbul): {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Yeni slot saatleri: {EVENING_TIMES}")

data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
slots = data["slots"]

# PosterLoop slot 24-29 (6 adet) guncelle
poster_slots = sorted([s for s in slots if s["channel"] == "poster_loop_cinema"], key=lambda s: s["slot"])
targets = [s for s in poster_slots if s["slot"] >= 24][:6]

for i, slot in enumerate(targets):
    slot["publishAtLocal"] = EVENING_TIMES[i]
    print(f"  Slot {slot['slot']} -> {EVENING_TIMES[i]}")

# Kaydet
tmp = SCHEDULE_PATH.with_name(".schedule_tmp.json")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(SCHEDULE_PATH)
print("Schedule kaydedildi.")
