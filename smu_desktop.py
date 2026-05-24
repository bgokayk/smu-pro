#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Pro Desktop Wrapper

Dashboard'u (5004) masaustu uygulamasi olarak acar.
Browser yerine native pencere kullanir. Sistem tray ikonu yok.

Kurulum (ilk kez):
    pip install pywebview

Calistirma:
    python smu_desktop.py

Bu script:
1. smu_app.py'yi arka planda baslatir (5004 portuna)
2. Native bir pencere acar (Edge WebView2/Chrome embedded)
3. Pencere kapatildiginda dashboard sunucusu da kapanir
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).parent
DASHBOARD_SCRIPT = ROOT / "state" / "run_dashboard_5004.py"
PORT = 5004
URL = f"http://127.0.0.1:{PORT}"


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def wait_for_dashboard(timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(PORT):
            return True
        time.sleep(0.5)
    return False


def start_dashboard_if_needed() -> subprocess.Popen | None:
    if is_port_open(PORT):
        print(f"Dashboard zaten calisiyor: {URL}")
        return None
    print(f"Dashboard baslatiliyor: {DASHBOARD_SCRIPT}")
    proc = subprocess.Popen(
        [sys.executable, str(DASHBOARD_SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if not wait_for_dashboard(30):
        print("HATA: Dashboard 30 saniyede acilmadi")
        proc.terminate()
        return None
    return proc


def main():
    proc = start_dashboard_if_needed()
    try:
        import webview
    except ImportError:
        print("pywebview yok, yukleniyor: pip install pywebview")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywebview"])
        import webview

    window = webview.create_window(
        "SMU Pro",
        URL,
        width=1600,
        height=1000,
        resizable=True,
        confirm_close=False,
        background_color="#0a0c0f",
    )
    try:
        webview.start()
    finally:
        if proc is not None:
            print("Dashboard kapatiliyor...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
