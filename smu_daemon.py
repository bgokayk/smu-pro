#!/usr/bin/env python3
"""SMU Daemon â€” 24/7 sosyal medya otomasyon sÃ¼reci.

DÃ¶ngÃ¼ mantÄ±ÄŸÄ±:
  - 01:00-07:00 Istanbul saatinde uyku modu (post yok, download yok)
  - 07:00: Sabah hazÄ±rlÄ±ÄŸÄ± â†’ indir â†’ gÃ¼n planÄ±nÄ± yap â†’ kuyruÄŸa ekle
  - GÃ¼n iÃ§i: schedule'daki slotlara gÃ¶re worker'larÄ± tetikle
  - Her post sonrasÄ± yorum taslaÄŸÄ±
  - Gece 01:00: tekrar uyku

KullanÄ±m:
  python smu_daemon.py start              # Ã‡alÄ±ÅŸtÄ±r (sonsuz dÃ¶ngÃ¼)
  python smu_daemon.py start --dry-run    # Test modu
  python smu_daemon.py next-event         # Bir sonraki olayÄ± gÃ¶ster
  python smu_daemon.py status             # BugÃ¼nkÃ¼ durum
  python smu_daemon.py morning-prep       # Elle sabah hazÄ±rlÄ±ÄŸÄ±nÄ± baÅŸlat
"""

from __future__ import annotations

import io
import sys

# Windows konsol UTF-8 zorla
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"
LOG_FILE = ROOT / "logs" / "smu_daemon.log"
DAEMON_STATE = ROOT / "state" / "daemon_state.json"
AUDIT_FREEZE_FILE = ROOT / "state" / "audit_freeze.json"
SLOT_QUEUE_DIR = ROOT / "queues" / "slot_runs"
PUBLISH_STATE_DIR = ROOT / "state" / "publish_runs"

ISTANBUL_OFFSET = dt.timedelta(hours=3)   # UTC+3 (DST yok, zoneinfo yoksa sabit)

try:
    from zoneinfo import ZoneInfo
    _ISTANBUL_TZ: Any = ZoneInfo("Europe/Istanbul")
    def _now_local() -> dt.datetime:
        return dt.datetime.now(tz=_ISTANBUL_TZ)
except Exception:
    _ISTANBUL_TZ = None
    def _now_local() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc) + ISTANBUL_OFFSET


# â”€â”€ loglama â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _setup_logging() -> logging.Logger:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smu_daemon")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8-sig")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


LOG = _setup_logging()


# â”€â”€ config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_config() -> dict[str, Any]:
    """Config dosyasÄ±nÄ± oku, hata yÃ¶netimi ile dÃ¶ndÃ¼r."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            LOG.warning("Config dosyasÄ± dict deÄŸil, boÅŸ config dÃ¶nÃ¼lÃ¼yor")
            return {}
        return data
    except FileNotFoundError:
        LOG.error("Config dosyasÄ± bulunamadÄ±: %s", CONFIG_FILE)
        return {}
    except json.JSONDecodeError as exc:
        LOG.error("Config dosyasÄ± JSON ayrÄ±ÅŸtÄ±rma hatasÄ±: %s", exc)
        return {}
    except PermissionError:
        LOG.error("Config dosyasÄ± okuma izni yok: %s", CONFIG_FILE)
        return {}
    except Exception as exc:
        LOG.error("Config dosyasÄ± okunurken beklenmeyen hata: %s", exc)
        return {}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    tmp.replace(path)


# â”€â”€ zaman yÃ¶netimi â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _parse_hhmm(value: str) -> dt.time:
    h, m = value.split(":")
    return dt.time(int(h), int(m))


def in_no_post_window(config: dict[str, Any], now: dt.datetime | None = None) -> bool:
    """01:00-07:00 aralÄ±ÄŸÄ±nda mÄ±yÄ±z? disabled=true ise hiÃ§ girmez."""
    npw = config.get("noPostWindow", {})
    if npw.get("disabled", False):
        return False
    if now is None:
        now = _now_local()
    t = now.time()
    start = _parse_hhmm(npw["start"])
    end   = _parse_hhmm(npw["end"])
    if start < end:
        return start <= t < end
    # Gece yarÄ±sÄ±nÄ± geÃ§en pencere (start > end): 23:00 - 05:00 gibi
    return t >= start or t < end


def seconds_until_window_end(config: dict[str, Any]) -> int:
    """07:00'a kaÃ§ saniye?"""
    now = _now_local()
    end = _parse_hhmm(config["noPostWindow"]["end"])
    target = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds())


