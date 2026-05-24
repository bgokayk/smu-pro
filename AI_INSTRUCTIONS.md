# SMU — AI Başlangıç Talimatları
# Claude Code ve Codex için ortak

Bu dosyayı her yeni session başında oku.

## Sistem Nedir?
SMU (Social Media Unit) — 3 kanallı otomasyon sistemi:
| Kanal | Tarayıcı | Port |
|-------|----------|------|
| Poster Loop Cinema | Chrome | 9222 |
| SahneBaddiesTR | Edge | 9223 |
| ChatKesti | Firefox | Selenium persistent profile |

## Session Başında Mutlaka Yap

```powershell
cd C:\Users\User\.codex\content-ops
python needs_help.py list        # Bekleyen görev var mı?
python smu_daemon.py status      # Sistem durumu nedir?
```

Bekleyen görev varsa → `python needs_help.py context` → talimatları oku ve hallederek `python needs_help.py resolve <id>` ile kapat.

## Temel Komutlar

```powershell
# Daemon (24/7 çalıştır, Ctrl+C ile durdur)
python smu_daemon.py start

# Elle sabah hazırlığı (indir + render + takvim)
python smu_daemon.py morning-prep

# Sadece indir (tüm kanallar)
python downloader.py run --channel all --limit 12 --assume-confirmed

# Sadece bir kanal indir
python downloader.py run --channel chatkesti --limit 10 --assume-confirmed

# ChatKesti tek komut: 50 video indir + render + Firefox ile YouTube/Instagram publish
powershell -ExecutionPolicy Bypass -File C:\Users\User\.codex\yayinci-kesitleri-auto\automation\run_chatkesti_50_firefox.ps1 -Limit 50

# Durum
python smu_daemon.py status
python needs_help.py list
```

## Dosya Hiyerarşisi

```
content-ops/
  smu_daemon.py       → 24/7 orkestratör
  downloader.py       → yt-dlp ile video indirici
  smu.py              → günlük takvim + planlama
  content_ops.py      → metadata + browser başlatma
  claude_client.py    → AI istemci (opsiyonel, API key olmadan çalışır)
  needs_help.py       → yardım kuyruğu (takılınca buraya yazar)
  sources/            → kanal kaynak konfigürasyonları (ytsearch: sorguları)
  state/              → daemon durumu, yardım kuyruğu
  schedules/          → günlük yayın takvimi
  logs/               → smu_daemon.log
```

## Kanal Pipeline'ları (Sabah Sırası)

**BaddiesTR:**
1. `downloader.py run --channel sahnebaddiestr` → source-videos/ doldurur
2. `ingest_baddies_sources.py` → dosyaları tarar, items.generated.json üretir
3. `build_baddies_queue.py` → yayın kuyruğu
4. `render_baddies_exports.py` → logo gömülü mp4 üretir
5. `baddies_dual_publish_worker.js` → Edge ile yükler

**PosterLoop:**
1. `downloader.py run --channel poster_loop_cinema` → source-videos/ doldurur
2. `build_posterloop_queue.py` → kuyruk
3. `render_filmmax_poster_exports.py` → poster efektli mp4
4. `posterloop_dual_publish_worker.js` → Chrome ile yükler

**ChatKesti:**
1. `run_chatkesti_50_firefox.ps1 -Limit 50` tek giriş noktasıdır
2. `downloader.py run --channel chatkesti --assume-confirmed` kaynak doldurur
3. `ingest_chatkesti_sources.py` + `analyze_clip_layout.py --items` + `render_chatkesti_exports.py` export üretir
4. `build_chatkesti_queue.py` YouTube/Instagram metadata kuyruğu hazırlar
5. `chatkesti_firefox_publish_worker.py` Firefox profiliyle YouTube Shorts + Instagram Reels paylaşır

## Kurallar (Değiştirme)
- 01:00-07:00 arası paylaşım yok
- Günde 10 video/kanal hedef
- Yorum: 10-15 hesaba manuel taslak (otomatik spam yok)
- Filigran: kaynak sayfada görünür filigran varsa o videoyu atla
- API key yoksa Claude istemcisi template'e düşer, sistem çalışmaya devam eder
