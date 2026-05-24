#!/usr/bin/env python3
"""SMU: always-on social media unit planner.

This is the operations layer above content_ops.py:
- daily posting schedule
- safe no-post window
- comment draft queue
- morning runbook

It does not download unauthorized media, remove watermarks, or spam comments.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "smu_config.json"
SCHEDULE_DIR = ROOT / "schedules"
COMMENT_DIR = ROOT / "comments"
RUNBOOK_DIR = ROOT / "runbooks"
STATE_DIR = ROOT / "state"
JOB_DIR = ROOT / "jobs"
QUEUE_DIR = ROOT / "queues"
MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
DEFAULT_SLOT_MINUTES = [5, 25, 40]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def load_config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def parse_date(value: str | None) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def parse_hhmm(value: str) -> dt.time:
    hour, minute = value.split(":", 1)
    return dt.time(int(hour), int(minute))


def active_channels(config: dict[str, Any], include_disabled: bool = False) -> dict[str, dict[str, Any]]:
    channels = config["channels"]
    if include_disabled:
        return channels
    return {key: value for key, value in channels.items() if value.get("active")}


def publication_window(config: dict[str, Any], day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    no_post = config["noPostWindow"]
    if no_post.get("disabled", False):
        # No sleep window: gece de yayın var, 00:05'ten ertesi gün 00:05'e kadar
        start = dt.datetime.combine(day, dt.time(0, 5))
        end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0))
        return start, end
    start = dt.datetime.combine(day, parse_hhmm(no_post["end"]))
    end_time = parse_hhmm(no_post["start"])
    end_day = day + dt.timedelta(days=1)
    end = dt.datetime.combine(end_day, end_time)
    return start, end


def fixed_hourly_minutes(config: dict[str, Any], channel: dict[str, Any]) -> list[int]:
    cadence = channel.get("publishCadence") or config.get("publishCadence") or {}
    if cadence.get("mode") != "hourly_fixed_minutes":
        return []
    raw = cadence.get("minutes", DEFAULT_SLOT_MINUTES)
    minutes = sorted({int(value) for value in raw if 0 <= int(value) <= 59})
    return minutes or DEFAULT_SLOT_MINUTES


def make_slots(day: dt.date, config: dict[str, Any], channel_id: str, channel: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = publication_window(config, day)
    target = int(channel.get("dailyPostTarget", 10))
    minutes = fixed_hourly_minutes(config, channel)
    slots = []
    if minutes:
        current_hour = start.replace(minute=0, second=0, microsecond=0)
        while current_hour < end and len(slots) < target:
            for minute in minutes:
                when = current_hour.replace(minute=minute)
                if when < start or when >= end:
                    continue
                if len(slots) >= target:
                    break
                slots.append(
                    {
                        "slot": len(slots) + 1,
                        "channel": channel_id,
                        "browser": channel.get("browser", ""),
                        "publishAtLocal": when.strftime("%Y-%m-%d %H:%M"),
                        "status": "needs_queue_item",
                        "queueItemId": "",
                        "file": "",
                        "youtubeTitle": "",
                        "youtubeDescription": "",
                        "instagramCaption": "",
                        "tiktokCaption": "",
                        "notes": channel.get("notes", ""),
                    }
                )
            current_hour += dt.timedelta(hours=1)
        return slots

    offset = dt.timedelta(minutes=int(channel.get("slotOffsetMinutes", 0)))
    total_seconds = (end - start).total_seconds()
    step = total_seconds / target
    for index in range(target):
        when = start + offset + dt.timedelta(seconds=round(step * index))
        if when >= end:
            when = end - dt.timedelta(minutes=5)
        slots.append(
            {
                "slot": index + 1,
                "channel": channel_id,
                "browser": channel.get("browser", ""),
                "publishAtLocal": when.strftime("%Y-%m-%d %H:%M"),
                "status": "needs_queue_item",
                "queueItemId": "",
                "file": "",
                "youtubeTitle": "",
                "youtubeDescription": "",
                "instagramCaption": "",
                "tiktokCaption": "",
                "notes": channel.get("notes", ""),
            }
        )
    return slots


def schedule_path(day: dt.date) -> Path:
    return SCHEDULE_DIR / f"{day.isoformat()}_smu_schedule.json"


def comments_path(day: dt.date) -> Path:
    return COMMENT_DIR / f"{day.isoformat()}_comment_drafts.json"


def runbook_path(day: dt.date) -> Path:
    return RUNBOOK_DIR / f"{day.isoformat()}_morning_runbook.md"


def channel_job_path(day: dt.date, channel_id: str) -> Path:
    return JOB_DIR / f"{day.isoformat()}_{channel_id}_job.json"


def channel_queue_path(day: dt.date, channel_id: str) -> Path:
    return QUEUE_DIR / f"{day.isoformat()}_{channel_id}_queue.json"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def canonical_media_id(path: Path) -> str:
    value = slugify(path.stem)
    suffixes = [
        "-poster-loop-optimized",
        "-poster-loop",
        "-sahne-baddies",
        "-chatkesti",
        "-optimized",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if value.endswith(suffix):
                value = value[: -len(suffix)].strip("-")
                changed = True
    return value or slugify(path.stem)


def ready_buckets(channel: dict[str, Any]) -> list[Path]:
    configured = channel.get("readyBuckets") or channel.get("publishBuckets")
    if configured:
        return [Path(value) for value in configured]
    return [Path(channel.get("sourceBucket", ""))]


def published_ids_for_channel(channel: dict[str, Any]) -> set[str]:
    project_root = Path(channel.get("projectRoot", ""))
    if not project_root.exists():
        return set()
    ids: set[str] = set()
    for path in project_root.glob("automation/*state*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if not key.endswith("Done") or not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str) and item.strip():
                    ids.add(item.strip())
    return ids


def sidecar_candidates(source_path: Path, channel: dict[str, Any]) -> list[Path]:
    bucket = Path(channel.get("sourceBucket", ""))
    return [
        source_path.with_suffix(".json"),
        bucket / "metadata" / f"{source_path.stem}.json",
        bucket.parent / "metadata" / f"{source_path.stem}.json",
    ]


def load_sidecar(source_path: Path, channel: dict[str, Any]) -> dict[str, Any]:
    for candidate in sidecar_candidates(source_path, channel):
        if candidate.exists():
            try:
                data = read_json(candidate)
            except json.JSONDecodeError:
                return {"sidecar_error": f"invalid_json:{candidate}"}
            if isinstance(data, dict):
                data["sidecar_path"] = str(candidate)
                return data
    return {}


def infer_item(channel_id: str, channel: dict[str, Any], source_path: Path, rights: str) -> dict[str, Any]:
    meta = load_sidecar(source_path, channel)
    item_id = meta.get("id") or canonical_media_id(source_path)
    item: dict[str, Any] = {
        "id": item_id,
        "source_path": source_path.as_posix(),
        "file": source_path.as_posix(),
        "export_path": source_path.as_posix(),
        "source_rights": meta.get("source_rights") or meta.get("rights_status") or rights,
        "rights_note": meta.get("rights_note", ""),
        "source_link": meta.get("source_link", meta.get("url", "")),
    }
    if "sidecar_path" in meta:
        item["metadata_sidecar"] = meta["sidecar_path"]
    if "sidecar_error" in meta:
        item["metadata_error"] = meta["sidecar_error"]

    if channel_id == "poster_loop_cinema":
        item.update(
            {
                "film_hint": meta.get("film") or meta.get("film_hint") or meta.get("title") or source_path.stem,
                "year_hint": meta.get("year", ""),
                "director_hint": meta.get("director", ""),
                "summary_hint": meta.get("summary") or meta.get("plot") or meta.get("description") or "",
                "scene_hint": meta.get("scene") or meta.get("scene_hint") or "",
            }
        )
    elif channel_id == "sahnebaddiestr":
        item.update(
            {
                "person_hint": meta.get("person") or meta.get("celebrity") or meta.get("person_hint") or source_path.stem,
                "program_hint": meta.get("program") or meta.get("context") or meta.get("program_hint") or "",
                "hook": meta.get("hook") or meta.get("title") or "Bu sahnenin enerjisi ayri.",
                "scene_description": meta.get("scene_description") or meta.get("description") or "",
                "question": meta.get("question") or "Sence bu anin aurasi kac/10?",
            }
        )
    elif channel_id == "chatkesti":
        item.update(
            {
                "platform": meta.get("platform") or "",
                "streamer": meta.get("streamer") or meta.get("creator") or source_path.stem,
                "game": meta.get("game") or meta.get("context") or "",
                "hook": meta.get("hook") or meta.get("title") or "Yayin burada koptu.",
                "clip_description": meta.get("clip_description") or meta.get("description") or "",
                "question": meta.get("question") or "Bir sonraki hangi yayinci gelsin?",
            }
        )
    return item


def scan_channel_sources(
    channel_id: str,
    channel: dict[str, Any],
    limit: int,
    rights: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    buckets = ready_buckets(channel)
    files: list[Path] = []
    missing = 0
    for bucket in buckets:
        if not bucket.exists():
            missing += 1
            continue
        files.extend(
            path
            for path in bucket.rglob("*")
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        )
    published = published_ids_for_channel(channel)
    unique_files = {path.resolve(): path for path in files}.values()
    candidates = sorted(unique_files, key=lambda path: path.stat().st_mtime, reverse=True)
    selected: list[Path] = []
    skipped_published = 0
    for path in candidates:
        if canonical_media_id(path) in published:
            skipped_published += 1
            continue
        selected.append(path)
        if len(selected) >= limit:
            break
    items = [infer_item(channel_id, channel, path, rights) for path in selected]
    confirmed = sum(1 for item in items if str(item.get("source_rights")).lower() == "confirmed")
    return items, {
        "found": len(files),
        "selected": len(selected),
        "confirmed": confirmed,
        "unknown_or_hold": len(items) - confirmed,
        "skippedPublished": skipped_published,
        "missingBuckets": missing,
    }


def cmd_plan_day(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    channels = active_channels(config, include_disabled=args.include_disabled)
    schedule = {
        "system": config["name"],
        "date": day.isoformat(),
        "timezone": config["timezone"],
        "noPostWindow": config["noPostWindow"],
        "sourcePolicy": config["sourcePolicy"],
        "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
        "channels": {},
        "slots": [],
    }
    for channel_id, channel in channels.items():
        slots = make_slots(day, config, channel_id, channel)
        schedule["channels"][channel_id] = {
            "active": channel.get("active"),
            "browser": channel.get("browser"),
            "dailyPostTarget": channel.get("dailyPostTarget"),
            "sourceBucket": channel.get("sourceBucket"),
        }
        schedule["slots"].extend(slots)
    schedule["slots"].sort(key=lambda item: item["publishAtLocal"])
    out = Path(args.out) if args.out else schedule_path(day)
    write_json(out, schedule)
    print(out)
    print(f"slots={len(schedule['slots'])}")


def load_queue_items(path: Path) -> tuple[str, list[dict[str, Any]]]:
    data = read_json(path)
    if isinstance(data, list):
        return "", data
    return data.get("channel", ""), data.get("items", [])


def cmd_attach_queue(args: argparse.Namespace) -> None:
    schedule = read_json(Path(args.schedule))
    channel, queue_items = load_queue_items(Path(args.queue))
    if args.channel:
        channel = args.channel
    if not channel:
        raise SystemExit("Queue channel is missing; pass --channel.")
    # --force: replace ALL slots of this channel (including already-scheduled ones)
    # default: only fill slots that are still empty
    force = getattr(args, "force", False)
    if force:
        eligible_statuses = {"needs_queue_item", "scheduled", "blocked_legacy_smu_review", "queued"}
    else:
        eligible_statuses = {"needs_queue_item"}
    open_slots = [
        slot for slot in schedule["slots"]
        if slot["channel"] == channel and slot.get("status") in eligible_statuses
    ]

    # Duplicate queueItemId kontrolÃ¼: aynÄ± kanalda daha Ã¶nce eklenmiÅŸ queueItemId'leri bul
    existing_ids: set[str] = set()
    for slot in schedule["slots"]:
        if slot["channel"] == channel and slot.get("queueItemId"):
            existing_ids.add(slot["queueItemId"])

    # Duplicate file path kontrolÃ¼: aynÄ± kanalda daha Ã¶nce eklenmiÅŸ dosyalarÄ± bul
    existing_files: set[str] = set()
    for slot in schedule["slots"]:
        if slot["channel"] == channel and slot.get("file"):
            existing_files.add(slot["file"])

    attached = 0
    skipped_duplicate_id = 0
    skipped_duplicate_file = 0
    for slot, item in zip(open_slots, queue_items):
        item_id = item.get("id", "")
        item_file = item.get("file", "")

        # AynÄ± queueItemId daha Ã¶nce eklenmiÅŸse atla
        if item_id and item_id in existing_ids:
            skipped_duplicate_id += 1
            continue

        # AynÄ± dosya yolu daha Ã¶nce eklenmiÅŸse atla
        if item_file and item_file in existing_files:
            skipped_duplicate_file += 1
            continue

        slot["status"] = "scheduled"
        slot["queueItemId"] = item_id
        slot["file"] = item_file
        slot["youtubeTitle"] = item.get("youtubeTitle", "")
        slot["youtubeDescription"] = item.get("youtubeDescription", "")
        slot["instagramCaption"] = item.get("instagramCaption", "")
        slot["tiktokCaption"] = item.get("tiktokCaption", "")
        attached += 1
        if item_id:
            existing_ids.add(item_id)
        if item_file:
            existing_files.add(item_file)

    out = Path(args.out) if args.out else Path(args.schedule)
    write_json(out, schedule)
    print(out)
    print(f"attached={attached} channel={channel} force={force} "
          f"skipped_duplicate_id={skipped_duplicate_id} "
          f"skipped_duplicate_file={skipped_duplicate_file}")



def rotate(values: list[str], count: int) -> list[str]:
    if not values:
        return []
    return [values[index % len(values)] for index in range(count)]


def cmd_comment_plan(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    channels = active_channels(config, include_disabled=args.include_disabled)
    drafts = {
        "system": config["name"],
        "date": day.isoformat(),
        "timezone": config["timezone"],
        "mode": "manual_drafts_only",
        "rules": [
            "No links.",
            "No copy-paste spam.",
            "Do not insult, harass, or target private life.",
            "Post manually after checking the account and context.",
        ],
        "channels": {},
    }
    for channel_id, channel in channels.items():
        target = int(channel.get("dailyCommentDraftTarget", 10))
        account_target = int(channel.get("dailyAccountDiscoveryTarget", 10))
        templates = config["commentTemplates"].get(channel_id, [])
        comments = rotate(templates, target)
        drafts["channels"][channel_id] = {
            "browser": channel.get("browser"),
            "accountDiscoveryTarget": account_target,
            "commentDraftTarget": target,
            "targetAccounts": [
                {
                    "account": "",
                    "url": "",
                    "topic": "",
                    "status": "find_manually",
                }
                for _ in range(account_target)
            ],
            "drafts": [
                {
                    "comment": comment,
                    "status": "draft",
                    "usedOn": "",
                    "note": "Use only if it fits the actual post."
                }
                for comment in comments
            ],
        }
    out = Path(args.out) if args.out else comments_path(day)
    write_json(out, drafts)
    print(out)


def cmd_morning_runbook(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    channels = active_channels(config)
    lines = [
        f"# SMU Morning Runbook - {day.isoformat()}",
        "",
        f"Timezone: `{config['timezone']}`",
        f"No-post window: `{config['noPostWindow']['start']}` - `{config['noPostWindow']['end']}`",
        f"Cadence: hourly fixed minutes `{', '.join(str(v).zfill(2) for v in (config.get('publishCadence', {}).get('minutes') or DEFAULT_SLOT_MINUTES))}`",
        "",
        "## Rules",
        "",
        "- Only rights-confirmed sources enter the publish queue.",
        "- Do not remove, hide, or crop out watermarks to disguise source ownership.",
        "- Comments are manual drafts, not spam automation.",
        "- ChatKesti stays disabled until its separate workflow is finalized.",
        "",
        "## Browser Map",
        "",
        "- Chrome: Poster Loop Cinema",
        "- Edge: SahneBaddiesTR",
        "- Firefox: ChatKesti",
        "",
        "## Start",
        "",
        "```powershell",
        "cd C:\\Users\\User\\.codex\\content-ops",
        "python content_ops.py launch-browsers --channel all",
        f"python smu.py plan-day --date {day.isoformat()}",
        f"python smu.py comment-plan --date {day.isoformat()}",
        "```",
        "",
        "## Channel Targets",
        "",
    ]
    for channel_id, channel in channels.items():
        lines.extend(
            [
                f"### {channel_id}",
                "",
                f"- Browser: `{channel.get('browser')}`",
                f"- Daily videos: `{channel.get('dailyPostTarget')}`",
                f"- Comment drafts: `{channel.get('dailyCommentDraftTarget')}`",
                f"- Source bucket: `{channel.get('sourceBucket')}`",
                f"- Ready buckets: `{', '.join(channel.get('readyBuckets') or channel.get('publishBuckets') or [channel.get('sourceBucket', '')])}`",
                f"- Notes: {channel.get('notes')}",
                "",
            ]
        )
    out = Path(args.out) if args.out else runbook_path(day)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    schedule = schedule_path(day)
    comments = comments_path(day)
    runbook = runbook_path(day)
    print(f"SMU={config['name']} timezone={config['timezone']}")
    for channel_id, channel in config["channels"].items():
        state = "active" if channel.get("active") else "disabled"
        print(f"{channel_id}: {state} browser={channel.get('browser')} dailyPostTarget={channel.get('dailyPostTarget')}")
    print(f"schedule_exists={schedule.exists()} {schedule}")
    print(f"comments_exists={comments.exists()} {comments}")
    print(f"runbook_exists={runbook.exists()} {runbook}")


def cmd_intake(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    channels = config["channels"]
    channel = channels.get(args.channel)
    if not channel:
        raise SystemExit(f"Unknown channel: {args.channel}")
    if not channel.get("active") and not args.include_disabled:
        raise SystemExit(f"Channel is disabled: {args.channel}")
    limit = args.limit or int(channel.get("dailyPostTarget", 10))
    rights = "confirmed" if args.assume_confirmed else "unknown"
    items, stats = scan_channel_sources(args.channel, channel, limit, rights)
    job = {
        "today": day.isoformat(),
        "mode": "batch",
        "platform": "all",
        "source_rights": rights,
        "batch": day.isoformat(),
        "channel": args.channel,
        "sourceBucket": channel.get("sourceBucket"),
        "sourceStats": stats,
        "items": items,
    }
    out = Path(args.out) if args.out else channel_job_path(day, args.channel)
    write_json(out, job)
    print(out)
    print(f"items={len(items)} stats={stats}")


def run_content_ops(channel_id: str, job_path: Path, queue_path: Path, providers: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "content_ops.py"),
        "run",
        "--channel",
        channel_id,
        "--items",
        str(job_path),
        "--providers",
        providers,
        "--out",
        str(queue_path),
    ]
    subprocess.run(command, cwd=str(ROOT), check=True)


def cmd_prepare_day(args: argparse.Namespace) -> None:
    config = load_config()
    day = parse_date(args.date)
    channels = active_channels(config)
    schedule = schedule_path(day)
    comments = comments_path(day)
    runbook = runbook_path(day)

    class Obj:
        pass

    plan_args = Obj()
    plan_args.date = day.isoformat()
    plan_args.out = str(schedule)
    plan_args.include_disabled = False
    cmd_plan_day(plan_args)  # type: ignore[arg-type]

    comment_args = Obj()
    comment_args.date = day.isoformat()
    comment_args.out = str(comments)
    comment_args.include_disabled = False
    cmd_comment_plan(comment_args)  # type: ignore[arg-type]

    runbook_args = Obj()
    runbook_args.date = day.isoformat()
    runbook_args.out = str(runbook)
    cmd_morning_runbook(runbook_args)  # type: ignore[arg-type]

    prepared: list[dict[str, Any]] = []
    for channel_id, channel in channels.items():
        limit = args.limit or int(channel.get("dailyPostTarget", 10))
        rights = "confirmed" if args.assume_confirmed else "unknown"
        items, stats = scan_channel_sources(channel_id, channel, limit, rights)
        job = {
            "today": day.isoformat(),
            "mode": "batch",
            "platform": "all",
            "source_rights": rights,
            "batch": day.isoformat(),
            "channel": channel_id,
            "sourceBucket": channel.get("sourceBucket"),
            "sourceStats": stats,
            "items": items,
        }
        job_path = channel_job_path(day, channel_id)
        queue_path = channel_queue_path(day, channel_id)
        write_json(job_path, job)
        if items:
            run_content_ops(channel_id, job_path, queue_path, args.providers)
            attach_args = Obj()
            attach_args.schedule = str(schedule)
            attach_args.queue = str(queue_path)
            attach_args.channel = channel_id
            attach_args.out = str(schedule)
            cmd_attach_queue(attach_args)  # type: ignore[arg-type]
        prepared.append(
            {
                "channel": channel_id,
                "job": str(job_path),
                "queue": str(queue_path) if items else "",
                "items": len(items),
                "stats": stats,
            }
        )

    report = {
        "system": config["name"],
        "date": day.isoformat(),
        "assumeConfirmed": args.assume_confirmed,
        "providers": args.providers,
        "schedule": str(schedule),
        "comments": str(comments),
        "runbook": str(runbook),
        "prepared": prepared,
    }
    report_path = STATE_DIR / f"{day.isoformat()}_prepare_report.json"
    write_json(report_path, report)
    print(report_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMU planner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan-day", help="Create daily posting schedule")
    p.add_argument("--date", default="")
    p.add_argument("--out", default="")
    p.add_argument("--include-disabled", action="store_true")
    p.set_defaults(func=cmd_plan_day)

    p = sub.add_parser("attach-queue", help="Attach content_ops queue items to schedule slots")
    p.add_argument("--schedule", required=True)
    p.add_argument("--queue", required=True)
    p.add_argument("--channel", default="")
    p.add_argument("--out", default="")
    p.add_argument("--force", action="store_true", help="Replace all channel slots, including already-scheduled ones")
    p.set_defaults(func=cmd_attach_queue)

    p = sub.add_parser("comment-plan", help="Create manual comment draft plan")
    p.add_argument("--date", default="")
    p.add_argument("--out", default="")
    p.add_argument("--include-disabled", action="store_true")
    p.set_defaults(func=cmd_comment_plan)

    p = sub.add_parser("morning-runbook", help="Create daily operator runbook")
    p.add_argument("--date", default="")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_morning_runbook)

    p = sub.add_parser("status", help="Show SMU status")
    p.add_argument("--date", default="")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("intake", help="Scan a channel source bucket and create a daily job file")
    p.add_argument("--channel", required=True)
    p.add_argument("--date", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default="")
    p.add_argument("--assume-confirmed", action="store_true", help="Mark local source bucket files as rights-confirmed")
    p.add_argument("--include-disabled", action="store_true")
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("prepare-day", help="Create schedule, comments, runbook, jobs and queues for active channels")
    p.add_argument("--date", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--providers", default="cache,template")
    p.add_argument("--assume-confirmed", action="store_true", help="Mark local source bucket files as rights-confirmed")
    p.set_defaults(func=cmd_prepare_day)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
