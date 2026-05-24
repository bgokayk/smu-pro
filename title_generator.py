#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Title Generator — DeepSeek ile kanal-spesifik YouTube Shorts başlığı üretir.

Kullanım:
    from title_generator import generate_title

    title = generate_title(
        channel="poster_loop_cinema",
        scene_summary="Bir adam diploması olmadığı halde herkesi kandırıyor",
        film_name="The Pursuit of Happyness",
        film_year="2006",
    )
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"

# Kanal-spesifik ton tanımları
CHANNEL_TONES = {
    "poster_loop_cinema": {
        "tone": "sinefil, nostaljik, sanatsal",
        "style": "Film adı + yıl + sahne betimlemesi, merak uyandıran",
        "examples": [
            "Inception (2010) – Rüya Katmanları Çöküyor #shorts",
            "The Dark Knight (2008) – Joker'in Kaosu Başlıyor #shorts",
            "Interstellar (2014) – Zamanın Kıyısında Bir Yolculuk #shorts",
        ],
    },
    "sahnebaddiestr": {
        "tone": "dramatik, duygusal, karakter odaklı",
        "style": "Karakter adı + replik/duygu + soru, izleyiciyi içine çeken",
        "examples": [
            "Bu Sahnede Herkes Susuyor – Aura 10/10 #shorts",
            "O An Gözlerindeki Ifade Her Şeyi Anlatti #shorts",
            "Bu Replik Türk Televizyon Tarihine Geçti #shorts",
        ],
    },
    "chatkesti": {
        "tone": "eğlenceli, samimi, yayıncı kültürü",
        "style": "Yayıncı adı + kopma anı + espri, gaming jargonu",
        "examples": [
            "Yayıncı Bu Anda Resmen Koptu 😂 #shorts",
            "Chat'in Sustuğu An – Müthiş Reaksiyon #shorts",
            "Oyunun En Komik Anı – Kaçıran Pişman #shorts",
        ],
    },
}


def _load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _get_api_key() -> str:
    config = _load_config()
    return config.get("deepseek_api_key", "")


def _extract_clean_hints(item: dict[str, Any]) -> str:
    """Queue item'ından anlamlı ipuçları çıkar."""
    hints = []

    # ID'den anlamlı kısmı çıkar (sayı-ID- kısmını atla)
    item_id = item.get("id", "")
    if item_id:
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", item_id)
        clean = re.sub(r"[-_]", " ", clean)
        if clean and len(clean) > 5:
            hints.append(clean)

    # Metadata'dan film/yayıncı bilgisi
    meta = item.get("metadata", {})
    film_identity = meta.get("film_identity", {})
    if film_identity.get("title"):
        title = film_identity.get("title", "")
        # Dosya adı kalıntılarını temizle
        title = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", title)
        title = re.sub(r"[-_]", " ", title)
        title = re.sub(r"-poster-loop.*$", "", title)
        hints.append(title.strip())

    if film_identity.get("director") and film_identity.get("director") != "VERIFY_NEEDED":
        hints.append(f"Yönetmen: {film_identity['director']}")

    # Dosya adından ipucu
    file_path = item.get("file", "")
    if file_path:
        stem = Path(file_path).stem
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", stem)
        clean = re.sub(r"[-_]", " ", clean)
        clean = re.sub(r"-poster-loop.*$", "", clean)
        if clean and len(clean) > 5 and clean not in hints:
            hints.append(clean)

    return " | ".join(hints) if hints else "Film sahnesi"


