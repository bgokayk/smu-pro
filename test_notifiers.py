#!/usr/bin/env python3
"""Test script for notifiers"""
import sys
sys.path.insert(0, r'C:\Users\User\.codex\content-ops')

from notifiers.telegram_notifier import TelegramNotifier
from notifiers.discord_notifier import DiscordNotifier

print("Notifier import OK")

# Test with empty config (should print "yapilandirma eksik" messages)
tg = TelegramNotifier("", "")
tg.send_message("Test mesaji")

dc = DiscordNotifier("")
dc.send("Test mesaji")

print("All notifier tests passed!")
