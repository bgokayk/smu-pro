#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from threading import Thread
from flask import Flask, jsonify, render_template_string

# ---------- Sabitler ----------
ROOT = Path(__file__).parent
SCHEDULE_FILE = ROOT / "schedules" / f"{time.strftime('%Y-%m-%d')}_smu_schedule.json"
DAEMON_SCRIPT = ROOT / "smu_daemon.py"
COMMENT_FILE = ROOT / "comments" / f"{time.strftime('%Y-%m-%d')}_comment_drafts.json"
LOG_FILE = ROOT / "logs" / "smu_daemon.log"

# ---------- Flask Uygulaması ----------
app = Flask(__name__)

# ---------- Örnek Takipçi Verileri (şimdilik statik, gerçek API ile değiştirilebilir) ----------
def get_follower_data():
    # Bu kısmı Instagram ve YouTube API ile değiştirebiliriz.
    # Şimdilik örnek veri.
    return {
        "poster_loop_cinema": {"name": "Poster Loop Cinema", "handle": "@posterloopcinema", "followers": 12450, "weekly_growth": 842, "history": [11800, 11950, 12100, 12220, 12340, 12400, 12450]},
        "sahnebaddiestr": {"name": "Sahne Baddies TR", "handle": "@sahnebaddiestr", "followers": 8760, "weekly_growth": 320, "history": [8320, 8410, 8500, 8590, 8650, 8700, 8760]},
        "chatkesti": {"name": "ChatKesti", "handle": "@chatkesti", "followers": 15230, "weekly_growth": 1210, "history": [13800, 14100, 14450, 14780, 14990, 15120, 15230]}
    }

# ---------- API Uç Noktaları ----------
@app.route('/api/schedule')
def api_schedule():
    if SCHEDULE_FILE.exists():
        data = json.loads(SCHEDULE_FILE.read_text(encoding='utf-8'))
        return jsonify(data.get('slots', []))
    return jsonify([])

@app.route('/api/followers')
def api_followers():
    return jsonify(get_follower_data())

@app.route('/api/comments')
def api_comments():
    if COMMENT_FILE.exists():
        data = json.loads(COMMENT_FILE.read_text(encoding='utf-8'))
        return jsonify(data)
    return jsonify({})

@app.route('/api/logs')
def api_logs():
    if LOG_FILE.exists():
        # son 100 satırı oku
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-100:]
        return jsonify({'logs': ''.join(lines)})
    return jsonify({'logs': 'Log dosyası bulunamadı.'})

@app.route('/')
def index():
    # Arayüzü döndür (HTML/CSS/JS)
    return render_template_string(HTML_TEMPLATE)

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
    # Daemon zaten çalışıyor mu?
    try:
        # Windows'ta tasklist ile kontrol
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], capture_output=True, text=True)
        if 'smu_daemon.py' not in result.stdout:
            subprocess.Popen([sys.executable, str(DAEMON_SCRIPT), 'start'], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
    except Exception:
        # Linux/Mac için ps aux
        pass

# ---------- Ana Fonksiyon ----------
def main():
    start_daemon()
    # Flask'ı ayrı bir thread'de başlat
    def run_flask():
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    Thread(target=run_flask, daemon=True).start()
    # Tarayıcıyı aç
    webbrowser.open('http://127.0.0.1:5000')
    print("SMU Pro Dashboard başlatıldı: http://127.0.0.1:5000")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Kapatılıyor...")
        sys.exit(0)

if __name__ == '__main__':
    main()