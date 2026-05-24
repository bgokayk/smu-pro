# SMU Daemon Başlatıcı
# Çift tıkla veya: .\start_smu.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PYTHON = "python"

Write-Host ""
Write-Host "================================================"
Write-Host "  SMU — Social Media Unit"
Write-Host "  PosterLoopCinema | SahneBaddiesTR"
Write-Host "================================================"
Write-Host ""

# Durum göster
Write-Host "[STATUS]"
& $PYTHON "$ROOT\smu_daemon.py" status
Write-Host ""

# Seçenek sun
Write-Host "Ne yapmak istiyorsun?"
Write-Host "  1) Daemon'u başlat (24/7)"
Write-Host "  2) Sadece sabah hazırlığı (download + plan)"
Write-Host "  3) Sadece indir (iki kanal)"
Write-Host "  4) Dry-run test (hiçbir şey yapma, sadece göster)"
Write-Host "  5) Çıkış"
Write-Host ""

$secim = Read-Host "Seçim (1-5)"

switch ($secim) {
    "1" {
        Write-Host ""
        Write-Host "Daemon başlatılıyor... (Ctrl+C ile durdur)"
        & $PYTHON "$ROOT\smu_daemon.py" start
    }
    "2" {
        Write-Host ""
        Write-Host "Sabah hazırlığı başlıyor..."
        & $PYTHON "$ROOT\smu_daemon.py" morning-prep
    }
    "3" {
        Write-Host ""
        Write-Host "PosterLoopCinema indiriliyor..."
        & $PYTHON "$ROOT\downloader.py" run --channel poster_loop_cinema --limit 12 --assume-confirmed
        Write-Host ""
        Write-Host "SahneBaddiesTR indiriliyor..."
        & $PYTHON "$ROOT\downloader.py" run --channel sahnebaddiestr --limit 12 --assume-confirmed
    }
    "4" {
        Write-Host ""
        Write-Host "Dry-run modu — gerçek işlem yok:"
        & $PYTHON "$ROOT\smu_daemon.py" morning-prep --dry-run
    }
    "5" {
        Write-Host "Çıkılıyor."
    }
    default {
        Write-Host "Geçersiz seçim."
    }
}
