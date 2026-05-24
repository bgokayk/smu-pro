#!/usr/bin/env python3
"""SMU Dashboard â€” tarayÄ±cÄ±da aÃ§Ä±lan gÃ¶rsel kontrol paneli.

KullanÄ±m:
  python dashboard.py          # http://localhost:8765 aÃ§ar
  python dashboard.py --port 9000
"""

from __future__ import annotations

import datetime as dt
import http.server, sys; sys.stdout.reconfigure(encoding="utf-8")
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SCHEDULE_DIR  = ROOT / "schedules"
COMMENT_DIR   = ROOT / "comments"
STATE_DIR     = ROOT / "state"
DAEMON_STATE  = STATE_DIR / "daemon_state.json"
HELP_FILE     = STATE_DIR / "needs_help.json"
CONFIG_FILE   = ROOT / "smu_config.json"


# â”€â”€ veri okuma â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def rj(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def today_str() -> str:
    return dt.date.today().isoformat()


def now_local() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(tz=ZoneInfo("Europe/Istanbul"))
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)


def get_schedule() -> dict[str, Any]:
    path = SCHEDULE_DIR / f"{today_str()}_smu_schedule.json"
    return rj(path) or {}


def get_comments() -> dict[str, Any]:
    path = COMMENT_DIR / f"{today_str()}_comment_drafts.json"
    return rj(path) or {}


def get_daemon_state() -> dict[str, Any]:
    return rj(DAEMON_STATE) or {}


def get_help_tasks() -> list[dict[str, Any]]:
    data = rj(HELP_FILE) or []
    return [t for t in data if t.get("status") == "pending"]


def get_config() -> dict[str, Any]:
    return rj(CONFIG_FILE) or {}


def in_sleep_window(config: dict[str, Any]) -> bool:
    t = now_local().time()
    try:
        s = dt.time(*map(int, config["noPostWindow"]["start"].split(":")))
        e = dt.time(*map(int, config["noPostWindow"]["end"].split(":")))
        return s <= t < e
    except Exception:
        return False


# â”€â”€ HTML Ã¼retici â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

CHANNEL_COLORS = {
    "poster_loop_cinema": "#3e9a9b",
    "sahnebaddiestr":     "#c65d35",
    "chatkesti":          "#71883f",
}
CHANNEL_LABELS = {
    "poster_loop_cinema": "Poster Loop Cinema",
    "sahnebaddiestr":     "Sahne Baddies TR",
    "chatkesti":          "ChatKesti",
}
PLATFORM_ICONS = {
    "youtube": "YT",
    "instagram": "IG",
}


def _slot_status_badge(status: str, slot_id: str, fired: list[str]) -> str:
    if slot_id in fired:
        return '<span class="badge done">YAYINLANDI</span>'
    if status == "scheduled":
        return '<span class="badge scheduled">PLANLI</span>'
    return '<span class="badge needs">KUYRUK YOK</span>'


