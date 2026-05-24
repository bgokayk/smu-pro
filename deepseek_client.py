#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek API istemcisi — başlık ve caption önerileri için.

Kullanım:
    from deepseek_client import get_title_suggestion
    title = get_title_suggestion("Inception 2010 dream scene", "poster_loop_cinema")
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def _load_api_key() -> str:
    """API anahtarını smu_config.json'dan oku."""
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return config.get("deepseek_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY", "")


def get_title_suggestion(
    video_hints: str,
    channel_name: str,
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> str | None:
    """DeepSeek API'den YouTube Shorts başlık önerisi al.

    Args:
        video_hints: Video hakkında ipuçları (dosya adı, klasör adı, açıklama vb.)
        channel_name: Kanal adı (ör: poster_loop_cinema)
        max_tokens: Maksimum token sayısı
        temperature: Yaratıcılık seviyesi (0.0-1.0)

    Returns:
        Önerilen başlık veya None
    """
    if requests is None:
        print("⚠️  requests kütüphanesi yüklü değil, DeepSeek kullanılamıyor.")
        return None

    api_key = _load_api_key()
    if not api_key:
        print("⚠️  DeepSeek API anahtarı bulunamadı (smu_config.json veya DEEPSEEK_API_KEY env)")
        return None

    # Kanal adını okunabilir forma çevir
    channel_display = channel_name.replace("_", " ").title()

    prompt = f"""Aşağıdaki video için YouTube Shorts başlığı oluştur.
Kesinlikle dosya adı, sayı dizileri, ID'ler içermemeli.
Sadece film adı, yıl ve etkileyici bir kısa açıklama olmalı.
Örnek: "Inception (2010) – Rüya Sahnesi #shorts"

Video ipuçları: {video_hints}
Kanal: {channel_display}
Başlık:"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=data,
            timeout=15,
        )
        if response.status_code == 200:
            result = response.json()
            title = result["choices"][0]["message"]["content"].strip()
            # Başlıkta tırnak işaretleri varsa temizle
            title = title.strip('"').strip("'").strip()
            return title
        else:
            print(f"DeepSeek API hatası (HTTP {response.status_code}): {response.text[:200]}")
            return None
    except Exception as e:
        print(f"DeepSeek API isteği başarısız: {e}")
        return None


def get_caption_suggestion(
    video_hints: str,
    channel_name: str,
    platform: str = "instagram",
) -> str | None:
    """DeepSeek API'den caption önerisi al.

    Args:
        video_hints: Video hakkında ipuçları
        channel_name: Kanal adı
        platform: Hedef platform (instagram, tiktok)

    Returns:
        Önerilen caption veya None
    """
    if requests is None:
        return None

    api_key = _load_api_key()
    if not api_key:
        return None

    channel_display = channel_name.replace("_", " ").title()
    max_len = 150 if platform == "instagram" else 100

    prompt = f"""Aşağıdaki video için {platform} caption'ı oluştur.
Kesinlikle dosya adı, sayı dizileri, ID'ler içermemeli.
Maksimum {max_len} karakter olmalı.
Doğal ve ilgi çekici bir dil kullan.

Video ipuçları: {video_hints}
Kanal: {channel_display}
Caption:"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 80,
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=data,
            timeout=15,
        )
        if response.status_code == 200:
            result = response.json()
            caption = result["choices"][0]["message"]["content"].strip()
            caption = caption.strip('"').strip("'").strip()
            if len(caption) > max_len:
                caption = caption[: max_len - 3] + "..."
            return caption
        return None
    except Exception as e:
        print(f"DeepSeek caption hatası: {e}")
        return None


if __name__ == "__main__":
    # Test
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek Client Test")
    parser.add_argument("--hints", default="Inception 2010 dream scene", help="Video ipuçları")
    parser.add_argument("--channel", default="poster_loop_cinema", help="Kanal adı")
    parser.add_argument("--type", choices=["title", "caption"], default="title", help="İstek tipi")
    args = parser.parse_args()

    if args.type == "title":
        result = get_title_suggestion(args.hints, args.channel)
    else:
        result = get_caption_suggestion(args.hints, args.channel)

    if result:
        print(f"✅ {args.type}: {result}")
    else:
        print(f"❌ {args.type} alınamadı")
