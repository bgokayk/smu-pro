#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import time
import webbrowser
import datetime as dt
import socket
import re
from pathlib import Path
from threading import Thread
from flask import Flask, jsonify, render_template_string

# ---------- Sabitler ----------
ROOT = Path(__file__).parent
SCHEDULE_FILE = ROOT / "schedules" / f"{time.strftime('%Y-%m-%d')}_smu_schedule.json"
DAEMON_SCRIPT = ROOT / "smu_daemon.py"
COMMENT_FILE = ROOT / "comments" / f"{time.strftime('%Y-%m-%d')}_comment_drafts.json"
LOG_FILE = ROOT / "logs" / "smu_daemon.log"
CONFIG_FILE = ROOT / "smu_config.json"
PUBLISHED_REGISTRY_FILE = ROOT / "published_registry.json"
PUBLISHED_LEDGER_FILE = ROOT / "state" / "published_ledger.json"
COMMENT_STATE_FILE = ROOT / "state" / "comment_state.json"
FIREFOX_PROFILE = Path(r"C:\Users\User\.codex\browser-profiles\chatkesti-firefox")
MODERN_TEMPLATE = (ROOT / "dashboard_template.html").read_text(encoding="utf-8")

# ---------- Flask Uygulaması ----------
app = Flask(__name__)

def _today_istanbul() -> str:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(tz=ZoneInfo("Europe/Istanbul")).date().isoformat()
    except Exception:
        return (dt.datetime.utcnow() + dt.timedelta(hours=3)).date().isoformat()


def _istanbul_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Istanbul")
    except Exception:
        return None


def _now_local() -> dt.datetime:
    tz = _istanbul_tz()
    if tz:
        return dt.datetime.now(tz=tz)
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def _parse_local_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    tz = _istanbul_tz()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz) if tz else parsed
    return parsed.astimezone(tz) if tz else parsed


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return default


def _latest_daily_file(folder: str, suffix: str) -> Path:
    directory = ROOT / folder
    today_file = directory / f"{_today_istanbul()}{suffix}"
    if today_file.exists():
        return today_file
    files = sorted(directory.glob(f"*{suffix}")) if directory.exists() else []
    return files[-1] if files else today_file


def _schedule_path() -> Path:
    return _latest_daily_file("schedules", "_smu_schedule.json")


def _comment_path() -> Path:
    return _latest_daily_file("comments", "_comment_drafts.json")


def _follower_counts():
    data = get_follower_data()
    return {
        key: int(value.get("followers", 0)) if isinstance(value, dict) else int(value or 0)
        for key, value in data.items()
    }


def _public_slot(slot: dict) -> dict:
    title = slot.get("youtubeTitle") or slot.get("title") or ""
    publish_at = slot.get("publishAtLocal") or ""
    return {
        "slot": slot.get("slot"),
        "time": publish_at[11:16] if len(publish_at) >= 16 else "",
        "channel": slot.get("channel", ""),
        "title": title,
        "youtubeTitle": title,
        "publishAtLocal": publish_at,
        "status": slot.get("status", ""),
        "queueItemId": slot.get("queueItemId", ""),
    }


