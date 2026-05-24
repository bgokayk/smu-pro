import json
import os
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify

ROOT = Path(__file__).parent
app = Flask(__name__)


# -------------------- Loaders --------------------

def _read_json(path, default=None):
    """Tek bir noktada güvenli JSON okuma — BOM destekli."""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception as e:
        print(f"JSON okuma hatası ({path}): {e}")
        return default if default is not None else {}


def load_schedule_slots():
    """
    schedules/{today}_smu_schedule.json içinden slot listesini al.
    Bu liste gerçek publishAtLocal, status, queueItemId içerir.
    """
    today = time.strftime('%Y-%m-%d')
    schedule_path = ROOT / 'schedules' / f'{today}_smu_schedule.json'
    if not schedule_path.exists():
        return []
    data = _read_json(schedule_path, {})
    return data.get('slots', []) if isinstance(data, dict) else []


def normalize(item, idx):
    """Eksik alanları doldur — gerçek veri varsa dokunma."""
    if item.get('status') in ('ready', 'queued', 'pending', None):
        item['status'] = 'scheduled'
    if not item.get('publishAtLocal'):
        batch = item.get('batch', datetime.now().strftime('%Y-%m-%d'))
        h, m = 9 + (idx // 60), idx % 60
        item['publishAtLocal'] = f"{batch} {h:02d}:{m:02d}"
    return item


def load_queue_slots():
    """Fallback: schedule yoksa queue dosyalarından oku."""
    slots = []
    queue_dir = ROOT / 'queues'
    if not queue_dir.exists():
        return slots
    for fname in sorted(os.listdir(queue_dir)):
        if not fname.endswith('.json'):
            continue
        data = _read_json(queue_dir / fname, {})
        raw = []
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            items = data.get('items', [])
            if isinstance(items, list):
                raw = items
        for item in raw:
            slots.append(normalize(dict(item), len(slots)))
    return slots


def load_all_slots():
    """Önce schedule'ı dene (gerçek saatler), yoksa queue'ya düş."""
    slots = load_schedule_slots()
    if slots:
        return [normalize(dict(s), i) for i, s in enumerate(slots)]
    return load_queue_slots()


def split_slots(slots):
    """Gelecek (scheduled) vs geçmiş (published/failed) ayır."""
    future = [s for s in slots if s.get('status') in ('scheduled', 'queued', 'ready')]
    past = [s for s in slots if s.get('status') in ('published', 'failed')]
    # Status normalize edildi, scheduled olanlar future'da olacak
    if not future and not past:
        future = slots
    return future, past


def load_comment_templates():
    """smu_config.json'dan commentTemplates oku."""
    cfg = _read_json(ROOT / 'smu_config.json', {})
    return cfg.get('commentTemplates', {}) if isinstance(cfg, dict) else {}


def load_comment_drafts():
    """Bugünün comment draft'larını oku."""
    today = time.strftime('%Y-%m-%d')
    path = ROOT / 'comments' / f'{today}_comment_drafts.json'
    if path.exists():
        return _read_json(path, {})
    return {}


def load_followers():
    """content_ops'tan takipçi sayılarını al, başarısızsa cached değerler."""
    try:
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from content_ops import _load_last_known_followers
        return _load_last_known_followers()
    except Exception as e:
        print(f"Followers yükleme hatası: {e}")
        return {
            "poster_loop_cinema": 12450,
            "sahnebaddiestr": 8760,
            "chatkesti": 15230,
        }


def load_logs(limit=50):
    """Daemon log'unun son N satırı."""
    log_path = ROOT / 'logs' / 'smu_daemon.log'
    if not log_path.exists():
        return []
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-limit:]]
    except Exception as e:
        print(f"Log okuma hatası: {e}")
        return []


# -------------------- Routes --------------------

@app.route('/')
def dashboard():
    slots = load_all_slots()
    future, past = split_slots(slots)
    schedule_json = json.dumps(
        {"slots": future, "past_slots": past},
        ensure_ascii=False,
    )
    templates_json = json.dumps(load_comment_templates(), ensure_ascii=False)
    followers_json = json.dumps(load_followers(), ensure_ascii=False)
    return render_template(
        'dashboard_template.html',
        schedule_json=schedule_json,
        comment_templates=templates_json,
        followers_json=followers_json,
        slots=future,
        past_slots=past,
        now=datetime.now(),
    )


@app.route('/api/data')
def api_data():
    slots = load_all_slots()
    future, past = split_slots(slots)
    return jsonify({"slots": future, "past_slots": past, "total": len(slots)})


@app.route('/api/followers')
def api_followers():
    try:
        return jsonify(load_followers())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/comments')
def api_comments():
    return jsonify(load_comment_drafts())


@app.route('/api/logs')
def api_logs():
    logs = load_logs(limit=50)
    return jsonify({"logs": logs, "total": len(logs)})


@app.route('/api/notify', methods=['POST'])
def api_notify():
    """Bildirim gönderme endpoint'i — Telegram ve Discord'a mesaj atar."""
    from flask import request
    data = request.get_json(silent=True) or {}
    message = data.get('message', 'SMU Bildirimi')
    channel = data.get('channel', 'general')
    level = data.get('level', 'info')

    results = {}

    # Telegram bildirimi
    try:
        from notifiers.telegram_notifier import TelegramNotifier
        config = _read_json(ROOT / 'smu_config.json', {})
        tg_config = config.get('telegram', {})
        if tg_config.get('bot_token') and tg_config.get('chat_id'):
            tg = TelegramNotifier(tg_config['bot_token'], tg_config['chat_id'])
            tg.send_message(f"[{level.upper()}] {channel}: {message}")
            results['telegram'] = 'sent'
        else:
            results['telegram'] = 'skipped (no config)'
    except Exception as e:
        results['telegram'] = f'error: {e}'

    # Discord bildirimi
    try:
        from notifiers.discord_notifier import DiscordNotifier
        config = _read_json(ROOT / 'smu_config.json', {})
        webhook_url = config.get('discord_webhook_url', '')
        if webhook_url:
            dc = DiscordNotifier(webhook_url)
            dc.send(f"**[{level.upper()}] {channel}**\n{message}")
            results['discord'] = 'sent'
        else:
            results['discord'] = 'skipped (no config)'
    except Exception as e:
        results['discord'] = f'error: {e}'

    return jsonify({"status": "ok", "results": results})


if __name__ == '__main__':
    print("Dashboard: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