def seconds_until_no_post(config: dict[str, Any]) -> int:
    """01:00'e kaÃ§ saniye? disabled=true ise Ã§ok bÃ¼yÃ¼k deÄŸer dÃ¶ner (asla uyuma)."""
    npw = config.get("noPostWindow", {})
    if npw.get("disabled", False):
        return 86400  # 24 saat â€” asla uyku moduna girmez
    now = _now_local()
    start = _parse_hhmm(npw["start"])
    target = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds())


# â”€â”€ daemon durumu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_daemon_state() -> dict[str, Any]:
    if DAEMON_STATE.exists():
        try:
            return read_json(DAEMON_STATE)
        except Exception:
            pass
    return {"last_morning_prep": "", "last_slots_fired": [], "last_comment_round": ""}


def save_daemon_state(state: dict[str, Any]) -> None:
    write_json(DAEMON_STATE, state)


def audit_freeze_active() -> bool:
    return AUDIT_FREEZE_FILE.exists()


def audit_freeze_reason() -> str:
    if not AUDIT_FREEZE_FILE.exists():
        return ""
    try:
        data = read_json(AUDIT_FREEZE_FILE)
        return str(data.get("reason") or "audit freeze active")
    except Exception:
        return "audit freeze active"


def morning_prep_done_today(state: dict[str, Any]) -> bool:
    today = _now_local().date().isoformat()
    return state.get("last_morning_prep", "")[:10] == today


# â”€â”€ alt sÃ¼reÃ§leri Ã§alÄ±ÅŸtÄ±r â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def run_python(args: list[str], cwd: Path | None = None, dry_run: bool = False) -> bool:
    cmd = [sys.executable] + args
    label = " ".join(str(a) for a in cmd[:5])
    if dry_run:
        LOG.info("[dry-run] %s", label)
        return True
    LOG.info("Ã‡alÄ±ÅŸtÄ±rÄ±yor: %s", label)
    result = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        text=True,
        timeout=3600,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        LOG.warning("Ã‡Ä±kÄ±ÅŸ kodu %d: %s", result.returncode, label)
        if result.stdout and result.stdout.strip():
            LOG.warning("  stdout: %s", result.stdout.strip()[-800:])
        if result.stderr and result.stderr.strip():
            LOG.warning("  stderr: %s", result.stderr.strip()[-800:])
        return False
    if result.stdout and result.stdout.strip():
        LOG.debug("  stdout: %s", result.stdout.strip()[-400:])
    return True