def _read_published_ledger() -> list[dict]:
    data = _read_json(PUBLISHED_LEDGER_FILE, [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("entries", [])
    return []


def _count_by_channel(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        channel = item.get("channel") or "unknown"
        counts[channel] = counts.get(channel, 0) + 1
    return counts


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _firefox_profile_running(profile_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -like 'firefox*' -and $_.CommandLine -like '*chatkesti-firefox*' } | "
                "Select-Object -First 1 -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False

# ---------- Örnek Takipçi Verileri (şimdilik statik, gerçek API ile değiştirilebilir) ----------
def get_follower_data():
    # Bu kısmı Instagram ve YouTube API ile değiştirebiliriz.
    # Şimdilik örnek veri.
    return {
        "poster_loop_cinema": {"name": "Poster Loop Cinema", "handle": "@posterloopcinema", "followers": 12450, "weekly_growth": 842, "history": [11800, 11950, 12100, 12220, 12340, 12400, 12450]},
        "sahnebaddiestr": {"name": "Sahne Baddies TR", "handle": "@sahnebaddiestr", "followers": 8760, "weekly_growth": 320, "history": [8320, 8410, 8500, 8590, 8650, 8700, 8760]},
        "chatkesti": {"name": "ChatKesti", "handle": "@chatkesti", "followers": 15230, "weekly_growth": 1210, "history": [13800, 14100, 14450, 14780, 14990, 15120, 15230]}
    }

# ---------- Yardımcı: Stock sayıları ----------
def _count_files(directory: Path, pattern: str = "*.mp4") -> int:
    """Belirtilen dizindeki dosya sayısını döndür."""
    try:
        return len(list(directory.glob(pattern)))
    except Exception:
        return 0

def _get_stock_data():
    """Her kanal için kaynak/render/queue sayılarını döndür."""
    config = _read_json(CONFIG_FILE, {})
    channels = config.get('channels', {})
    stock = {}
    for ch_id, ch_cfg in channels.items():
        source_dir = Path(ch_cfg.get('sourceBucket', ''))
        ready_dirs = ch_cfg.get('readyBuckets', [])
        source_count = _count_files(source_dir)
        render_count = sum(_count_files(Path(d)) for d in ready_dirs)
        # Queue sayısı
        queue_file = ROOT / "queues" / f"{_today_istanbul()}_{ch_id}_queue.json"
        queue_data = _read_json(queue_file, {})
        queue_count = len(queue_data.get('queue', [])) if isinstance(queue_data, dict) else 0
        stock[ch_id] = {
            "source": source_count,
            "render": render_count,
            "queue": queue_count
        }
    return stock

def _get_pipeline_status():
    """Pipeline durumunu döndür (hangi kanal hangi aşamada)."""
    # Basit mantık: queue'su olan kanal "publish" aşamasında
    # source'u olan "download", render'ı olan "render"
    stock = _get_stock_data()
    status = {}
    for ch_id, data in stock.items():
        if data["queue"] > 0:
            status[ch_id] = "publish"
        elif data["render"] > 0:
            status[ch_id] = "render"
        elif data["source"] > 0:
            status[ch_id] = "download"
        else:
            status[ch_id] = "idle"
    return status

# ---------- API Uç Noktaları ----------
@app.route('/api/schedule')
def api_schedule():
    data = _read_json(_schedule_path(), {})
    return jsonify(data.get('slots', []))

@app.route('/api/followers')
def api_followers():
    return jsonify(_follower_counts())

@app.route('/api/comments')
def api_comments():
    return jsonify(_read_json(_comment_path(), {}))

@app.route('/api/logs')
def api_logs():
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-100:]
        return jsonify({'logs': [line.rstrip('\n') for line in lines]})
    return jsonify({'logs': []})


@app.route('/api/data')
def api_data():
    schedule = _read_json(_schedule_path(), {})
    comments = _read_json(_comment_path(), {})
    return jsonify({'schedule': schedule, 'comments': comments})

@app.route('/api/stock')
def api_stock():
    """Kaynak/render/queue sayıları"""
    return jsonify(_get_stock_data())

@app.route('/api/pipeline')
def api_pipeline():
    """Pipeline durumu"""
    stock = _get_stock_data()
    status = _get_pipeline_status()
    return jsonify({"stock": stock, "status": status})

@app.route('/api/cline-log')
def api_cline_log():
    """Cline pipeline log içeriği"""
    cline_log = ROOT / "logs" / "cline_pipeline.md"
    if cline_log.exists():
        return jsonify({"content": cline_log.read_text(encoding="utf-8")})
    return jsonify({"content": "Cline log bulunamadı."})

@app.route('/api/codex-log')
def api_codex_log():
    """Codex pipeline log içeriği"""
    codex_log = ROOT / "logs" / "codex_pipeline.md"
    if codex_log.exists():
        return jsonify({"content": codex_log.read_text(encoding="utf-8")})
    return jsonify({"content": "Codex log bulunamadı."})

@app.route('/api/next-slots')
def api_next_slots():
    """Sıradaki 5 slot"""
    schedule = _read_json(_schedule_path(), {})
    slots = schedule.get('slots', [])
    now = _now_local()
    
    future_slots = []
    for s in slots:
        t = _parse_local_datetime(s.get('publishAtLocal'))
        if t and t > now:
            future_slots.append(s)
    
    future_slots.sort(key=lambda x: x.get('publishAtLocal', ''))
    return jsonify([_public_slot(slot) for slot in future_slots[:5]])


@app.route('/api/today-stats')
def api_today_stats():
    """Bugunku hedef vs gercek + sonraki paylasim."""
    target_total = 30  # 10/kanal x 3
    now = _now_local()
    today = _today_istanbul()
    sched_path = ROOT / "schedules" / f"{today}_smu_schedule.json"
    slots = []
    try:
        if sched_path.exists():
            slots = json.loads(sched_path.read_text(encoding="utf-8-sig")).get("slots", [])
    except Exception:
        pass

    now_str = now.strftime("%Y-%m-%d %H:%M")
    future = [s for s in slots if s.get("publishAtLocal", "") >= now_str]
    past = [s for s in slots if s.get("publishAtLocal", "") < now_str]
    next_slot = future[0] if future else None

    # Bugun yayinlanan (ledger)
    entries = _read_published_ledger()
    today_pub = sum(1 for e in entries
                    if _parse_local_datetime(e.get("publishedAt"))
                    and _parse_local_datetime(e.get("publishedAt")).date().isoformat() == today)

    by_ch_today = {}
    for s in slots:
        ch = s.get("channel", "?")
        by_ch_today[ch] = by_ch_today.get(ch, 0) + 1

    return jsonify({
        "targetTotal": target_total,
        "scheduledSlots": len(slots),
        "passedSlots": len(past),
        "futureSlots": len(future),
        "todayPublished": today_pub,
        "remainingTarget": max(target_total - today_pub, 0),
        "byChannel": by_ch_today,
        "nextSlot": {
            "time": next_slot.get("publishAtLocal") if next_slot else None,
            "channel": next_slot.get("channel") if next_slot else None,
            "title": (next_slot.get("youtubeTitle", "")[:80]) if next_slot else None,
        } if next_slot else None,
    })


@app.route('/api/cadence-stats')
def api_cadence_stats():
    """Son 1 saat yayin cadence metrigi."""
    target_per_hour = 5
    now = _now_local()
    window_start = now - dt.timedelta(hours=1)
    entries = _read_published_ledger()

    recent = []
    today_entries = []
    for entry in entries:
        published_at = _parse_local_datetime(entry.get("publishedAt"))
        if not published_at:
            continue
        if published_at.date().isoformat() == _today_istanbul():
            today_entries.append(entry)
        if window_start <= published_at <= now:
            recent.append(entry)

    registry = _read_json(PUBLISHED_REGISTRY_FILE, {})
    registry_counts = {
        channel: len(ids) for channel, ids in registry.items() if isinstance(ids, list)
    } if isinstance(registry, dict) else {}
    actual = len(recent)

    return jsonify({
        "targetPerHour": target_per_hour,
        "actualLastHour": actual,
        "remainingToTarget": max(target_per_hour - actual, 0),
        "status": "ok" if actual >= target_per_hour else "behind",
        "windowStart": window_start.isoformat(timespec="seconds"),
        "windowEnd": now.isoformat(timespec="seconds"),
        "todayPublished": len(today_entries),
        "byChannelLastHour": _count_by_channel(recent),
        "publishedRegistryTotal": sum(registry_counts.values()),
        "publishedRegistryByChannel": registry_counts,
        "source": "state/published_ledger.json",
    })


@app.route('/api/comment-stats')
def api_comment_stats():
    """Yorum motoru state metrigi."""
    target_per_hour = 5
    now = _now_local()
    window_start = now - dt.timedelta(hours=1)
    state = _read_json(COMMENT_STATE_FILE, {})
    comments = state.get("posted_comments", []) if isinstance(state, dict) else []

    recent = []
    for comment in comments:
        posted_at = _parse_local_datetime(comment.get("posted_at"))
        if posted_at and window_start <= posted_at <= now:
            recent.append(comment)

    return jsonify({
        "targetPerHour": target_per_hour,
        "postedLastHour": len(recent),
        "remainingToTarget": max(target_per_hour - len(recent), 0),
        "totalPosted": len(comments),
        "lastPostTime": state.get("last_post_time", "") if isinstance(state, dict) else "",
        "byChannelLastHour": _count_by_channel(recent),
        "stateExists": COMMENT_STATE_FILE.exists(),
        "windowStart": window_start.isoformat(timespec="seconds"),
        "windowEnd": now.isoformat(timespec="seconds"),
    })


@app.route('/api/dedup-stats')
def api_dedup_stats():
    """Bugunku global dedup engel sayisi."""
    today = _today_istanbul()
    events = []
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            if "GLOBAL DEDUP engellendi" not in line or not line.startswith(f"[{today}"):
                continue
            match = re.search(
                r"^\[(?P<ts>[^\]]+)\].*GLOBAL DEDUP engellendi: (?P<item>.*?) zaten .*?\(kanal: (?P<channel>.*?)\)",
                line,
            )
            if match:
                events.append(match.groupdict())
            else:
                events.append({"ts": line[1:20], "item": "", "channel": "unknown"})

    by_channel: dict[str, int] = {}
    for event in events:
        channel = event.get("channel") or "unknown"
        by_channel[channel] = by_channel.get(channel, 0) + 1

    return jsonify({
        "today": today,
        "globalDedupBlockedToday": len(events),
        "byChannel": by_channel,
        "lastEvents": events[-5:],
        "source": "logs/smu_daemon.log",
    })


@app.route('/api/browser-health')
def api_browser_health():
    """Browser debug port ve Firefox profile sagligi."""
    chrome_online = _port_open(9222)
    edge_online = _port_open(9223)
    firefox_exists = FIREFOX_PROFILE.exists()
    firefox_running = _firefox_profile_running(FIREFOX_PROFILE)

    def badge(ok: bool) -> str:
        return "online" if ok else "offline"

    return jsonify({
        "chrome9222": {
            "label": "Chrome 9222",
            "port": 9222,
            "ok": chrome_online,
            "status": badge(chrome_online),
        },
        "edge9223": {
            "label": "Edge 9223",
            "port": 9223,
            "ok": edge_online,
            "status": badge(edge_online),
        },
        "firefox": {
            "label": "Firefox chatkesti",
            "profile": str(FIREFOX_PROFILE),
            "profileExists": firefox_exists,
            "running": firefox_running,
            "ok": firefox_exists,
            "status": "running" if firefox_running else ("profile-ready" if firefox_exists else "missing"),
        },
    })

@app.route('/')
def index():
    schedule = _read_json(_schedule_path(), {})
    config = _read_json(CONFIG_FILE, {})
    return render_template_string(
        MODERN_TEMPLATE,
        schedule_json=json.dumps({'slots': schedule.get('slots', [])}, ensure_ascii=False),
        followers_json=json.dumps(_follower_counts(), ensure_ascii=False),
        comment_templates=json.dumps(config.get('commentTemplates', {}), ensure_ascii=False),
    )

# ---------- HTML Şablonu (Güncellenmiş Dashboard) ----------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMU Pro Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/remixicon@4.3.0/fonts/remixicon.css" rel="stylesheet">
    <style>
        body { background: #0a0c0f; font-family: system-ui, -apple-system, sans-serif; }
        .sidebar { background: #0f1115; border-right: 1px solid #1e2229; }
        .card { background: #13161c; border: 1px solid #1e2229; border-radius: 20px; transition: all 0.2s; }
        .card:hover { border-color: #2d3748; }
        .stat-value { font-size: 2rem; font-weight: 800; }
        .menu-item { transition: all 0.2s; border-radius: 12px; cursor: pointer; }
        .menu-item:hover { background: #1a1f2a; }
        .active-menu { background: #1e2a3a; color: #60a5fa; }
        .slot-row:hover { background: #1a1f2a; }
        .badge { background: #1a3a2a; color: #4caf50; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
    </style>
</head>
<body class="text-gray-200">
<div class="flex min-h-screen">
    <aside class="sidebar w-64 p-5 hidden md:block">
        <div class="flex items-center gap-2 mb-8"><div class="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl"></div><span class="text-xl font-bold">SMU<span class="text-blue-400"> Pro</span></span></div>
        <nav class="space-y-1">
            <div class="menu-item active-menu px-4 py-2.5 flex items-center gap-3 text-sm" data-page="dashboard"><i class="ri-dashboard-line"></i> Kontrol Paneli</div>
            <div class="menu-item px-4 py-2.5 flex items-center gap-3 text-sm text-gray-400" data-page="schedule"><i class="ri-calendar-line"></i> Yayın Takvimi</div>
            <div class="menu-item px-4 py-2.5 flex items-center gap-3 text-sm text-gray-400" data-page="comments"><i class="ri-chat-3-line"></i> Yorum Planı</div>
            <div class="menu-item px-4 py-2.5 flex items-center gap-3 text-sm text-gray-400" data-page="logs"><i class="ri-pulse-line"></i> Log Kayıtları</div>
        </nav>
        <div class="absolute bottom-6 text-xs text-gray-600">v2.0 · 7/24 Aktif</div>
    </aside>

    <main class="flex-1 p-5 md:p-7">
        <div class="flex flex-wrap justify-between items-center mb-6">
            <div><h1 class="text-2xl font-bold" id="pageTitle">Kontrol Paneli</h1><p class="text-gray-400 text-sm" id="pageDesc">Tüm otomasyon süreçleriniz buradan yönetilir.</p></div>
            <div class="flex items-center gap-3"><div class="bg-gray-800/50 rounded-full px-3 py-1 text-xs"><i class="ri-chat-check-line mr-1"></i> AI Aktif</div></div>
        </div>

        <div id="dashboardView">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-7" id="stats"></div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-7" id="channels"></div>
            <div class="card p-0 overflow-hidden mb-7">
                <div class="px-5 py-3 border-b border-gray-800 flex justify-between items-center">
                    <h2 class="font-semibold"><i class="ri-table-line mr-2"></i>Bugünün Yayın Takvimi</h2>
                    <span class="text-xs text-gray-500" id="scheduleCount">0 slot</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead class="bg-gray-800/40 text-gray-300 text-xs"><tr><th class="px-4 py-2 text-left">Saat</th><th class="px-4 py-2 text-left">Kanal</th><th class="px-4 py-2 text-left">Kalan Süre</th><th class="px-4 py-2 text-left">YouTube Başlık</th><th class="px-4 py-2 text-left">Instagram Caption</th><th class="px-4 py-2 text-left">Durum</th></tr></thead>
                        <tbody id="scheduleBody"></tbody>
                    </table>
                </div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-7">
                <div class="card p-4">
                    <h2 class="font-semibold mb-3"><i class="ri-heart-line"></i> Anlık Takipçi Sayıları</h2>
                    <div id="followerStats" class="space-y-4"></div>
                </div>
                <div class="card p-4">
                    <h2 class="font-semibold mb-3"><i class="ri-line-chart-line"></i> Son 7 Gün Takipçi Artışı</h2>
                    <canvas id="growthChart" width="400" height="200" style="max-height: 200px;"></canvas>
                </div>
            </div>
        </div>
        <div id="otherView" class="hidden"></div>
    </main>
</div>

<script>
    let growthChart = null;

    async function fetchJSON(url) {
        const res = await fetch(url);
        return res.json();
    }

    async function updateDashboard() {
        const slots = await fetchJSON('/api/schedule');
        const followers = await fetchJSON('/api/followers');
        const now = new Date();
        const published = slots.filter(s => new Date(s.publishAtLocal) < now).length;
        const planned = slots.filter(s => new Date(s.publishAtLocal) >= now).length;
        document.getElementById('stats').innerHTML = `
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-calendar-check-line"></i> Yayınlanan</div><div class="stat-value">${published}</div><div class="text-green-400 text-xs mt-1">bugün</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-time-line"></i> Planlanan</div><div class="stat-value">${planned}</div><div class="text-blue-400 text-xs mt-1">kalan</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-checkbox-circle-line"></i> Başarı Oranı</div><div class="stat-value">98%</div><div class="text-gray-500 text-xs mt-1">son 24s</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-error-warning-line"></i> Hata</div><div class="stat-value">0</div><div class="text-red-400 text-xs mt-1">otomatik düzeltme</div></div>
        `;

        const channelMap = { poster_loop_cinema: 'Poster Loop Cinema', sahnebaddiestr: 'Sahne Baddies TR', chatkesti: 'ChatKesti' };
        const colors = { poster_loop_cinema: 'blue', sahnebaddiestr: 'orange', chatkesti: 'green' };
        let channelsHtml = '';
        for (const [id, name] of Object.entries(channelMap)) {
            const done = slots.filter(s => s.channel === id && new Date(s.publishAtLocal) < now).length;
            const percent = (done / 30) * 100;
            channelsHtml += `<div class="card p-4"><div><div class="font-semibold">${name}</div><div class="text-2xl font-bold mt-1">${done}/30</div><div class="text-xs text-gray-400">yayınlandı</div></div><div class="w-full bg-gray-800 rounded-full h-1.5 mt-3"><div class="bg-${colors[id]}-500 h-1.5 rounded-full" style="width:${percent}%"></div></div></div>`;
        }
        document.getElementById('channels').innerHTML = channelsHtml;

        const tbody = slots.map(slot => {
            const slotTime = new Date(slot.publishAtLocal);
            const diff = Math.floor((slotTime - now) / 60000);
            const timeText = diff > 0 ? `${diff}dk sonra` : `${Math.abs(diff)}dk önce`;
            let channelName = slot.channel === 'poster_loop_cinema' ? 'Poster Loop' : (slot.channel === 'sahnebaddiestr' ? 'Baddies' : 'ChatKesti');
            return `<tr class="slot-row border-t border-gray-800"><td class="px-4 py-2 text-xs font-mono">${slot.publishAtLocal.slice(11,16)}</td><td class="px-4 py-2 text-xs">${channelName}</td><td class="px-4 py-2 text-xs ${diff>0?'text-blue-400':'text-gray-400'}">${timeText}</td><td class="px-4 py-2 text-xs truncate max-w-[200px]">${slot.youtubeTitle || '-'}</td><td class="px-4 py-2 text-xs truncate max-w-[200px]">${slot.instagramCaption || '-'}</td><td class="px-4 py-2"><span class="badge">Planlı</span></td></tr>`;
        }).join('');
        document.getElementById('scheduleBody').innerHTML = tbody || '<tr><td colspan="6" class="text-center py-6 text-gray-500">Takvim boş</td></tr>';
        document.getElementById('scheduleCount').innerText = `${slots.length} slot`;

        // Takipçi istatistikleri
        let followerHtml = '';
        for (const [key, data] of Object.entries(followers)) {
            const growthPercent = (data.weekly_growth / (data.followers - data.weekly_growth) * 100).toFixed(1);
            followerHtml += `
                <div class="flex justify-between items-center border-b border-gray-800 pb-2">
                    <div><div class="font-semibold">${data.name}</div><div class="text-xs text-gray-400">${data.handle}</div></div>
                    <div class="text-right"><div class="text-xl font-bold">${data.followers.toLocaleString()}</div><div class="text-xs text-green-400">+${data.weekly_growth} (${growthPercent}%) bu hafta</div></div>
                </div>
            `;
        }
        document.getElementById('followerStats').innerHTML = followerHtml;

        // Grafik
        if (growthChart) growthChart.destroy();
        const ctx = document.getElementById('growthChart').getContext('2d');
        const labels = ['-7', '-6', '-5', '-4', '-3', '-2', 'Bugün'];
        const datasets = [];
        for (const [key, data] of Object.entries(followers)) {
            let color = key === 'poster_loop_cinema' ? '#3b82f6' : (key === 'sahnebaddiestr' ? '#f97316' : '#22c55e');
            datasets.push({ label: data.name, data: data.history, borderColor: color, backgroundColor: 'transparent', tension: 0.3, fill: false });
        }
        growthChart = new Chart(ctx, { type: 'line', data: { labels, datasets }, options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { position: 'top', labels: { color: '#ccc' } } } } });
    }

    // Menü geçişleri
    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', () => {
            const page = item.getAttribute('data-page');
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active-menu'));
            item.classList.add('active-menu');
            if (page === 'dashboard') {
                document.getElementById('dashboardView').classList.remove('hidden');
                document.getElementById('otherView').classList.add('hidden');
                document.getElementById('pageTitle').innerText = 'Kontrol Paneli';
                document.getElementById('pageDesc').innerText = 'Tüm otomasyon süreçleriniz buradan yönetilir.';
                updateDashboard();
            } else if (page === 'comments') {
                document.getElementById('dashboardView').classList.add('hidden');
                document.getElementById('otherView').classList.remove('hidden');
                fetchJSON('/api/comments').then(data => {
                    let html = '<div class="card p-4"><h2 class="font-semibold mb-3">Yorum Planı</h2>';
                    for (const [ch, val] of Object.entries(data.channels || {})) {
                        html += `<div class="mb-4"><div class="font-bold">${ch}</div><ul class="list-disc pl-5">`;
                        (val.drafts || []).forEach(d => html += `<li>${d.comment} (${d.status})</li>`);
                        html += `</ul></div>`;
                    }
                    html += '</div>';
                    document.getElementById('otherView').innerHTML = html;
                });
                document.getElementById('pageTitle').innerText = 'Yorum Planı';
                document.getElementById('pageDesc').innerText = 'Hazırlanan yorum taslakları.';
            } else if (page === 'logs') {
                document.getElementById('dashboardView').classList.add('hidden');
                document.getElementById('otherView').classList.remove('hidden');
                fetchJSON('/api/logs').then(data => {
                    document.getElementById('otherView').innerHTML = `<div class="card p-4"><h2 class="font-semibold mb-3">Son Loglar</h2><pre class="text-xs bg-black p-2 rounded overflow-auto max-h-96">${data.logs}</pre></div>`;
                });
                document.getElementById('pageTitle').innerText = 'Log Kayıtları';
                document.getElementById('pageDesc').innerText = 'Daemon ve worker logları.';
            } else {
                document.getElementById('dashboardView').classList.add('hidden');
                document.getElementById('otherView').classList.remove('hidden');
                document.getElementById('otherView').innerHTML = `<div class="card p-8 text-center text-gray-400"><i class="ri-information-line text-4xl"></i><p class="mt-2">${item.innerText.trim()} sayfası hazırlanıyor.</p></div>`;
                document.getElementById('pageTitle').innerText = item.innerText.trim();
                document.getElementById('pageDesc').innerText = 'Bu bölüm yakında aktif olacak.';
            }
        });
    });

    updateDashboard();
    setInterval(updateDashboard, 30000);
</script>
</body>
</html>
'''

# ---------- Daemon'u Arka Planda Başlat ----------
def start_daemon():
    # Daemon zaten çalışıyor mu? tasklist komut satırını göstermediği için
    # Win32_Process üzerinden kontrol ediyoruz.
    try:
        result = subprocess.run(
            [
                'powershell',
                '-NoProfile',
                '-Command',
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -match 'smu_daemon.py' -and $_.CommandLine -match ' start' } | "
                "Select-Object -First 1 -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if not result.stdout.strip():
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.Popen([sys.executable, str(DAEMON_SCRIPT), 'start'], cwd=ROOT, creationflags=creationflags)
            time.sleep(2)
    except Exception:
        pass


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(('127.0.0.1', port)) != 0


def _pick_dashboard_port(preferred: int = 5000) -> int:
    if _port_available(preferred):
        return preferred
    for port in range(preferred + 1, preferred + 20):
        if _port_available(port):
            return port
    return preferred


# ---------- Ana Fonksiyon ----------
def main():
    start_daemon()
    preferred_port = int(os.environ.get('SMU_DASHBOARD_PORT', '5000'))
    port = _pick_dashboard_port(preferred_port)

    # Flask'ı ayrı bir thread'de başlat
    def run_flask():
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
    Thread(target=run_flask, daemon=True).start()
    # Tarayıcıyı aç
    url = f'http://127.0.0.1:{port}'
    webbrowser.open(url)
    print(f"SMU Pro Dashboard başlatıldı: {url}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Kapatılıyor...")
        sys.exit(0)

if __name__ == '__main__':
    main()
