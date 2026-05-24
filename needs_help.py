#!/usr/bin/env python3
"""SMU Yardım Kuyruğu — sistem takıldığında AI'ya iletilecek görevler.

Sistem bir şeyi yapamadığında needs_help.json'a yazar.
Claude Code veya Codex session başında bunu okur ve halleder.

Kullanım:
  python needs_help.py list          # Bekleyen görevleri göster
  python needs_help.py add ...       # Elle görev ekle (sistem tarafından da çağrılır)
  python needs_help.py resolve <id>  # Görevi tamamlandı işaretle
  python needs_help.py context       # AI'ya yapıştırılacak context üret
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HELP_FILE = ROOT / "state" / "needs_help.json"

PRIORITIES = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def read_all() -> list[dict[str, Any]]:
    if not HELP_FILE.exists():
        return []
    try:
        return json.loads(HELP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def write_all(items: list[dict[str, Any]]) -> None:
    HELP_FILE.parent.mkdir(parents=True, exist_ok=True)
    HELP_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_task(
    category: str,
    title: str,
    detail: str = "",
    channel: str = "",
    priority: str = "medium",
    context: dict[str, Any] | None = None,
) -> str:
    """Yardım kuyruğuna görev ekle. Sistem otomatik çağırır."""
    items = read_all()
    task_id = uuid.uuid4().hex[:8]
    items.append({
        "id": task_id,
        "status": "pending",
        "priority": priority,
        "category": category,
        "channel": channel,
        "title": title,
        "detail": detail,
        "context": context or {},
        "created_at": _now(),
        "resolved_at": "",
        "resolved_by": "",
    })
    # Öncelik sırasına göre sırala
    items.sort(key=lambda x: PRIORITIES.get(x.get("priority", "medium"), 2))
    write_all(items)
    return task_id


def resolve_task(task_id: str, resolved_by: str = "ai") -> bool:
    items = read_all()
    for item in items:
        if item["id"] == task_id:
            item["status"] = "resolved"
            item["resolved_at"] = _now()
            item["resolved_by"] = resolved_by
            write_all(items)
            return True
    return False


def pending_tasks() -> list[dict[str, Any]]:
    return [t for t in read_all() if t.get("status") == "pending"]


# ── AI context üretici ────────────────────────────────────────────────────────

AI_CONTEXT_TEMPLATE = """\
# SMU — Bekleyen Görevler ({count} adet)

Sen SMU (Social Media Unit) sisteminin AI asistanısın.
Aşağıdaki görevler sistem tarafından otomatik oluşturuldu — elle müdahale gerekenler.

Kanal haritası:
  poster_loop_cinema → Chrome, port 9222
  sahnebaddiestr     → Edge, port 9223
  chatkesti          → (gelecek)

Proje kökleri:
  PosterLoop : C:/Users/User/.codex/analog-neo-moving-poster/
  BaddiesTR  : C:/Users/User/.codex/sahne-baddies-auto/
  ChatKesti  : C:/Users/User/.codex/yayinci-kesitleri-auto/
  SMU ops    : C:/Users/User/.codex/content-ops/

## Bekleyen Görevler

{tasks}

## Tamamlayınca
Her görevi bitirince: python needs_help.py resolve <id>
"""


def generate_context() -> str:
    tasks = pending_tasks()
    if not tasks:
        return "# SMU — Bekleyen görev yok, sistem normal çalışıyor."

    lines = []
    for task in tasks:
        lines.append(
            f"### [{task['id']}] [{task['priority'].upper()}] {task['title']}\n"
            f"Kanal: {task['channel'] or 'genel'}  |  Kategori: {task['category']}\n"
            f"{task['detail']}\n"
        )
        if task.get("context"):
            lines.append(f"Bağlam: {json.dumps(task['context'], ensure_ascii=False)}\n")

    return AI_CONTEXT_TEMPLATE.format(
        count=len(tasks),
        tasks="\n".join(lines),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    tasks = pending_tasks() if not args.all else read_all()
    if not tasks:
        print("Bekleyen görev yok.")
        return
    for task in tasks:
        status = task.get("status", "pending")
        print(f"[{task['id']}] [{task['priority']}] [{status}] {task['title']}")
        if task.get("detail"):
            print(f"  {task['detail'][:100]}")


def cmd_add(args: argparse.Namespace) -> None:
    task_id = add_task(
        category=args.category,
        title=args.title,
        detail=args.detail,
        channel=args.channel,
        priority=args.priority,
    )
    print(f"Eklendi: {task_id}")


def cmd_resolve(args: argparse.Namespace) -> None:
    ok = resolve_task(args.id, resolved_by=args.by)
    print("Tamam." if ok else f"Bulunamadi: {args.id}")


def cmd_context(args: argparse.Namespace) -> None:
    print(generate_context())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMU yardım kuyruğu")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="Bekleyen görevleri listele")
    p.add_argument("--all", action="store_true", help="Tamamlananları da göster")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="Görev ekle")
    p.add_argument("--category", default="manual", help="download|identify|publish|comment|other")
    p.add_argument("--title", required=True)
    p.add_argument("--detail", default="")
    p.add_argument("--channel", default="")
    p.add_argument("--priority", default="medium", choices=["critical", "high", "medium", "low"])
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("resolve", help="Görevi tamamlandı işaretle")
    p.add_argument("id")
    p.add_argument("--by", default="ai")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("context", help="AI'ya yapıştırılacak context üret")
    p.set_defaults(func=cmd_context)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