def run_node(script: Path, env: dict[str, str] | None = None, dry_run: bool = False) -> bool:
    if dry_run:
        LOG.info("[dry-run] node %s", script.name)
        return True
    if not script.exists():
        LOG.warning("Script bulunamadÄ±: %s", script)
        return False
    full_env = {**os.environ, **(env or {})}
    LOG.info("node %s", script.name)
    result = subprocess.run(
        ["node", str(script)],
        cwd=str(script.parent),
        env=full_env,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        LOG.warning("node Ã§Ä±kÄ±ÅŸ kodu %d: %s", result.returncode, script.name)
        return False
    return True


# â”€â”€ kanal pipeline tanÄ±mlarÄ± â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

CHANNEL_PIPELINES: dict[str, dict[str, Any]] = {
    "poster_loop_cinema": {
        "root": Path("C:/Users/User/.codex/analog-neo-moving-poster"),
        "steps": [
            # Filmmax-21-50 export klasÃ¶rÃ¼nden queue JSON Ã¼ret (render zaten tamamlandÄ±)
            {"type": "python", "script": "build_posterloop_queue_21_50.py", "label": "queue oluÅŸtur"},
            # Not: render_filmmax_poster_exports.py filmmax-last20 iÃ§indir ve zaten tamamlandÄ±.
            # filmmax-21-50 render'Ä± ayrÄ± bir scriptile yapÄ±lÄ±r, burada Ã§alÄ±ÅŸtÄ±rÄ±lmaz.
        ],
        # pipeline bittikten sonra bu dosya schedule slotlarÄ±na eklenir
        "queue_file": Path("C:/Users/User/.codex/analog-neo-moving-poster/automation/posterloop_queue_21_50.json"),
        "worker": Path("C:/Users/User/.codex/analog-neo-moving-poster/automation/posterloop_dual_publish_worker.js"),
        "worker_env": {
            "POSTERLOOP_BASE": "C:/Users/User/.codex/analog-neo-moving-poster",
            "POSTERLOOP_DEBUG_ENDPOINT": "http://127.0.0.1:9222",
        },
    },
    "sahnebaddiestr": {
        "root": Path("C:/Users/User/.codex/sahne-baddies-auto"),
        "steps": [
            {"type": "python", "script": "ingest_baddies_sources.py", "label": "ingest"},
            {"type": "python", "script": "build_baddies_queue.py",    "label": "queue oluÅŸtur"},
            {"type": "python", "script": "render_baddies_exports.py", "label": "render"},
        ],
        # build_baddies_queue.py bu dosyayÄ± Ã¼retmeli
        "queue_file": Path("C:/Users/User/.codex/sahne-baddies-auto/automation/baddies_queue_batch001.json"),
        "worker": Path("C:/Users/User/.codex/sahne-baddies-auto/automation/baddies_dual_publish_worker.js"),
        "worker_env": {
            "BADDIES_BASE": "C:/Users/User/.codex/sahne-baddies-auto",
            "BADDIES_DEBUG_ENDPOINT": "http://127.0.0.1:9223",
        },
    },
    "chatkesti": {
        "root": Path("C:/Users/User/.codex/yayinci-kesitleri-auto"),
        "steps": [
            {"type": "python", "script": "ingest_chatkesti_sources.py", "label": "ingest"},
            {"type": "python", "script": "analyze_clip_layout.py", "args": ["--items"], "label": "analiz"},
            {"type": "python", "script": "render_chatkesti_exports.py", "label": "render"},
            {"type": "python", "script": "build_chatkesti_queue.py",    "label": "queue oluÅŸtur"},
        ],
        "queue_file": Path("C:/Users/User/.codex/yayinci-kesitleri-auto/automation/chatkesti_queue_batch001.json"),
        "worker": Path("C:/Users/User/.codex/yayinci-kesitleri-auto/automation/chatkesti_firefox_publish_worker.py"),
        "worker_env": {
            "CHATKESTI_ROOT": "C:/Users/User/.codex/yayinci-kesitleri-auto",
            "CHATKESTI_FIREFOX_PROFILE": "C:/Users/User/.codex/browser-profiles/chatkesti-firefox",
            "CHATKESTI_MAX_JOBS": "1",
        },
    },
}


def run_channel_pipeline(channel_id: str, dry_run: bool = False) -> bool:
    """Bir kanalÄ±n ingestâ†’queueâ†’render pipeline'Ä±nÄ± Ã§alÄ±ÅŸtÄ±r."""
    pipeline = CHANNEL_PIPELINES.get(channel_id)
    if not pipeline:
        LOG.warning("Pipeline tanÄ±mÄ± yok: %s", channel_id)
        return False

    root = pipeline["root"]
    for step in pipeline["steps"]:
        script = root / step["script"]
        label  = step.get("label", step["script"])
        if not script.exists():
            LOG.warning("  Script bulunamadÄ±, atlanÄ±yor: %s", script)
            continue
        LOG.info("  [%s] %s", channel_id, label)
        ok = run_python([str(script), *step.get("args", [])], cwd=root, dry_run=dry_run)
        if not ok:
            LOG.warning("  [%s] %s baÅŸarÄ±sÄ±z, devam ediliyorâ€¦", channel_id, label)

    return True


# â”€â”€ sabah hazÄ±rlÄ±ÄŸÄ± â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def do_morning_prep(config: dict[str, Any], dry_run: bool = False) -> None:
    if audit_freeze_active():
        LOG.warning("Audit freeze active; morning-prep skipped: %s", audit_freeze_reason())
        return

    LOG.info("=== Sabah hazÄ±rlÄ±ÄŸÄ± baÅŸlÄ±yor ===")

    active_channels = [
        ch_id
        for ch_id, ch in config.get("channels", {}).items()
        if ch.get("active", False)
    ]

    # 1. Her kanal iÃ§in ingest â†’ queue â†’ render
    for channel_id in active_channels:
        LOG.info("--- Pipeline: %s ---", channel_id)
        run_channel_pipeline(channel_id, dry_run=dry_run)

    # 2. BoÅŸ takvim + yorum planÄ± oluÅŸtur (slotlar needs_queue_item olarak gelir)
    LOG.info("GÃ¼nlÃ¼k takvim hazÄ±rlanÄ±yorâ€¦")
    today = _now_local().date().isoformat()
    schedule_file = ROOT / "schedules" / f"{today}_smu_schedule.json"

    prep_ok = run_python(
        [str(ROOT / "smu.py"), "prepare-day",
         "--providers", "cache,template",
         "--assume-confirmed"],
        dry_run=dry_run,
    )
    if not prep_ok:
        # Fallback: create a blank slot schedule without content pipeline
        LOG.warning("prepare-day baÅŸarÄ±sÄ±z; yedek plan-day Ã§alÄ±ÅŸtÄ±rÄ±lÄ±yorâ€¦")
        run_python(
            [str(ROOT / "smu.py"), "plan-day"],
            dry_run=dry_run,
        )

    # 3. Her kanal iÃ§in pipeline'Ä±n Ã¼rettiÄŸi queue'yu slotlara at
    if schedule_file.exists():
        for channel_id in active_channels:
            pipeline = CHANNEL_PIPELINES.get(channel_id, {})
            queue_file: Path = pipeline.get("queue_file", Path(""))
            if queue_file.exists():
                LOG.info("  Slotlara atanÄ±yor (force): %s â†’ %s", channel_id, queue_file.name)
                run_python(
                    [str(ROOT / "smu.py"), "attach-queue",
                     "--schedule", str(schedule_file),
                     "--queue",    str(queue_file),
                     "--channel",  channel_id,
                     "--out",      str(schedule_file),
                     "--force"],    # override template slots with real queue content
                    dry_run=dry_run,
                )
            else:
                LOG.warning("  Queue dosyasÄ± yok, slot boÅŸ kalacak: %s (%s)", channel_id, queue_file)
    else:
        LOG.warning("Schedule dosyasÄ± bulunamadÄ±: %s", schedule_file)

    # 4. TarayÄ±cÄ±larÄ± aÃ§ (Chrome â†’ PosterLoop, Edge â†’ BaddiesTR)
    LOG.info("TarayÄ±cÄ±lar aÃ§Ä±lÄ±yorâ€¦")
    run_python(
        [str(ROOT / "content_ops.py"), "launch-browsers", "--channel", "all"],
        dry_run=dry_run,
    )

    state = load_daemon_state()
    state["last_morning_prep"] = _now_local().isoformat(timespec="seconds")
    state["last_slots_fired"] = []
    save_daemon_state(state)
    LOG.info("=== Sabah hazÄ±rlÄ±ÄŸÄ± tamamlandÄ± ===")


# â”€â”€ slot yÃ¶netimi â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _channel_worker(channel_id: str) -> Path:
    pipeline = CHANNEL_PIPELINES.get(channel_id, {})
    return Path(pipeline.get("worker", ""))


def _channel_env(channel_id: str) -> dict[str, str]:
    pipeline = CHANNEL_PIPELINES.get(channel_id, {})
    return pipeline.get("worker_env", {})


def _safe_slot_id(slot: dict[str, Any]) -> str:
    raw = f"{slot.get('channel', 'channel')}-slot{slot.get('slot', '0')}-{slot.get('queueItemId') or slot.get('id') or 'item'}"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in raw).strip("-")