def generate_title(
    channel: str,
    scene_summary: str = "",
    film_name: str = "",
    film_year: str = "",
    streamer: str = "",
    game: str = "",
    hook: str = "",
    item: dict[str, Any] | None = None,
) -> str:
    """DeepSeek ile kanal-spesifik YouTube Shorts başlığı üret.

    Args:
        channel: Kanal ID (poster_loop_cinema, sahnebaddiestr, chatkesti)
        scene_summary: Sahne özeti (Türkçe)
        film_name: Film adı (poster_loop_cinema için)
        film_year: Film yılı
        streamer: Yayıncı adı (chatkesti için)
        game: Oyun adı (chatkesti için)
        hook: Hook/etkileyici cümle
        item: Queue item'ı (opsiyonel, otomatik ipucu çıkarmak için)

    Returns:
        Üretilmiş başlık (str)
    """
    api_key = _get_api_key()
    if not api_key:
        return _fallback_title(channel, film_name, film_year, streamer, hook)

    # Kanal tonu
    tone_info = CHANNEL_TONES.get(channel, CHANNEL_TONES["poster_loop_cinema"])

    # İpuçlarını topla
    hints = scene_summary
    if item:
        hints = _extract_clean_hints(item)

    # Kanal-spesifik prompt
    if channel == "poster_loop_cinema":
        prompt = (
            f"Sen Türk sosyal medya uzmanısın. poster_loop_cinema kanalı için "
            f"viral YouTube Shorts başlığı yazıyorsun.\n\n"
            f"Kurallar:\n"
            f"- 70-100 karakter\n"
            f"- Türkçe, doğal ve akıcı\n"
            f"- Film adı + yıl + sahne betimlemesi\n"
            f"- Merak uyandırıcı hook\n"
            f"- Clickbait değil ama ilgi çekici\n"
            f"- #shorts ile bitmeli\n"
            f"- Emoji opsiyonel, max 1 tane\n\n"
            f"Ton: sinefil, nostaljik, sanatsal\n\n"
            f"Örnekler:\n"
            f"- Inception (2010) – Rüya Katmanları Çöküyor #shorts\n"
            f"- The Dark Knight (2008) – Joker'in Kaosu Başlıyor #shorts\n"
            f"- Interstellar (2014) – Zamanın Kıyısında Bir Yolculuk #shorts\n\n"
            f"Film: {film_name or 'Bilinmiyor'}\n"
            f"Yıl: {film_year or 'Bilinmiyor'}\n"
            f"Sahne: {hints}\n\n"
            f"Sadece başlığı yaz. Başka bir şey yazma."
        )
    elif channel == "sahnebaddiestr":
        prompt = (
            f"Sen Türk sosyal medya uzmanısın. sahnebaddiestr kanalı için "
            f"viral YouTube Shorts başlığı yazıyorsun.\n\n"
            f"Kurallar:\n"
            f"- 70-100 karakter\n"
            f"- Türkçe, dramatik ve duygusal\n"
            f"- Karakter/kişi odaklı, replik veya duygu içeren\n"
            f"- İzleyiciyi içine çeken soru veya iddia\n"
            f"- #shorts ile bitmeli\n"
            f"- Emoji opsiyonel, max 1 tane\n\n"
            f"Ton: dramatik, duygusal, karakter odaklı\n\n"
            f"Örnekler:\n"
            f"- Bu Sahnede Herkes Susuyor – Aura 10/10 #shorts\n"
            f"- O An Gözlerindeki Ifade Her Şeyi Anlatti #shorts\n"
            f"- Bu Replik Türk Televizyon Tarihine Geçti #shorts\n\n"
            f"Sahne: {hints}\n"
            f"Hook: {hook or 'yok'}\n\n"
            f"Sadece başlığı yaz. Başka bir şey yazma."
        )
    elif channel == "chatkesti":
        prompt = (
            f"Sen Türk sosyal medya uzmanısın. chatkesti kanalı için "
            f"viral YouTube Shorts başlığı yazıyorsun.\n\n"
            f"Kurallar:\n"
            f"- 70-100 karakter\n"
            f"- Türkçe, eğlenceli ve samimi\n"
            f"- Yayıncı adı + kopma anı + espri\n"
            f"- Gaming jargonu kullan\n"
            f"- #shorts ile bitmeli\n"
            f"- Emoji serbest, 1-2 tane\n\n"
            f"Ton: eğlenceli, samimi, yayıncı kültürü\n\n"
            f"Örnekler:\n"
            f"- Yayıncı Bu Anda Resmen Koptu 😂 #shorts\n"
            f"- Chat'in Sustuğu An – Müthiş Reaksiyon #shorts\n"
            f"- Oyunun En Komik Anı – Kaçıran Pişman #shorts\n\n"
            f"Yayıncı: {streamer or 'Bilinmiyor'}\n"
            f"Oyun: {game or 'Bilinmiyor'}\n"
            f"Sahne: {hints}\n"
            f"Hook: {hook or 'yok'}\n\n"
            f"Sadece başlığı yaz. Başka bir şey yazma."
        )
    else:
        return _fallback_title(channel, film_name, film_year, streamer, hook)

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "Sen Türk sosyal medya uzmanısın. Kısa, viral, Türkçe başlıklar üretiyorsun.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 100,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        title = r.json()["choices"][0]["message"]["content"].strip()

        # Temizlik
        title = title.strip('"').strip("'").strip()
        # #shorts ekle (yoksa)
        if not title.endswith("#shorts"):
            title = title.rstrip() + " #shorts"
        # Karakter sınırı
        if len(title) > 100:
            title = title[:97] + " #shorts"
        if len(title) < 10:
            return _fallback_title(channel, film_name, film_year, streamer, hook)

        return title
    except Exception as e:
        print(f"[TitleGenerator HATA] {e}")
        return _fallback_title(channel, film_name, film_year, streamer, hook)


def _fallback_title(
    channel: str,
    film_name: str = "",
    film_year: str = "",
    streamer: str = "",
    hook: str = "",
) -> str:
    """DeepSeek yoksa veya hata alırsa kullanılacak fallback."""
    if channel == "poster_loop_cinema":
        if film_name:
            return f"{film_name} ({film_year}) – Sinema Tarihine Geçen Sahne #shorts" if film_year else f"{film_name} – Sinema Tarihine Geçen Sahne #shorts"
        return "Sinema Tarihine Geçen Sahne #shorts"
    elif channel == "sahnebaddiestr":
        if hook:
            return f"{hook} – Aura 10/10 #shorts"
        return "Bu Sahnenin Enerjisi Başka #shorts"
    elif channel == "chatkesti":
        if streamer:
            return f"{streamer} – Yayında Kopma Anı 😂 #shorts"
        return "Yayında Kopma Anı 😂 #shorts"
    return "Shorts #shorts"


def regenerate_title(
    old_title: str,
    channel: str,
    item: dict[str, Any] | None = None,
) -> str:
    """Mevcut başlığı DeepSeek ile yeniden üret (re-generate butonu için)."""
    hints = ""
    if item:
        hints = _extract_clean_hints(item)
    return generate_title(
        channel=channel,
        scene_summary=hints or old_title,
        item=item,
    )