def _time_diff(slot_time_str: str) -> str:
    try:
        st = dt.datetime.strptime(slot_time_str, "%Y-%m-%d %H:%M")
        now = now_local().replace(tzinfo=None)
        diff = (st - now).total_seconds()
        if diff < 0:
            return f"{int(-diff // 60)}dk Ã¶nce"
        h, m = int(diff // 3600), int((diff % 3600) // 60)
        return f"{h}s {m}dk sonra" if h else f"{m}dk sonra"
    except Exception:
        return ""


def build_html() -> str:
    config    = get_config()
    schedule  = get_schedule()
    comments  = get_comments()
    daemon    = get_daemon_state()
    help_tasks = get_help_tasks()
    now        = now_local()
    sleeping   = in_sleep_window(config)
    fired      = daemon.get("last_slots_fired", [])

    slots = schedule.get("slots", [])
    total_slots     = len(slots)
    done_slots      = sum(1 for s in slots if f"{s['channel']}-slot{s['slot']}" in fired)
    pending_slots   = sum(1 for s in slots if s.get("status") == "scheduled" and f"{s['channel']}-slot{s['slot']}" not in fired)

    # â”€â”€ durum banner â”€â”€
    if sleeping:
        mode_cls = "mode-sleep"
        mode_txt = "UYKU MODU â€” 01:00â€“07:00"
    else:
        mode_cls = "mode-active"
        mode_txt = "AKTIF"

    # â”€â”€ slot satÄ±rlarÄ± â”€â”€
    slot_rows = ""
    for s in sorted(slots, key=lambda x: x.get("publishAtLocal", "")):
        ch     = s.get("channel", "")
        color  = CHANNEL_COLORS.get(ch, "#888")
        label  = CHANNEL_LABELS.get(ch, ch)
        slot_id = f"{ch}-slot{s['slot']}"
        badge  = _slot_status_badge(s.get("status", ""), slot_id, fired)
        diff   = _time_diff(s.get("publishAtLocal", ""))
        file_  = Path(s.get("file", "")).name or "â€”"
        yt_title = (s.get("youtubeTitle") or "â€”")[:60]
        ig_cap   = (s.get("instagramCaption") or "â€”")[:60]
        slot_rows += f"""
        <tr>
          <td><span class="dot" style="background:{color}"></span> {label}</td>
          <td class="mono">{s.get("publishAtLocal","")}</td>
          <td class="dim">{diff}</td>
          <td class="file">{file_}</td>
          <td class="caption" title="{yt_title}">YT: {yt_title}</td>
          <td class="caption" title="{ig_cap}">IG: {ig_cap}</td>
          <td>{badge}</td>
        </tr>"""

    if not slot_rows:
        slot_rows = '<tr><td colspan="7" class="empty">BugÃ¼n iÃ§in takvim yok â€” daemon sabah hazÄ±rlÄ±ÄŸÄ±nÄ± yaptÄ± mÄ±?</td></tr>'

    # â”€â”€ yorum bÃ¶lÃ¼mÃ¼ â”€â”€
    comment_sections = ""
    for ch_id, ch_data in comments.get("channels", {}).items():
        color = CHANNEL_COLORS.get(ch_id, "#888")
        label = CHANNEL_LABELS.get(ch_id, ch_id)
        drafts = ch_data.get("drafts", [])
        target_count = ch_data.get("accountDiscoveryTarget", 0)

        draft_rows = "".join(
            f'<li class="comment-draft">{d["comment"]} '
            f'<span class="badge-small {d.get("status","draft")}">{d.get("status","draft")}</span></li>'
            for d in drafts[:5]
        )
        comment_sections += f"""
        <div class="comment-block" style="border-left:3px solid {color}">
          <div class="comment-header">
            <span class="dot" style="background:{color}"></span>
            <strong>{label}</strong>
            <span class="dim">â€” {len(drafts)} yorum taslaÄŸÄ± / {target_count} hesap hedef</span>
          </div>
          <ul>{draft_rows}</ul>
          {f'<p class="dim">... ve {len(drafts)-5} tane daha</p>' if len(drafts)>5 else ""}
        </div>"""

    if not comment_sections:
        comment_sections = '<p class="empty">Yorum planÄ± yok.</p>'

    # â”€â”€ yardÄ±m kuyrugu â”€â”€
    help_html = ""
    if help_tasks:
        rows = "".join(
            f'<tr class="help-row"><td>[{t["id"]}]</td>'
            f'<td><span class="priority-{t.get("priority","medium")}">{t.get("priority","").upper()}</span></td>'
            f'<td>{t.get("channel","â€”")}</td>'
            f'<td>{t["title"]}</td>'
            f'<td class="dim">{t.get("detail","")[:80]}</td></tr>'
            for t in help_tasks
        )
        help_html = f"""
        <div class="section help-section">
          <h2>YardÄ±m Gerekiyor ({len(help_tasks)})</h2>
          <p class="dim">Claude Code veya Codex'te: <code>python needs_help.py context</code></p>
          <table><tr><th>#</th><th>Ã–ncelik</th><th>Kanal</th><th>GÃ¶rev</th><th>Detay</th></tr>
          {rows}</table>
        </div>"""

    # â”€â”€ kanal Ã¶zeti â”€â”€
    ch_summary = ""
    for ch_id, ch_cfg in config.get("channels", {}).items():
        if not ch_cfg.get("active"):
            continue
        color = CHANNEL_COLORS.get(ch_id, "#888")
        label = CHANNEL_LABELS.get(ch_id, ch_id)
        ch_slots = [s for s in slots if s.get("channel") == ch_id]
        ch_done  = sum(1 for s in ch_slots if f"{s['channel']}-slot{s['slot']}" in fired)
        ch_total = len(ch_slots)
        pct = int(ch_done / ch_total * 100) if ch_total else 0
        bucket = Path(ch_cfg.get("sourceBucket",""))
        exts = {".mp4",".mov",".mkv",".webm",".m4v"}
        src_count = sum(1 for f in bucket.iterdir() if f.suffix.lower() in exts) if bucket.exists() else 0
        ch_summary += f"""
        <div class="channel-card" style="border-top:3px solid {color}">
          <div class="ch-name" style="color:{color}">{label}</div>
          <div class="ch-stat">{ch_done}/{ch_total} yayÄ±nlandÄ±</div>
          <div class="progress-bar"><div class="progress-fill" style="width:{pct}%;background:{color}"></div></div>
          <div class="ch-stat dim">{src_count} kaynak video mevcut</div>
          <div class="ch-stat dim">TarayÄ±cÄ±: {ch_cfg.get("browser","?")}</div>
        </div>"""

    last_prep = daemon.get("last_morning_prep","") or "HenÃ¼z yapÄ±lmadÄ±"

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<title>SMU Dashboard</title>
<style>
  :root {{
    --bg: #0f0f0f; --surface: #1a1a1a; --border: #2a2a2a;
    --text: #e8e8e6; --dim: #7a7a78; --accent: #3e9a9b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; line-height: 1.5; }}
  header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ font-size: 16px; font-weight: 700; letter-spacing: 2px; color: var(--accent); }}
  .mode-pill {{ padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
  .mode-active {{ background: #1a3a2a; color: #4caf50; }}
  .mode-sleep  {{ background: #2a2a3a; color: #7986cb; }}
  .timestamp {{ color: var(--dim); margin-left: auto; font-size: 11px; }}
  main {{ padding: 20px 24px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .stat-num {{ font-size: 28px; font-weight: 700; }}
  .stat-label {{ color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }}
  .channel-cards {{ display: flex; gap: 12px; margin-bottom: 20px; }}
  .channel-card {{ flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .ch-name {{ font-weight: 700; font-size: 13px; margin-bottom: 6px; }}
  .ch-stat {{ font-size: 12px; margin-top: 4px; }}
  .progress-bar {{ background: #222; border-radius: 4px; height: 4px; margin: 8px 0; overflow: hidden; }}
  .progress-fill {{ height: 100%; border-radius: 4px; transition: width .3s; }}
  .section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
  .section h2 {{ font-size: 13px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; padding: 4px 8px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #1f1f1f; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1f1f1f; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; }}
  .done      {{ background: #1a3a2a; color: #4caf50; }}
  .scheduled {{ background: #1a2a3a; color: #42a5f5; }}
  .needs     {{ background: #3a2a1a; color: #ff9800; }}
  .badge-small {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; }}
  .draft   {{ background: #2a2a2a; color: #aaa; }}
  .used    {{ background: #1a3a2a; color: #4caf50; }}
  .mono {{ font-family: monospace; font-size: 12px; }}
  .dim {{ color: var(--dim); }}
  .file {{ font-size: 11px; color: #aaa; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .caption {{ font-size: 11px; color: #bbb; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .empty {{ color: var(--dim); text-align: center; padding: 20px; font-style: italic; }}
  .comment-block {{ background: #161616; border-radius: 6px; padding: 12px; margin-bottom: 10px; }}
  .comment-header {{ margin-bottom: 8px; }}
  .comment-block ul {{ padding-left: 16px; }}
  .comment-block li {{ margin: 4px 0; font-size: 12px; color: #ccc; }}
  .help-section {{ border: 1px solid #3a2010; }}
  .help-section h2 {{ color: #ff7043; }}
  .help-row {{ background: #1a1008; }}
  .priority-critical {{ color: #f44336; font-weight: 700; }}
  .priority-high    {{ color: #ff9800; font-weight: 700; }}
  .priority-medium  {{ color: #ffeb3b; }}
  .priority-low     {{ color: #aaa; }}
  code {{ background: #222; padding: 1px 5px; border-radius: 3px; font-size: 11px; }}
  .refresh-note {{ color: var(--dim); font-size: 11px; margin-top: 12px; text-align: center; }}
</style>
</head>
<body>
<header>
  <h1>SMU</h1>
  <span class="mode-pill {mode_cls}">{mode_txt}</span>
  <span class="timestamp">
    {now.strftime("%d %b %Y, %H:%M:%S")} Istanbul &nbsp;|&nbsp;
    Son hazÄ±rlÄ±k: {last_prep[:16] if len(last_prep) > 10 else last_prep}
  </span>
</header>

<main>

<!-- KPI kartlarÄ± -->
<div class="grid-3">
  <div class="stat-card">
    <div class="stat-num">{done_slots}</div>
    <div class="stat-label">BugÃ¼n YayÄ±nlanan</div>
  </div>
  <div class="stat-card">
    <div class="stat-num">{pending_slots}</div>
    <div class="stat-label">SÄ±rada Bekleyen</div>
  </div>
  <div class="stat-card">
    <div class="stat-num" style="color:{'#f44336' if help_tasks else '#4caf50'}">{len(help_tasks)}</div>
    <div class="stat-label">YardÄ±m Gerekiyor</div>
  </div>
</div>

<!-- Kanal kartlarÄ± -->
<div class="channel-cards">
  {ch_summary or '<p class="dim">Aktif kanal yok.</p>'}
</div>

{help_html}

<!-- BugÃ¼nkÃ¼ yayÄ±n takvimi -->
<div class="section">
  <h2>BugÃ¼nkÃ¼ YayÄ±n Takvimi â€” {today_str()}</h2>
  <table>
    <tr>
      <th>Kanal</th>
      <th>Saat</th>
      <th>Ne Zaman</th>
      <th>Dosya</th>
      <th>YouTube BaÅŸlÄ±k</th>
      <th>Instagram Caption</th>
      <th>Durum</th>
    </tr>
    {slot_rows}
  </table>
</div>

<!-- Yorum planÄ± -->
<div class="section">
  <h2>BugÃ¼nkÃ¼ Yorum PlanÄ±</h2>
  {comment_sections}
</div>

<p class="refresh-note">Her 30 saniyede otomatik yenilenir &bull; <code>python dashboard.py</code></p>
</main>
</body>
</html>"""


# â”€â”€ HTTP sunucusu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass  # konsol kirliliÄŸi olmasÄ±n

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/data":
            payload = json.dumps({
                "schedule": get_schedule(),
                "comments": get_comments(),
                "daemon":   get_daemon_state(),
                "help":     get_help_tasks(),
            }, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
            return

        # Ana sayfa
        html = build_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="SMU Dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # UTF-8 konsol
    import io
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    url = f"http://localhost:{args.port}"
    server = http.server.HTTPServer(("", args.port), Handler)
    print(f"SMU Dashboard â†’ {url}")
    print("Durdurmak iÃ§in: Ctrl+C")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDurduruldu.")


if __name__ == "__main__":
    main()



