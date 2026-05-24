#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram bildirim altyapısı — SMU V3.0

Kullanım:
    from notifiers.telegram_notifier import TelegramNotifier
    tg = TelegramNotifier(bot_token, chat_id)
    tg.send_message("Merhaba Dünya")
"""

import requests


class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text):
        if not self.bot_token or not self.chat_id:
            print("Telegram yapılandırması eksik.")
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {'chat_id': self.chat_id, 'text': text, 'parse_mode': 'HTML'}
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("Telegram bildirimi gönderildi.")
            else:
                print(f"Telegram hatası: {r.text}")
        except Exception as e:
            print(f"Telegram bağlantı hatası: {e}")
