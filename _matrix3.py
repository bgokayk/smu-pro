"""GERCEK state'i oku — state/published_ledger.json + publish_runs/"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\User\.codex\content-ops")
STATE = ROOT / "state"
CHANNELS = ["poster_loop_cinema", "sahnebaddiestr", "chatkesti"]


def read_json(p, default=None):
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        return default if default is not None else {}


# 1. published_ledger.json — esas kaynak
print("=" * 70)
print("1. STATE/PUBLISHED_LEDGER.JSON")
print("=" * 70)
ledger = read_json(STATE / "published_ledger.json", {})
print(f"Top type: {type(ledger).__name__}")
if isinstance(ledger, dict):
    print(f"Top keys: {list(ledger.keys())[:10]}")
    # Tahminen channel -> liste / kanal x platform yapisi
    for k in list(ledger.keys())[:3]:
        v = ledger[k]
        print(f"  {k}: {type(v).__name__}, ", end="")
        if isinstance(v, list):
            print(f"len={len(v)}")
            if v and isinstance(v[0], dict):
                print(f"    first keys: {list(v[0].keys())}")
                print(f"    first: {json.dumps(v[0], ensure_ascii=False)[:200]}")
        elif isinstance(v, dict):
            print(f"keys={list(v.keys())[:5]}")
elif isinstance(ledger, list):
    print(f"Liste, len={len(ledger)}")
    if ledger and isinstance(ledger[0], dict):
        print(f"First keys: {list(ledger[0].keys())}")
        print(f"First: {json.dumps(ledger[0], ensure_ascii=False)[:300]}")


# 2. publish_runs detayli
print("\n" + "=" * 70)
print("2. STATE/PUBLISH_RUNS/ DETAYI")
print("=" * 70)
pr_dir = STATE / "publish_runs"
if pr_dir.exists():
    by_channel = defaultdict(list)
    for f in pr_dir.glob("*.json"):
        for ch in CHANNELS:
            if ch in f.name:
                by_channel[ch].append(f)
                break

    for ch in CHANNELS:
        files = by_channel[ch]
        print(f"\n  {ch}: {len(files)} dosya")
        # Hepsini oku
        platform_results = defaultdict(lambda: defaultdict(int))
        for f in files[-5:]:  # son 5
            data = read_json(f)
            print(f"\n    {f.stem[:60]}:")
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, (str, int, bool)):
                        print(f"      {k}: {v}")
                    elif isinstance(v, dict):
                        print(f"      {k}: {json.dumps(v, ensure_ascii=False)[:150]}")
                    elif isinstance(v, list):
                        print(f"      {k}: [{len(v)} items]")
                        for item in v[:2]:
                            print(f"        - {json.dumps(item, ensure_ascii=False)[:120]}")


# 3. daemon_state ve pipeline_state
print("\n" + "=" * 70)
print("3. DAEMON_STATE.JSON")
print("=" * 70)
ds = read_json(STATE / "daemon_state.json")
print(json.dumps(ds, ensure_ascii=False, indent=2)[:1000])

print("\n" + "=" * 70)
print("4. PIPELINE_STATE.JSON (ilk 1500 char)")
print("=" * 70)
ps = read_json(STATE / "pipeline_state.json")
print(json.dumps(ps, ensure_ascii=False, indent=2)[:1500])
