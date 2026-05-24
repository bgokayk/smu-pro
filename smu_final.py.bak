#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Final Dashboard — Flask tabanlı canlı dashboard.

Özellikler:
- Gelecek yayınlar (scheduled/queued) ve geçmiş yayınlar (published/failed) ayrı listelenir
- Anlık takipçi sayıları (YouTube API + Instagram API)
- Yorum motoru tetikleme endpoint'i
- Log görüntüleme
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

ROOT = Path(__file__).parent
SCHEDULE_FILE = ROOT / "schedules" / f"{time.strftime('%Y-%m-%d')}_smu_schedule.json"
COMMENTS_FILE = ROOT / "comments" / f"{time.strftime('%Y-%m-%d')}_comment_drafts.json"
CONFIG_FILE = ROOT / "smu_config.json"
LOG_FILE = ROOT / "logs" / "smu_daemon.log"

# HTML template'i ayrı dosyadan oku
HTML_TEMPLATE = (ROOT / "dashboard_template.html").read_text(encoding="utf-8")

app = Flask(__name__)


def load_schedule() -> list[dict[str, Any]]:
    if SCHEDULE_FILE.exists():
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding='utf-8-sig'))
            return data.get('slots', [])
        except Exception as e:
            print(f"load_schedule error: {e}")
            return []
    return []


def load_comments() -> dict[str, Any]:
    if COMMENTS_FILE.exists():
        try:
            return json.loads(COMMENTS_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def load_logs() -> list[str]:
    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text(encoding='utf-8').splitlines()
            return lines[-50:]
        except Exception:
            return []
    return []


def get_followers_stats() -> dict[str, int]:
    """Takipçi istatistiklerini content_ops.py üzerinden al."""
    try:
        from content_ops import get_followers_stats as _get_followers
        return _get_followers()
    except Exception:
        pass
    # Fallback: son bilinen değerler
    try:
        from content_ops import _load_last_known_followers
        return _load_last_known_followers()
    except Exception:
        return {
            "poster_loop_cinema": 12450,
            "sahnebaddiestr": 8760,
            "chatkesti": 15230,
        }


@app.route('/')
def dashboard():
    all_slots = load_schedule()
    config = load_config()
    comment_templates = config.get('commentTemplates', {})

    # Gelecek slotlar (scheduled veya queued)
    future_slots = [
        s for s in all_slots
        if s.get('status') in ['scheduled', 'queued']
    ]
    # Geçmiş slotlar (published veya failed)
    past_slots = [
        s for s in all_slots
        if s.get('status') in ['published', 'failed']
    ]

    # Takipçi verisi
    followers = get_followers_stats()

    schedule_json = json.dumps({"slots": future_slots, "past_slots": past_slots}, ensure_ascii=False)
    templates_json = json.dumps(comment_templates, ensure_ascii=False)
    followers_json = json.dumps(followers, ensure_ascii=False)

    return render_template_string(
        HTML_TEMPLATE,
        schedule_json=schedule_json,
        comment_templates=templates_json,
        followers_json=followers_json,
    )


@app.route('/api/data')
def api_data():
    all_slots = load_schedule()
    future_slots = [
        s for s in all_slots
        if s.get('status') in ['scheduled', 'queued']
    ]
    past_slots = [
        s for s in all_slots
        if s.get('status') in ['published', 'failed']
    ]
    return jsonify({"slots": future_slots, "past_slots": past_slots})


@app.route('/api/followers')
def api_followers():
    try:
        stats = get_followers_stats()
        return jsonify(stats)
    except Exception:
        return jsonify({
            "poster_loop_cinema": 12450,
            "sahnebaddiestr": 8760,
            "chatkesti": 15230,
        })


@app.route('/api/comments')
def api_comments():
    data = load_comments()
    return jsonify(data)


@app.route('/api/logs')
def api_logs():
    logs = load_logs()
    return jsonify({"logs": logs, "total": len(logs)})


@app.route('/api/comment', methods=['POST'])
def trigger_comment():
    """Worker'lardan yorum motorunu tetiklemek için endpoint.

    POST JSON:
        {
            "video_id": "VIDEO_ID",
            "channel": "poster_loop_cinema",
            "metadata": {"film": "Inception", ...}
        }
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    video_id = data.get('video_id', '')
    channel = data.get('channel', '')
    metadata = data.get('metadata', {})

    if not video_id or not channel:
        return jsonify({"status": "error", "message": "video_id and channel required"}), 400

    try:
        from comment_engine import CommentEngine, load_config as _load_comment_config
        config = _load_comment_config()
        engine = CommentEngine(config)
        result = engine.post_youtube_comment(video_id, channel, metadata)
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/notify', methods=['POST'])
def notify_publish():
    """Worker'lardan bildirim tetiklemek için endpoint.

    POST JSON:
        {
            "title": "Inception (2010) – Rüya Sahnesi",
            "channel": "poster_loop_cinema",
            "url": "https://youtube.com/watch?v=..."
        }
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    title = data.get('title', 'Bilinmeyen')
    channel = data.get('channel', 'Bilinmeyen')
    url = data.get('url', '#')

    message = f"✅ Yeni paylaşım: {title}\n📺 Kanal: {channel}\n🔗 {url}"

    # Config'i yükle
    config = load_config()

    # Telegram bildirimi
    try:
        from notifiers.telegram_notifier import TelegramNotifier
        tg_config = config.get('telegram', {})
        tg = TelegramNotifier(tg_config.get('bot_token', ''), tg_config.get('chat_id', ''))
        tg.send_message(message)
    except Exception as e:
        print(f"Telegram bildirim hatası: {e}")

    # Discord bildirimi
    try:
        from notifiers.discord_notifier import DiscordNotifier
        discord_webhook = config.get('discord_webhook_url', '')
        if discord_webhook:
            dc = DiscordNotifier(discord_webhook)
            dc.send(message)
    except Exception as e:
        print(f"Discord bildirim hatası: {e}")

    return jsonify({"status": "ok", "message": "Bildirimler gönderildi"})


def start_daemon():
    """Daemon'u arka planda başlat (bloklamaz)."""
    daemon_script = ROOT / "smu_daemon.py"
    if daemon_script.exists():
        try:
            subprocess.Popen(
                [sys.executable, str(daemon_script), 'start'],
                cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"Daemon başlatılamadı: {e}")


if __name__ == '__main__':
    # Daemon'u arka planda başlat (başarısız olursa Flask yine de çalışır)
    try:
        start_daemon()
    except Exception:
        pass
    webbrowser.open('http://localhost:5000')
    app.run(host='127.0.0.1', port=5000, debug=False)
