"""Detayli yayin analizi — slot_runs ve actual publish state."""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\User\.codex\content-ops")
CHANNELS = ["poster_loop_cinema", "sahnebaddiestr", "chatkesti"]


def read_json(p):
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


# 1. slot_runs detayi
print("=" * 70)
print("SLOT_RUNS DETAYLI ANALIZI")
print("=" * 70)
slot_runs_dir = ROOT / "queues" / "slot_runs"
runs_by_channel_platform = defaultdict(lambda: defaultdict(list))

for f in sorted(slot_runs_dir.glob("*.json")):
    data = read_json(f)
    ch = data.get("channel", "?")
    for prov in data.get("providers", []):
        plat = prov.get("provider", "?")
        status = prov.get("status", "?")
        url = prov.get("url") or prov.get("video_url") or prov.get("post_url") or ""
        err = prov.get("error", "")
        runs_by_channel_platform[ch][plat].append({
            "file": f.name,
            "status": status,
            "url": url[:60] if url else "",
            "err": err[:80] if err else "",
            "ts": data.get("publishedAt", data.get("attemptedAt", "")),
        })

for ch in CHANNELS:
    print(f"\n{ch}:")
    plats = runs_by_channel_platform.get(ch, {})
    for plat, attempts in plats.items():
        ok = sum(1 for a in attempts if a["status"] in ("published", "success", "ok"))
        fail = sum(1 for a in attempts if a["status"] in ("failed", "error"))
        other = len(attempts) - ok - fail
        print(f"  {plat:<12s}: {len(attempts):3d} attempt  ({ok} OK, {fail} FAIL, {other} other)")
        # Son 3 attempt
        for a in attempts[-3:]:
            tag = "OK " if a["status"] in ("published", "success", "ok") else "FAIL"
            print(f"    [{tag}] {a['ts'][:19]} -> {a['url'] or a['err'] or a['status']}")


# 2. Schedule slot'larin status alanlarini dikkatli kontrol et
print("\n" + "=" * 70)
print("SCHEDULE SLOT STATUS DETAYI")
print("=" * 70)
import time
today = time.strftime("%Y-%m-%d")
sched = read_json(ROOT / "schedules" / f"{today}_smu_schedule.json")
slots = sched.get("slots", [])

# Hangi slot'larin yayinlanma kaydi var
status_per_channel = defaultdict(lambda: defaultdict(int))
publish_records = defaultdict(lambda: defaultdict(list))

for s in slots:
    ch = s.get("channel", "?")
    # Tum status alanlarini topla
    for k, v in s.items():
        if isinstance(v, str) and v in ("published", "failed", "scheduled", "pending", "ready", "uploaded"):
            status_per_channel[ch][f"{k}={v}"] += 1
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, str) and vv in ("published", "failed", "scheduled", "pending", "uploaded"):
                    status_per_channel[ch][f"{k}.{kk}={vv}"] += 1

    # platform-spesifik url'ler
    for url_key in ("youtubeUrl", "instagramUrl", "tiktokUrl", "youtube_url", "instagram_url"):
        if s.get(url_key):
            plat = url_key.replace("Url", "").replace("_url", "")
            publish_records[ch][plat].append(s.get(url_key, "")[:60])

print("\nStatus dagilimi:")
for ch in CHANNELS:
    print(f"  {ch}:")
    for k, v in sorted(status_per_channel[ch].items()):
        print(f"    {k}: {v}")

print("\nSlot uzerindeki yayinlanma URL kayitlari:")
for ch in CHANNELS:
    plats = publish_records.get(ch, {})
    print(f"  {ch}: {dict((p, len(urls)) for p, urls in plats.items())}")


# 3. State klasoru var mi
print("\n" + "=" * 70)
print("STATE KLASORU")
print("=" * 70)
state_dir = ROOT / "state"
if state_dir.exists():
    files = list(state_dir.glob("*.json")) + list(state_dir.glob("*.jsonl"))
    for f in files:
        print(f"  {f.name}: {f.stat().st_size} bytes")
        # Ilk birkac satir
        try:
            content = f.read_text(encoding="utf-8-sig")[:300]
            print(f"    Preview: {content[:200]}")
        except Exception:
            pass
else:
    print("  YOK")


# 4. Worker config — hangi worker ne yapiyor
print("\n" + "=" * 70)
print("WORKER FILE ANALIZI")
print("=" * 70)
worker_files = list(ROOT.glob("*publish*.js")) + list(ROOT.glob("*worker*.js")) + list(ROOT.glob("*publish*.py"))
for w in sorted(set(worker_files)):
    try:
        content = w.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    yt_refs = len(re.findall(r"youtube|YOUTUBE|studio\.youtube", content))
    ig_refs = len(re.findall(r"instagram|INSTAGRAM|reels", content, re.I))
    tt_refs = len(re.findall(r"tiktok|TIKTOK", content, re.I))
    print(f"  {w.name}:")
    print(f"    YT refs: {yt_refs}, IG refs: {ig_refs}, TT refs: {tt_refs}")
