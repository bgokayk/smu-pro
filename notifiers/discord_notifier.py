#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discord bildirim altyapısı — SMU V3.0

Kullanım:
    from notifiers.discord_notifier import DiscordNotifier
    dc = DiscordNotifier(webhook_url)
    dc.send("Merhaba Dünya")
"""

import requests


class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send(self, content):
        if not self.webhook_url:
            print("Discord webhook URL'si eksik.")
            return
        try:
            r = requests.post(self.webhook_url, json={"content": content}, timeout=10)
            if r.status_code == 204:
                print("Discord bildirimi gönderildi.")
            else:
                print(f"Discord hatası: {r.text}")
        except Exception as e:
            print(f"Discord bağlantı hatası: {e}")
