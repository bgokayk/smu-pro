@echo off
REM SMU Pro Desktop Launcher
REM Bu dosyayi cift tikla — masaustu uygulamasi gibi acilir.
title SMU Pro
cd /d "%~dp0"
python smu_desktop.py
if errorlevel 1 (
    echo.
    echo HATA: SMU Pro baslatilamadi. Hata mesajini yukarida gor.
    pause
)
