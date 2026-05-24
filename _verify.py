import json

with open(r"C:\Users\User\.codex\content-ops\schedules\2026-05-24_smu_schedule.json", "r", encoding="utf-8-sig") as f:
    d = json.load(f)

print("=== ORNEK SLOT'LAR (basliklar regenerate edildi mi?) ===\n")
for i in [0, 30, 60, 89]:
    s = d["slots"][i]
    ch = s["channel"]
    title = s.get("youtubeTitle", "")
    desc_len = len(s.get("youtubeDescription", ""))
    insta_len = len(s.get("instagramCaption", ""))
    print(f"Slot {i} [{ch}]")
    print(f"  Baslik    ({len(title)} char): {title}")
    print(f"  YT acklma uzunluk: {desc_len} (hedef: 800+)")
    print(f"  Insta caption uzunluk: {insta_len} (hedef: 500+)")
    print()

# Toplam istatistik
titles = [s.get("youtubeTitle", "") for s in d["slots"]]
descs = [s.get("youtubeDescription", "") for s in d["slots"]]
captions = [s.get("instagramCaption", "") for s in d["slots"]]

print("=== TOPLAM ISTATISTIK ===")
print(f"Toplam slot: {len(d['slots'])}")
print(f"Ortalama baslik uzunlugu: {sum(len(t) for t in titles)/len(titles):.0f} char (hedef: 70-100)")
print(f"Ortalama acklma uzunlugu: {sum(len(d) for d in descs)/len(descs):.0f} char (hedef: 800+)")
print(f"Ortalama caption uzunlugu: {sum(len(c) for c in captions)/len(captions):.0f} char (hedef: 500+)")

# Duplicate kontrolu
from collections import Counter
title_count = Counter(titles)
duplicates = {t: c for t, c in title_count.items() if c > 1}
print(f"\n=== DUPLICATE BASLIKLAR ===")
print(f"Unique baslik sayisi: {len(title_count)}/{len(titles)}")
if duplicates:
    print(f"Duplicate sayisi: {sum(duplicates.values()) - len(duplicates)} tekrar")
    for t, c in list(duplicates.items())[:5]:
        print(f"  {c}x: {t[:80]}")
else:
    print("Duplicate yok")
