"""Tum sistemin kapsamli kontrolu - tek bakista nerede ne var."""
import json
import os
import socket
import subprocess
from collections import Counter
from pathlib import Path

CONTENT_OPS = Path(r"C:\Users\User\.codex\content-ops")
SMU_PRO = Path(r"C:\Users\User\.codex\smu-pro")


def hr(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")


def port_listening(port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def proc_matching(pattern: str) -> list:
    """Find python/node processes matching a pattern in cmdline."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "name='python.exe' or name='node.exe'",
             "get", "ProcessId,CommandLine", "/format:list"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).decode(errors="replace")
    except Exception:
        return []
    procs = []
    pid = None
    cmd = None
    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("CommandLine="):
            cmd = line[12:]
        elif line.startswith("ProcessId="):
            pid = line[10:]
            if cmd and pattern.lower() in cmd.lower():
                procs.append((pid, cmd[:120]))
            cmd = None
    return procs


def check_schedule(label: str, path: Path) -> dict:
    if not path.exists():
        return {"ok": False, "reason": "dosya yok"}
    try:
        d = json.loads(path.read_text(encoding="utf-8-sig"))
        slots = d.get("slots", [])
        titles = [s.get("youtubeTitle", "") for s in slots]
        descs = [s.get("youtubeDescription", "") for s in slots]
        igs = [s.get("instagramCaption", "") for s in slots]
        unique = len(Counter(titles))
        avg_t = sum(len(t) for t in titles) / max(len(titles), 1)
        avg_d = sum(len(t) for t in descs) / max(len(descs), 1)
        avg_i = sum(len(t) for t in igs) / max(len(igs), 1)
        return {
            "ok": True,
            "slots": len(slots),
            "unique": unique,
            "avg_title": avg_t,
            "avg_desc": avg_d,
            "avg_ig": avg_i,
            "mtime": path.stat().st_mtime,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ----------------- 1. SCHEDULE DURUMU -----------------
hr("1. SCHEDULE DURUMU (regenerator bitti mi?)")
for label, root in [("content-ops", CONTENT_OPS), ("smu-pro", SMU_PRO)]:
    path = root / "schedules" / "2026-05-24_smu_schedule.json"
    info = check_schedule(label, path)
    if info["ok"]:
        import datetime
        mtime = datetime.datetime.fromtimestamp(info["mtime"]).strftime("%H:%M:%S")
        verdict = "OK" if info["unique"] >= 85 and info["avg_desc"] >= 800 else "EKSIK"
        print(f"  {label:12s} | slot:{info['slots']:3d} | unique:{info['unique']:3d}/90 | "
              f"baslik:{info['avg_title']:.0f}c | yt:{info['avg_desc']:.0f}c | "
              f"ig:{info['avg_ig']:.0f}c | mtime:{mtime} | {verdict}")
    else:
        print(f"  {label:12s} | HATA: {info.get('reason')}")

# ----------------- 2. REGENERATOR HALA CALISIYOR MU? -----------------
hr("2. REGENERATOR/CLINE SURECLERI")
for pat in ["regenerate", "smu_daemon", "smu_app", "run_dashboard"]:
    matches = proc_matching(pat)
    print(f"  [{pat}] -> {len(matches)} process")
    for pid, cmd in matches[:3]:
        print(f"    PID {pid}: {cmd[:100]}")

# ----------------- 3. DASHBOARD 5004 -----------------
hr("3. DASHBOARD 5004 DURUMU")
if port_listening(5004):
    print("  Port 5004 DINLENIYOR")
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:5004/api/data", timeout=5)
        data = json.loads(r.read())
        slots = data.get("slots", [])
        past = data.get("past_slots", [])
        print(f"  API yanit: slots={len(slots)} past={len(past)}")
    except Exception as e:
        print(f"  API hata: {e}")
else:
    print("  Port 5004 KAPALI")

# ----------------- 4. BROWSER DEBUG PORTS -----------------
hr("4. BROWSER DEBUG PORTS")
for port, name in [(9222, "Chrome (poster_loop)"), (9223, "Edge (baddies)"), (9224, "Firefox (chatkesti)")]:
    status = "ACIK" if port_listening(port) else "KAPALI"
    print(f"  Port {port} ({name}): {status}")

# Firefox port'u 9224 degil de standart firefox debug olabilir
try:
    firefox_procs = proc_matching("firefox")
    print(f"  Firefox process sayisi: {len(firefox_procs)}")
except Exception:
    pass

# ----------------- 5. WORKER LOG/HATA DURUMU -----------------
hr("5. SON DAEMON AKTIVITESI")
for label, root in [("content-ops", CONTENT_OPS), ("smu-pro", SMU_PRO)]:
    log = root / "logs" / "smu_daemon.log"
    if log.exists():
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            print(f"  {label} smu_daemon.log son 5 satir:")
            for line in lines[-5:]:
                print(f"    {line[:150]}")
        except Exception as e:
            print(f"  {label}: log okunamadi: {e}")
    else:
        print(f"  {label}: log yok")

# ----------------- 6. QUEUE DURUMLARI -----------------
hr("6. QUEUE DOSYALARI (chatkesti yeniden olusturuldu mu?)")
queues = [
    ("posterloop", r"C:\Users\User\.codex\analog-neo-moving-poster\automation\posterloop_queue_21_50.json"),
    ("baddies", r"C:\Users\User\.codex\sahne-baddies-auto\automation\baddies_queue_batch001.json"),
    ("chatkesti", r"C:\Users\User\.codex\yayinci-kesitleri-auto\automation\chatkesti_queue_batch001.json"),
]
for name, path in queues:
    p = Path(path)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            items = len(d.get("items", d) if isinstance(d, dict) else d)
            sz = p.stat().st_size
            import datetime
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
            print(f"  {name:12s} | items:{items:3d} | {sz:6d}b | {mtime}")
        except Exception as e:
            print(f"  {name}: parse hata: {e}")
    else:
        print(f"  {name}: YOK")

# ----------------- 7. CLINE DEVIR LOG -----------------
hr("7. CLINE DEVIR LOG (gorev raporu)")
for root in [CONTENT_OPS, SMU_PRO]:
    log = root / "logs" / "cline_devir_log.md"
    if log.exists():
        print(f"  VAR: {log}")
        try:
            content = log.read_text(encoding="utf-8", errors="replace")
            print(content[:2000])
        except Exception:
            pass
        break
else:
    print("  Cline devir logu YOK (Cline gorev yapmamis olabilir)")

# ----------------- 8. STATE/PUBLISHED_LEDGER -----------------
hr("8. PUBLISHED_LEDGER (duplicate kontrolu icin)")
for label, root in [("content-ops", CONTENT_OPS), ("smu-pro", SMU_PRO)]:
    p = root / "state" / "published_ledger.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(d, list):
                print(f"  {label}: {len(d)} entry")
            elif isinstance(d, dict):
                total = sum(len(v) if isinstance(v, list) else 1 for v in d.values())
                print(f"  {label}: {len(d)} key, ~{total} entry")
        except Exception as e:
            print(f"  {label}: parse hata: {e}")
    else:
        print(f"  {label}: ledger yok")

print("\n" + "=" * 60)
print("KONTROL TAMAMLANDI")
print("=" * 60)
