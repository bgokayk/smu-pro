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

# ================= MODERN DASHBOARD HTML (Gömülü) =================
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
        body { background: #0a0c0f; font-family: system-ui, sans-serif; }
        .sidebar { background: #0f1115; border-right: 1px solid #1e2229; }
        .card { background: #13161c; border: 1px solid #1e2229; border-radius: 20px; transition: 0.2s; }
        .card:hover { border-color: #2d3748; }
        .stat-value { font-size: 2rem; font-weight: 800; }
        .menu-item { transition: 0.2s; border-radius: 12px; cursor: pointer; }
        .menu-item:hover { background: #1a1f2a; }
        .active-menu { background: #1e2a3a; color: #60a5fa; }
        .slot-row:hover { background: #1a1f2a; }
        .badge { background: #1a3a2a; color: #4caf50; padding: 2px 8px; border-radius: 20px; font-size: 11px; }
        .growth-up { color: #4caf50; }
        .growth-down { color: #f44336; }
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
            <div class="flex items-center gap-3"><div class="bg-gray-800/50 rounded-full px-3 py-1 text-xs"><i class="ri-chat-check-line mr-1"></i> AI Aktif</div><div class="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center"><span class="text-xs font-bold">SM</span></div></div>
        </div>

        <div id="dashboardView">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-7" id="stats"></div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-7" id="channels"></div>
            <div class="card p-0 overflow-hidden mb-7">
                <div class="px-5 py-3 border-b border-gray-800 flex justify-between"><h2 class="font-semibold"><i class="ri-table-line mr-2"></i>Bugünün Yayın Takvimi</h2><span class="text-xs text-gray-500" id="scheduleCount">0 slot</span></div>
                <div class="overflow-x-auto"><table class="w-full text-sm"><thead class="bg-gray-800/40 text-gray-300 text-xs"><tr><th class="px-4 py-2">Saat</th><th>Kanal</th><th>Kalan Süre</th><th>YouTube Başlık</th><th>Instagram Caption</th><th>Durum</th></tr></thead><tbody id="scheduleBody"></tbody></table></div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card p-4"><h2 class="font-semibold mb-3"><i class="ri-heart-line"></i> Anlık Takipçi Sayıları</h2><div id="followerStats"></div></div>
                <div class="card p-4"><h2 class="font-semibold mb-3"><i class="ri-line-chart-line"></i> Son 7 Gün Takipçi Artışı</h2><canvas id="growthChart" style="max-height:200px"></canvas></div>
            </div>
        </div>
        <div id="otherView" class="hidden"></div>
    </main>
</div>
<script>
    // Örnek veri (gerçek zamanlı API'den de gelebilir)
    const scheduleData = {{ schedule_json|safe }};
    const followerData = {
        "poster_loop_cinema": { name: "Poster Loop Cinema", handle: "@posterloopcinema", followers: 12450, weeklyGrowth: 842, history: [11800,11950,12100,12220,12340,12400,12450] },
        "sahnebaddiestr": { name: "Sahne Baddies TR", handle: "@sahnebaddiestr", followers: 8760, weeklyGrowth: 320, history: [8320,8410,8500,8590,8650,8700,8760] },
        "chatkesti": { name: "ChatKesti", handle: "@chatkesti", followers: 15230, weeklyGrowth: 1210, history: [13800,14100,14450,14780,14990,15120,15230] }
    };
    let growthChart = null;

    function updateStatsAndChannels() {
        const now = new Date();
        const slots = scheduleData.slots || [];
        const published = slots.filter(s => new Date(s.publishAtLocal) < now).length;
        const planned = slots.filter(s => new Date(s.publishAtLocal) >= now).length;
        document.getElementById('stats').innerHTML = `
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-calendar-check-line"></i> Yayınlanan</div><div class="stat-value">${published}</div><div class="text-green-400 text-xs mt-1">bugün</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-time-line"></i> Planlanan</div><div class="stat-value">${planned}</div><div class="text-blue-400 text-xs mt-1">kalan</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-checkbox-circle-line"></i> Başarı Oranı</div><div class="stat-value">98%</div><div class="text-gray-500 text-xs mt-1">son 24s</div></div>
            <div class="card p-4"><div class="text-gray-400 text-sm"><i class="ri-error-warning-line"></i> Hata</div><div class="stat-value">0</div><div class="text-red-400 text-xs mt-1">otomatik düzeltme</div></div>
        `;
        const channels = { poster_loop_cinema: 'Poster Loop Cinema', sahnebaddiestr: 'Sahne Baddies TR', chatkesti: 'ChatKesti' };
        const colors = { poster_loop_cinema: 'blue', sahnebaddiestr: 'orange', chatkesti: 'green' };
        let chHtml = '';
        for (const [id, name] of Object.entries(channels)) {
            let done = slots.filter(s => s.channel === id && new Date(s.publishAtLocal) < now).length;
            let percent = (done/30)*100;
            chHtml += `<div class="card p-4"><div><div class="font-semibold">${name}</div><div class="text-2xl font-bold mt-1">${done}/30</div><div class="text-xs text-gray-400">yayınlandı</div></div><div class="w-full bg-gray-800 rounded-full h-1.5 mt-3"><div class="bg-${colors[id]}-500 h-1.5 rounded-full" style="width:${percent}%"></div></div></div>`;
        }
        document.getElementById('channels').innerHTML = chHtml;

        const tbody = slots.map(s => {
            let t = new Date(s.publishAtLocal);
            let diff = Math.floor((t - now)/60000);
            let timeText = diff>0 ? `${diff}dk sonra` : `${-diff}dk önce`;
            let chName = s.channel==='poster_loop_cinema' ? 'Poster' : (s.channel==='sahnebaddiestr' ? 'Baddies' : 'Chat');
            return `<tr class="slot-row border-t border-gray-800"><td class="px-4 py-2 text-xs font-mono">${s.publishAtLocal.slice(11,16)}</td><td class="px-4 py-2 text-xs">${chName}</td><td class="px-4 py-2 text-xs ${diff>0?'text-blue-400':'text-gray-400'}">${timeText}</td><td class="px-4 py-2 text-xs truncate max-w-[200px]">${s.youtubeTitle||'-'}</td><td class="px-4 py-2 text-xs truncate max-w-[200px]">${s.instagramCaption||'-'}</td><td class="px-4 py-2"><span class="badge">Planlı</span></td></tr>`;
        }).join('');
        document.getElementById('scheduleBody').innerHTML = tbody || '<tr><td colspan="6" class="text-center py-6 text-gray-500">Takvim boş</td></tr>';
        document.getElementById('scheduleCount').innerText = `${slots.length} slot`;
    }

    function updateFollowerStats() {
        let html = '';
        for (const [key, d] of Object.entries(followerData)) {
            let growthPercent = (d.weeklyGrowth/(d.followers-d.weeklyGrowth)*100).toFixed(1);
            html += `<div class="flex justify-between items-center border-b border-gray-800 pb-2"><div><div class="font-semibold">${d.name}</div><div class="text-xs text-gray-400">${d.handle}</div></div><div class="text-right"><div class="text-xl font-bold">${d.followers.toLocaleString()}</div><div class="text-xs ${d.weeklyGrowth>=0?'growth-up':'growth-down'}">${d.weeklyGrowth>=0?'+'+d.weeklyGrowth:d.weeklyGrowth} (${growthPercent}%) bu hafta</div></div></div>`;
        }
        document.getElementById('followerStats').innerHTML = html;
    }

    function initGrowthChart() {
        const ctx = document.getElementById('growthChart').getContext('2d');
        if(growthChart) growthChart.destroy();
        const labels = ['-7','-6','-5','-4','-3','-2','Bugün'];
        const datasets = [];
        for(const [key,d] of Object.entries(followerData)){
            let color = key==='poster_loop_cinema'?'#3b82f6':(key==='sahnebaddiestr'?'#f97316':'#22c55e');
            datasets.push({ label: d.name, data: d.history, borderColor: color, backgroundColor: 'transparent', tension:0.3, fill:false });
        }
        growthChart = new Chart(ctx, { type:'line', data:{ labels, datasets }, options:{ responsive:true, maintainAspectRatio:true, plugins:{ legend:{ position:'top', labels:{ color:'#ccc' } } } } });
    }

    function setupMenu() {
        document.querySelectorAll('.menu-item').forEach(el=>{
            el.addEventListener('click',()=>{
                const page = el.getAttribute('data-page');
                document.querySelectorAll('.menu-item').forEach(m=>m.classList.remove('active-menu'));
                el.classList.add('active-menu');
                if(page==='dashboard'){
                    document.getElementById('dashboardView').classList.remove('hidden');
                    document.getElementById('otherView').classList.add('hidden');
                    document.getElementById('pageTitle').innerText = 'Kontrol Paneli';
                    document.getElementById('pageDesc').innerText = 'Tüm otomasyon süreçleriniz buradan yönetilir.';
                } else {
                    document.getElementById('dashboardView').classList.add('hidden');
                    document.getElementById('otherView').classList.remove('hidden');
                    let content = '';
                    if(page==='schedule') content = '<div class="card p-8 text-center text-gray-400"><i class="ri-calendar-line text-4xl"></i><p class="mt-2">Yayın takvimi detayları burada gösterilecek.</p></div>';
                    else if(page==='comments') content = '<div class="card p-8 text-center text-gray-400"><i class="ri-chat-3-line text-4xl"></i><p class="mt-2">Yorum planı ve taslaklar burada listelenecek.</p></div>';
                    else content = '<div class="card p-8 text-center text-gray-400"><i class="ri-pulse-line text-4xl"></i><p class="mt-2">Log kayıtları burada görüntülenecek.</p></div>';
                    document.getElementById('otherView').innerHTML = content;
                    document.getElementById('pageTitle').innerText = el.innerText.trim();
                    document.getElementById('pageDesc').innerText = 'Detaylı bilgiler bu bölümde.';
                }
            });
        });
    }

    setupMenu();
    updateStatsAndChannels();
    updateFollowerStats();
    initGrowthChart();
    setInterval(()=>{ updateStatsAndChannels(); updateFollowerStats(); if(growthChart) growthChart.destroy(); initGrowthChart(); }, 30000);
</script>
</body>
</html>
'''

app = Flask(__name__)

def load_schedule():
    if SCHEDULE_FILE.exists():
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding='utf-8'))
            return data.get('slots', [])
        except:
            return []
    return []

@app.route('/')
def dashboard():
    slots = load_schedule()
    # Schedule JSON'ını template'e gönder
    schedule_json = json.dumps({"slots": slots}, ensure_ascii=False)
    return render_template_string(HTML_TEMPLATE, schedule_json=schedule_json)

def start_daemon():
    # Daemon'u arka planda başlat (zaten çalışıyorsa tekrar başlatma)
    daemon_script = ROOT / "smu_daemon.py"
    if daemon_script.exists():
        subprocess.Popen([sys.executable, str(daemon_script), 'start'], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)

if __name__ == '__main__':
    start_daemon()
    webbrowser.open('http://localhost:5000')
    app.run(host='127.0.0.1', port=5000, debug=False)