def _slot_queue_item(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": slot.get("queueItemId") or slot.get("id") or _safe_slot_id(slot),
        "sourceLink": slot.get("sourceLink", ""),
        "platform": slot.get("platform", ""),
        "streamer": slot.get("streamer", ""),
        "game": slot.get("game", ""),
        "rightsNote": slot.get("rightsNote", ""),
        "file": slot.get("file", ""),
        "youtubeTitle": slot.get("youtubeTitle", ""),
        "youtubeDescription": slot.get("youtubeDescription", ""),
        "instagramCaption": slot.get("instagramCaption", ""),
        "tiktokCaption": slot.get("tiktokCaption", ""),
    }


def _slot_worker_env(channel_id: str, slot: dict[str, Any]) -> dict[str, str]:
    """Run each scheduled slot as a one-item queue.

    Channel workers are batch workers by default. If SMU calls a worker without
    an explicit slot queue, the worker can fall back to an old/default queue and
    publish the wrong videos.
    """
    env = dict(_channel_env(channel_id))
    slot_id = _safe_slot_id(slot)
    SLOT_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISH_STATE_DIR.mkdir(parents=True, exist_ok=True)

    queue_path = SLOT_QUEUE_DIR / f"{slot_id}.json"
    state_path = PUBLISH_STATE_DIR / f"{slot_id}.json"
    log_path = ROOT / "logs" / f"{slot_id}.log"
    write_json(queue_path, [_slot_queue_item(slot)])

    if channel_id == "poster_loop_cinema":
        env.update(
            {
                "POSTERLOOP_QUEUE_PATH": str(queue_path),
                "POSTERLOOP_STATE_PATH": str(state_path),
                "POSTERLOOP_LOG_PATH": str(log_path),
                "POSTERLOOP_WAIT_MS": "5000",
            }
        )
    elif channel_id == "sahnebaddiestr":
        env.update(
            {
                "BADDIES_QUEUE_PATH": str(queue_path),
                "BADDIES_STATE_PATH": str(state_path),
                "BADDIES_LOG_PATH": str(log_path),
                "BADDIES_WAIT_MS": "5000",
            }
        )
    elif channel_id == "chatkesti":
        env.update(
            {
                "CHATKESTI_QUEUE_PATH": str(queue_path),
                "CHATKESTI_STATE_PATH": str(state_path),
                "CHATKESTI_LOG_PATH": str(log_path),
                "CHATKESTI_WAIT_MS": "5000",
            }
        )
    return env


