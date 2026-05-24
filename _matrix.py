"""Kanal x Platform yayin matrisi raporu."""
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\User\.codex\content-ops")

CHANNELS = ["poster_loop_cinema", "sahnebaddiestr", "chatkesti"]
PLATFORMS = ["youtube", "instagram", "tiktok"]


def read_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


# 1. published_registry.json
registry = read_json(ROOT / "published_registry.json", {})
print("=" * 70)
print("1. PUBLISHED_REGISTRY.JSON")
print("=" * 70)
for ch in CHANNELS:
    items = registry.get(ch, [])
    print(f"  {ch:25s}: {len(items)} kayit")
    if items:
        print(f"    Ornek: {items[:3]}")

# 2. published_ledger varsa
ledger_files = list(ROOT.glob("*ledger*.json")) + list(ROOT.glob("*ledger*.jsonl"))
print("\n" + "=" * 70)
print("2. LEDGER DOSYALARI")
print("=" * 70)
for lf in ledger_files:
    print(f"  {lf.name}: {lf.stat().st_size} bytes")

# 3. Schedule status
print("\n" + "=" * 70)
print("3. SCHEDULE STATUS (bugun)")
print("=" * 70)
today = datetime.now().strftime("%Y-%m-%d")
sched = read_json(ROOT / "schedules" / f"{today}_smu_schedule.json", {})
slots = sched.get("slots", [])

# Channel x Platform matrix
matrix = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
for s in slots:
    ch = s.get("channel", "?")
    status = s.get("status", "unknown")
    # Slotun platforms alani var mi?
    platforms = s.get("platforms", [])
    if platforms:
        for p in platforms:
            matrix[ch][p][status] += 1
    else:
        matrix[ch]["all"][status] += 1

for ch in CHANNELS:
    print(f"\n  {ch}:")
    for plat, statuses in matrix[ch].items():
        print(f"    {plat}: {dict(statuses)}")

# 4. Log dosyalarindan platform-spesifik yayinlanma sayilari
print("\n" + "=" * 70)
print("4. LOG ANALIZI — son 7 gun")
print("=" * 70)

log_dir = ROOT / "logs"
publish_counts = defaultdict(lambda: defaultdict(int))
error_counts = defaultdict(lambda: defaultdict(int))

if log_dir.exists():
    for log_file in log_dir.glob("*.log"):
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Tahmini kanal-platform parse (filename'den)
        name = log_file.stem.lower()
        ch_match = None
        for ch in CHANNELS:
            if ch in name:
                ch_match = ch
                break
        if not ch_match:
            continue
        # Basari/hata sayisi
        success = len(re.findall(r"published|success|uploaded|posted", content, re.I))
        errors = len(re.findall(r"error|hata|failed|exception", content, re.I))

        # Platform tahmini
        plat = "?"
        if "youtube" in name or "_yt" in name or "shorts" in content[:5000].lower():
            plat = "youtube"
        elif "instagram" in name or "_ig" in name or "reels" in content[:5000].lower():
            plat = "instagram"
        elif "tiktok" in name or "_tt" in name:
            plat = "tiktok"

        if success > 0:
            publish_counts[ch_match][plat] += success
        if errors > 0:
            error_counts[ch_match][plat] += errors

print("\n  Yayinlanma sayilari (log icinden):")
print(f"  {'Kanal':<25s} {'YT':>8s} {'IG':>8s} {'TT':>8s} {'?':>8s}")
for ch in CHANNELS:
    yt = publish_counts[ch].get("youtube", 0)
    ig = publish_counts[ch].get("instagram", 0)
    tt = publish_counts[ch].get("tiktok", 0)
    unk = publish_counts[ch].get("?", 0)
    print(f"  {ch:<25s} {yt:>8d} {ig:>8d} {tt:>8d} {unk:>8d}")

print("\n  Hata sayilari (log icinden):")
print(f"  {'Kanal':<25s} {'YT':>8s} {'IG':>8s} {'TT':>8s} {'?':>8s}")
for ch in CHANNELS:
    yt = error_counts[ch].get("youtube", 0)
    ig = error_counts[ch].get("instagram", 0)
    tt = error_counts[ch].get("tiktok", 0)
    unk = error_counts[ch].get("?", 0)
    print(f"  {ch:<25s} {yt:>8d} {ig:>8d} {tt:>8d} {unk:>8d}")

# 5. Slot run logs
print("\n" + "=" * 70)
print("5. SLOT_RUNS klasoru")
print("=" * 70)
slot_runs = ROOT / "queues" / "slot_runs"
if slot_runs.exists():
    files = list(slot_runs.glob("*.json"))
    print(f"  Toplam slot_run dosyasi: {len(files)}")
    # Kanal bazli grupla
    by_channel = defaultdict(list)
    for f in files:
        for ch in CHANNELS:
            if ch in f.name.lower():
                by_channel[ch].append(f)
                break
    for ch in CHANNELS:
        print(f"  {ch}: {len(by_channel[ch])} dosya")

# 6. Worker dosyalari listele
print("\n" + "=" * 70)
print("6. WORKER DOSYALARI")
print("=" * 70)
workers = list(ROOT.glob("*worker*.js")) + list(ROOT.glob("*worker*.py")) + list(ROOT.glob("*publish*.js")) + list(ROOT.glob("*publish*.py"))
for w in sorted(set(workers)):
    print(f"  {w.name}: {w.stat().st_size} bytes, {datetime.fromtimestamp(w.stat().st_mtime).strftime('%m-%d %H:%M')}")
