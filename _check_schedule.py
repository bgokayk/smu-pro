#!/usr/bin/env python3
import json
from pathlib import Path

sched = json.loads(Path(r"schedules\2026-05-25_smu_schedule.json").read_text(encoding="utf-8-sig"))
slots = sched.get("slots", [])
print(f"Toplam slot: {len(slots)}")
future = [x for x in slots if x.get("publishAtLocal", "") >= "2026-05-25 04:20"]
print(f"Gelecek slot (04:20'den sonra): {len(future)}")
polished = sum(1 for x in slots if "_polished_at" in x)
print(f"Polished: {polished}/{len(slots)}")

# Kanal bazında dağılım
from collections import Counter
channels = Counter(x.get("channel","?") for x in slots)
print(f"\nKanal dağılımı:")
for ch, cnt in channels.most_common():
    fut = sum(1 for x in slots if x.get("channel")==ch and x.get("publishAtLocal","") >= "2026-05-25 04:20")
    pol = sum(1 for x in slots if x.get("channel")==ch and "_polished_at" in x)
    print(f"  {ch}: {cnt} slot (gelecek={fut}, polished={pol})")