def load_today_schedule() -> dict[str, Any]:
    today = _now_local().date().isoformat()
    sch_path = ROOT / "schedules" / f"{today}_smu_schedule.json"
    if not sch_path.exists():
        return {}
    try:
        return read_json(sch_path)
    except Exception:
        return {}


# Statuses that are eligible to be fired by the slot loop.
# "blocked_legacy_smu_review" was set by an older Codex version â€” treat as scheduled.
FIREABLE_STATUSES = {"scheduled", "queued"}


def slots_due_now(schedule: dict[str, Any], already_fired: list[str], window_min: int = 3) -> list[dict[str, Any]]:
    """Åu anki zamana gÃ¶re ateÅŸlenmesi gereken slotlarÄ± bul."""
    now = _now_local()
    result = []
    for slot in schedule.get("slots", []):
        slot_id = f"{slot['channel']}-slot{slot['slot']}"
        if slot_id in already_fired:
            continue
        if slot.get("status") not in FIREABLE_STATUSES:
            continue
        if not slot.get("file"):
            # No media file attached â€” cannot publish
            continue
        try:
            slot_time = dt.datetime.strptime(slot["publishAtLocal"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        # BugÃ¼nkÃ¼ saat bazÄ±nda karÅŸÄ±laÅŸtÄ±r
        slot_time_naive = slot_time.replace(tzinfo=None)
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        diff = (now_naive - slot_time_naive).total_seconds()
        # Slot zamanÄ± geÃ§ti ama window_min dakikadan fazla geÃ§medi
        if 0 <= diff <= window_min * 60:
            result.append({**slot, "_slot_id": slot_id})
    return result


def _publish_state_path(slot: dict[str, Any]) -> Path:
    """Slot için publish state dosyasının yolunu döndür."""
    slot_id = _safe_slot_id(slot)
    return PUBLISH_STATE_DIR / f"{slot_id}.json"


def _already_published(slot: dict[str, Any]) -> bool:
    """Bu slot daha önce başarıyla publish oldu mu? (youtubeDone veya instagramDone varsa)"""
    state_path = _publish_state_path(slot)
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    # Worker state.json'da youtubeDone veya instagramDone varsa publish tamamlanmıştır
    for key in data:
        if key.endswith("Done") and isinstance(data[key], list) and len(data[key]) > 0:
            LOG.info("  Zaten publish olmuş (state=%s): %s", key, state_path.name)
            return True
    return False


def fire_slot(slot: dict[str, Any], dry_run: bool = False) -> bool:
    if audit_freeze_active():
        LOG.warning("Audit freeze active; slot skipped: %s", audit_freeze_reason())
        return False

    # Duplicate publish kontrolü — daha önce başarıyla publish olduysa atla
    if _already_published(slot):
        LOG.info("  Slot zaten publish olmuş, atlanıyor: %s", slot.get("_slot_id", ""))
        return True  # Başarısızlık değil, zaten yapılmış

    channel_id = slot.get("channel", "")
    worker_path = _channel_worker(channel_id)
    env = _slot_worker_env(channel_id, slot)
    LOG.info("Slot ateşleniyor: %s  %s  dosya=%s",
             channel_id, slot.get("publishAtLocal"), slot.get("file", ""))
    if worker_path.suffix.lower() == ".py":
        full_env = {**os.environ, **env}
        if dry_run:
            LOG.info("[dry-run] python %s", worker_path.name)
            return True
        result = subprocess.run(
            [sys.executable, str(worker_path)],
            cwd=str(worker_path.parent),
            env=full_env,
            text=True,
            timeout=3600,
        )
        if result.returncode != 0:
            LOG.warning("python worker cikis kodu %d: %s", result.returncode, worker_path.name)
            return False
        return True
    return run_node(worker_path, env=env, dry_run=dry_run)


# â”€â”€ yorum motoru â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â


# â”€â”€ ana dÃ¶ngÃ¼ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def cmd_start(args: argparse.Namespace) -> None:
    config = load_config()
    LOG.info("SMU Daemon baÅŸlatÄ±ldÄ± (dry_run=%s)", args.dry_run)

    while True:
        try:
            config = load_config()   # Her dÃ¶ngÃ¼de config'i yenile
            now = _now_local()

            if audit_freeze_active():
                LOG.warning("Audit freeze active; daemon waiting: %s", audit_freeze_reason())
                time.sleep(60)
                continue

            if in_no_post_window(config, now):
                secs = seconds_until_window_end(config)
                LOG.info("Uyku modu (01:00-07:00). BitiÅŸ: %ds sonra (%.1fh)",
                         secs, secs / 3600)
                _sleep_chunked(secs, label="uyku modu")
                continue

            state = load_daemon_state()

            # Sabah hazÄ±rlÄ±ÄŸÄ± (sadece gÃ¼n baÅŸÄ±nda bir kez)
            if not morning_prep_done_today(state):
                do_morning_prep(config, dry_run=args.dry_run)

            # GÃ¼n iÃ§i slot kontrolÃ¼
            run_daily_loop(config, dry_run=args.dry_run)

            # Yorum motoru (saatte en fazla 2 yorum)
            _run_comment_engine(config, dry_run=args.dry_run)

            # 01:00'e kaÃ§ saniye kaldÄ±?
            secs_to_sleep = seconds_until_no_post(config)
            if secs_to_sleep < 120:
                LOG.info("01:00 yaklaÅŸÄ±yor, kÄ±sa beklemeâ€¦")
                time.sleep(60)
            else:
                # 1 dakikada bir slot kontrol et
                time.sleep(60)

        except KeyboardInterrupt:
            LOG.info("Durduruldu (Ctrl+C)")
            break
        except Exception as exc:
            LOG.exception("Beklenmeyen hata: %s", exc)
            time.sleep(60)


def _sleep_chunked(total_seconds: int, label: str = "") -> None:
    """Uzun uyku â€” her 5 dakikada bir log atar, Ctrl+C'ye duyarlÄ±."""
    chunk = 300  # 5 dakika
    remaining = total_seconds
    while remaining > 0:
        wait = min(chunk, remaining)
        LOG.debug("  [%s] %ds dahaâ€¦", label, remaining)
        time.sleep(wait)
        remaining -= wait


# â”€â”€ diÄŸer komutlar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def cmd_status(args: argparse.Namespace) -> None:
    config = load_config()
    now = _now_local()
    is_sleep = in_no_post_window(config, now)

    print(f"Åu an (Istanbul): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    if audit_freeze_active():
        print(f"Mod: [AUDIT_FREEZE] {audit_freeze_reason()}")
    else:
        print(f"Mod: {'[UYKU 01:00-07:00]' if is_sleep else '[AKTIF]'}")

    if is_sleep:
        secs = seconds_until_window_end(config)
        print(f"Aktif olmaya: {secs // 3600}h {(secs % 3600) // 60}m")
    else:
        secs = seconds_until_no_post(config)
        print(f"Uyku moduna: {secs // 3600}h {(secs % 3600) // 60}m")

    state = load_daemon_state()
    print(f"Son sabah hazÄ±rlÄ±ÄŸÄ±: {state.get('last_morning_prep', 'yok')}")
    print(f"BugÃ¼n ateÅŸlenen slot: {len(state.get('last_slots_fired', []))}")

    schedule = load_today_schedule()
    if schedule:
        total = len(schedule.get("slots", []))
        scheduled = sum(1 for s in schedule.get("slots", []) if s.get("status") == "scheduled")
        print(f"BugÃ¼nkÃ¼ schedule: {total} slot, {scheduled} planlanmÄ±ÅŸ")
    else:
        print("BugÃ¼nkÃ¼ schedule yok")


def cmd_morning_prep(args: argparse.Namespace) -> None:
    config = load_config()
    do_morning_prep(config, dry_run=args.dry_run)


def cmd_next_event(args: argparse.Namespace) -> None:
    config = load_config()
    now = _now_local()

    if in_no_post_window(config, now):
        secs = seconds_until_window_end(config)
        print(f"Sonraki olay: Uyku bitti (07:00) â€” {secs // 60}dk sonra")
        return

    schedule = load_today_schedule()
    state = load_daemon_state()
    fired = state.get("last_slots_fired", [])

    next_slot = None
    next_time = None
    for slot in schedule.get("slots", []):
        slot_id = f"{slot['channel']}-slot{slot['slot']}"
        if slot_id in fired or slot.get("status") != "scheduled":
            continue
        try:
            t = dt.datetime.strptime(slot["publishAtLocal"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        if t < now.replace(tzinfo=None):
            continue
        if next_time is None or t < next_time:
            next_time = t
            next_slot = slot

    if next_slot is None:
        secs = seconds_until_no_post(config)
        print(f"Kalan slot yok. Uyku modu: {secs // 60}dk sonra")
    else:
        now_naive = now.replace(tzinfo=None)
        diff = (next_time - now_naive).total_seconds()  # type: ignore[operator]
        print(f"Sonraki slot: [{next_slot['channel']}] {next_slot['publishAtLocal']}  "
              f"({int(diff // 60)}dk {int(diff % 60)}sn sonra)")


# â”€â”€ CLI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMU Daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="24/7 daemon baÅŸlat")
    p.add_argument("--dry-run", action="store_true", help="GerÃ§ek action yapma")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("status", help="Daemon ve schedule durumu")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next-event", help="Bir sonraki olayÄ± gÃ¶ster")
    p.set_defaults(func=cmd_next_event)

    p = sub.add_parser("morning-prep", help="Sabah hazÄ±rlÄ±ÄŸÄ±nÄ± elle Ã§alÄ±ÅŸtÄ±r")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_morning_prep)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


def run_daily_loop(config: dict[str, Any], dry_run: bool = False) -> None:
    """Gün içi slot kontrolü: zamanı gelen slotları ateşle."""
    schedule = load_today_schedule()
    if not schedule:
        return

    state = load_daemon_state()
    fired: list[str] = state.get("last_slots_fired", [])

    due = slots_due_now(schedule, fired)
    if not due:
        return

    for slot in due:
        slot_id = slot["_slot_id"]
        LOG.info("Slot ateşleniyor: %s  %s", slot_id, slot.get("publishAtLocal", ""))
        ok = fire_slot(slot, dry_run=dry_run)
        if ok:
            fired.append(slot_id)
            state["last_slots_fired"] = fired
            save_daemon_state(state)
            LOG.info("Slot başarılı: %s", slot_id)
        else:
            LOG.warning("Slot başarısız: %s", slot_id)


def _run_comment_engine(config: dict[str, Any], dry_run: bool = False) -> None:
    """Yorum motoru: saatte en fazla 2 yorum taslağı oluştur.

    Son yorum turundan bu yana en az 30 dakika geçmiş olmalı.
    """
    state = load_daemon_state()
    last_round = state.get("last_comment_round", "")
    now = _now_local()

    # En az 30 dakika geçmiş mi kontrol et
    if last_round:
        try:
            last_dt = dt.datetime.fromisoformat(last_round)
            if (now - last_dt).total_seconds() < 1800:  # 30 dakika
                return
        except (ValueError, TypeError):
            pass

    # Yorum taslağı oluştur
    LOG.info("Yorum motoru çalıştırılıyor...")
    ok = run_python(
        [str(ROOT / "smu.py"), "generate-comments", "--max", "2"],
        dry_run=dry_run,
    )
    if ok:
        state["last_comment_round"] = now.isoformat(timespec="seconds")
        save_daemon_state(state)
        LOG.info("Yorum motoru tamamlandı")
    else:
        LOG.warning("Yorum motoru başarısız")


if __name__ == "__main__":
    raise SystemExit(main())
