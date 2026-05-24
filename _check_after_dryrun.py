import json
from collections import Counter
from pathlib import Path

p = Path(r"C:\Users\User\.codex\content-ops\schedules\2026-05-24_smu_schedule.json")
with open(p, "r", encoding="utf-8-sig") as f:
    d = json.load(f)

titles = [s.get("youtubeTitle", "") for s in d["slots"]]
descs = [s.get("youtubeDescription", "") for s in d["slots"]]
total = len(d["slots"])

print(f"Toplam slot: {total}")
print(f"Avg baslik uzunlugu: {sum(len(t) for t in titles)/total:.0f} char")
print(f"Avg aciklama uzunlugu: {sum(len(x) for x in descs)/total:.0f} char")
print()

c = Counter(titles)
print(f"Unique baslik: {len(c)}/{total}")
print(f"En cok tekrar eden 3 baslik:")
for t, n in c.most_common(3):
    print(f"  {n}x: {t[:80]}")

print()
print("Slot 1, 30, 60 ornekleri:")
for i in [1, 30, 60]:
    if i < total:
        s = d["slots"][i]
        regen = "_regenerated_at" in s or "_regenerated" in s
        print(f"  Slot {i} [{s['channel']}] {'(REGEN)' if regen else '(eski)'}: {s.get('youtubeTitle','')[:80]}")
