#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import time
import webbrowser
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template_string, jsonify

ROOT = Path(__file__).parent
SCHEDULE_FILE = ROOT / "schedules" / f"{time.strftime('%Y-%m-%d')}_smu_schedule.json"
COMMENTS_FILE = ROOT / "comments" / f"{time.strftime('%Y-%m-%d')}_comment_drafts.json"
CONFIG_FILE = ROOT / "smu_config.json"
LOG_FILE = ROOT / "logs" / "smu_daemon.log"

# HTML template'i ayri dosyadan oku
HTML_TEMPLATE = (ROOT / "dashboard_template.html").read_text(encoding="utf-8")

app = Flask(__name__)

def load_schedule():
    if SCHEDULE_FILE.exists():
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding='utf-8-sig'))
            return data.get('slots', [])
        except Exception as e:
            print(f"load_schedule error: {e}")
            return []
    return []

def load_comments():
    if COMMENTS_FILE.exists():
        try:
            return json.loads(COMMENTS_FILE.read_text(encoding='utf-8'))
        except:
            return {}
    return {}

def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except:
            return {}
    return {}

def load_logs():
    if LOG_FILE.exists():
        try:
            lines = LOG_FILE.read_text(encoding='utf-8').splitlines()
            return lines[-50:]
        except:
            return []
    return []

@app.route('/')
def dashboard():
    slots = load_schedule()
    config = load_config()
    comment_templates = config.get('commentTemplates', {})
    schedule_json = json.dumps({"slots": slots}, ensure_ascii=False)
    templates_json = json.dumps(comment_templates, ensure_ascii=False)
    return render_template_string(HTML_TEMPLATE, schedule_json=schedule_json, comment_templates=templates_json)

@app.route('/api/data')
def api_data():
    slots = load_schedule()
    return jsonify({"slots": slots})

@app.route('/api/followers')
def api_followers():
    try:
        from content_ops import get_followers_stats
        stats = get_followers_stats()
        return jsonify(stats)
    except Exception:
        # Mock data fallback
        return jsonify({
            "poster_loop_cinema": 12450,
            "sahnebaddiestr": 8760,
            "chatkesti": 15230
        })

@app.route('/api/comments')
def api_comments():
    data = load_comments()
    return jsonify(data)

@app.route('/api/logs')
def api_logs():
    logs = load_logs()
    return jsonify({"logs": logs, "total": len(logs)})

def start_daemon():
    daemon_script = ROOT / "smu_daemon.py"
    if daemon_script.exists():
        subprocess.Popen([sys.executable, str(daemon_script), 'start'], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)

if __name__ == '__main__':
    start_daemon()
    webbrowser.open('http://localhost:5000')
    app.run(host='127.0.0.1', port=5000, debug=False)
