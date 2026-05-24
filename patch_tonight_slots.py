#!/usr/bin/env python3
"""
Bu script 2026-05-21 schedule'ındaki PosterLoop slot 24-30'u
22:33-23:55 arası akşam saatlerine taşır ve daemon'ı hemen başlatabilmek için
hazır hale getirir. BaddiesTR slotlarını da ekler (eğer queue hazırsa).
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
SCHEDULE_PATH = ROOT / "schedules" / "2026-05-21_smu_schedule.json"

# Akşam yayın saatleri (22:33'ten başla, ~15 dk aralıkla)
EVENING_TIMES = [
    "2026-05-21 22:33",
    "2026-05-21 22:48",
    "2026-05-21 23:05",
    "2026-05-21 23:25",
    "2026-05-21 23:40",
    "2026-05-21 23:55",
]

def main():
    data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    slots = data["slots"]

    # PosterLoop slot 24-30 → akşam saatlerine taşı
    poster_slots = [s for s in slots if s["channel"] == "poster_loop_cinema"]
    # Slot numarasına göre sırala
    poster_slots.sort(key=lambda s: s["slot"])

    # Slot 24-29 (indices 23-28 in sorted list) → 6 akşam saati
    evening_candidates = [s for s in poster_slots if s["slot"] >= 24][:6]

    print(f"Taşınacak poster slot sayısı: {len(evening_candidates)}")
    for i, slot in enumerate(evening_candidates):
        old_time = slot["publishAtLocal"]
        slot["publishAtLocal"] = EVENING_TIMES[i]
        print(f"  Slot {slot['slot']} ({slot.get('queueItemId','')}): {old_time} -> {EVENING_TIMES[i]}")

    # Baddies queue var mı?
    baddies_queue_path = Path("C:/Users/User/.codex/sahne-baddies-auto/automation/baddies_queue_batch001.json")
    if baddies_queue_path.exists():
        baddies_items = json.loads(baddies_queue_path.read_text(encoding="utf-8"))
        print(f"\nBaddies queue: {len(baddies_items)} item")
        if baddies_items:
            # Mevcut baddies slotlarını evening saatlerine taşı
            baddies_slots = [s for s in slots if s["channel"] == "sahnebaddiestr"]
            baddies_slots.sort(key=lambda s: s["slot"])
            evening_baddies = [s for s in baddies_slots if s["slot"] >= 24][:len(baddies_items)]

            for i, (slot, item) in enumerate(zip(evening_baddies, baddies_items[:len(EVENING_TIMES)])):
                slot["publishAtLocal"] = EVENING_TIMES[i]
                slot["status"] = "scheduled"
                slot["queueItemId"] = item.get("id", "")
                slot["file"] = item.get("file", "")
                slot["youtubeTitle"] = item.get("youtubeTitle", "")
                slot["youtubeDescription"] = item.get("youtubeDescription", "")
                slot["instagramCaption"] = item.get("instagramCaption", "")
                print(f"  Baddies Slot {slot['slot']}: {EVENING_TIMES[i]} ← {item.get('id','')}")
    else:
        print("Baddies queue yok, baddies slotları boş kalıyor")

    # Kaydet
    tmp = SCHEDULE_PATH.with_name(".2026-05-21_smu_schedule.json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SCHEDULE_PATH)
    print(f"\nSchedule güncellendi: {SCHEDULE_PATH}")

if __name__ == "__main__":
    main()
