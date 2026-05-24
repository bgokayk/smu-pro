#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Description Generator — DeepSeek ile platform-spesifik açıklama üretir.

YouTube: 800+ karakter, Instagram: 500+ karakter, TikTok: 150-200 karakter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"

# Cross-promo kanal linkleri
CROSS_PROMO = {
    "poster_loop_cinema": {
        "other_channels": [
            "🎬 @sahnebaddiestr – Türk dizi/film sahneleri",
            "🎮 @chatkesti – Yayıncı kesitleri",
        ],
    },
    "sahnebaddiestr": {
        "other_channels": [
            "🎬 @poster_loop_cinema – Sinema klasikleri",
            "🎮 @chatkesti – Yayıncı kesitleri",
        ],
    },
    "chatkesti": {
        "other_channels": [
            "🎬 @poster_loop_cinema – Sinema klasikleri",
            "🎬 @sahnebaddiestr – Türk dizi/film sahneleri",
        ],
    },
}

# Kanal-spesifik hashtag havuzları
HASHTAG_POOLS = {
    "poster_loop_cinema": [
        "#shorts", "#sinema", "#film", "#movie", "#cinema", "#movingposter",
        "#filmclips", "#moviescenes", "#filmedit", "#movieedit", "#cultcinema",
        "#filmart", "#posterdesign", "#filmhistory", "#classicmovies",
        "#filmquote", "#cinematography", "#filmphotography", "#movieclips",
        "#filmclips", "#sinematik", "#filmönerisi", "#sinemaseverler",
        "#filmkareleri", "#sinematarihi",
    ],
    "sahnebaddiestr": [
        "#shorts", "#sahnebaddies", "#baddies", "#reels", "#türkdizisi",
        "#türkfilmleri", "#duygusal", "#dram", "#karakter", "#replik",
        "#aura", "#edit", "#kesfet", "#ünlüler", "#magazin",
        "#sahne", "#dizisahneleri", "#filmsahneleri", "#türksinemasi",
        "#duygusalanlar", "#karakteranalizi", "#türktelevizyonu",
    ],
    "chatkesti": [
        "#shorts", "#chatkesti", "#twitch", "#kick", "#streamerclips",
        "#yayinkesitleri", "#gaming", "#reels", "#twitchturkiye",
        "#kickturkiye", "#yayinkesiti", "#gamingclips", "#fyp",
        "#streamer", "#clips", "#yayıncı", "#oyun", "#komik",
        "#kahkaha", "#eğlence", "#canlıyayın", "#esports",
    ],
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
    item_id = item.get("id", "")
    if item_id:
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", item_id)
        clean = re.sub(r"[-_]", " ", clean)
        if clean and len(clean) > 5:
            hints.append(clean)

    meta = item.get("metadata", {})
    film_identity = meta.get("film_identity", {})
    if film_identity.get("title"):
        title = film_identity.get("title", "")
        title = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", title)
        title = re.sub(r"[-_]", " ", title)
        title = re.sub(r"-poster-loop.*$", "", title)
        hints.append(title.strip())

    file_path = item.get("file", "")
    if file_path:
        stem = Path(file_path).stem
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", stem)
        clean = re.sub(r"[-_]", " ", clean)
        clean = re.sub(r"-poster-loop.*$", "", clean)
        if clean and len(clean) > 5 and clean not in hints:
            hints.append(clean)

    return " | ".join(hints) if hints else "Film sahnesi"


def _build_hashtag_block(channel: str, count: int = 20) -> str:
    """Kanal-spesifik hashtag bloğu oluştur."""
    pool = HASHTAG_POOLS.get(channel, HASHTAG_POOLS["poster_loop_cinema"])
    # İlk 20'yi al, karıştırma yapma (tutarlılık için)
    selected = pool[:count]
    return " ".join(selected)


def generate_youtube_description(
    channel: str,
    scene_summary: str = "",
    film_name: str = "",
    film_year: str = "",
    streamer: str = "",
    game: str = "",
    hook: str = "",
    title: str = "",
    item: dict[str, Any] | None = None,
) -> str:
    """YouTube Shorts açıklaması üret (800+ karakter).

    Yapı:
    1. Hook cümle (ilk satır, soru veya iddialı)
    2. Sahne anlatımı (3-4 cümle)
    3. Duygu/yorum (2 cümle)
    4. Cross-promo (diğer kanalları öner)
    5. CTA (beğen, takip, bildirim)
    6. Hashtag bloğu (20-25 hashtag)
    """
    api_key = _get_api_key()
    hints = scene_summary
    if item:
        hints = _extract_clean_hints(item)

    cross = CROSS_PROMO.get(channel, {})
    other_channels = "\n".join(cross.get("other_channels", []))

    if api_key:
        prompt = (
            f"Sen Türk içerik yazarısın. YouTube Shorts açıklaması yazıyorsun.\n\n"
            f"Yapı:\n"
            f"1. Hook cümle (ilk satır, soru veya iddialı)\n"
            f"2. Sahne anlatımı (3-4 cümle)\n"
            f"3. Duygu/yorum (2 cümle)\n"
            f"4. Diğer kanalları öner:\n{other_channels}\n"
            f"5. CTA: Beğen + Takip et + Bildirim aç\n"
            f"6. Hashtag bloğu (20-25 hashtag)\n\n"
            f"Kurallar:\n"
            f"- Minimum 800 karakter\n"
            f"- Türkçe, doğal ve akıcı\n"
            f"- Başlığı tekrarlama\n"
            f"- Soru sor (izleyiciyi yoruma teşvik)\n"
            f"- Emoji kullan (3-5 tane)\n\n"
            f"Kanal: {channel}\n"
            f"Başlık: {title}\n"
            f"Sahne: {hints}\n"
            f"Film: {film_name or 'Bilinmiyor'} ({film_year or '?'})\n"
            f"Yayıncı: {streamer or 'Bilinmiyor'}\n"
            f"Oyun: {game or 'Bilinmiyor'}\n\n"
            f"Sadece açıklamayı yaz. Başka bir şey yazma."
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "Sen Türk içerik yazarısın. Uzun, kaliteli YouTube açıklamaları yazıyorsun.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 2000,
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
                timeout=60,
            )
            r.raise_for_status()
            desc = r.json()["choices"][0]["message"]["content"].strip()
            if len(desc) >= 800:
                return desc
        except Exception as e:
            print(f"[DescriptionGenerator HATA] {e}")

    # Fallback: template tabanlı açıklama
    return _fallback_youtube_description(channel, hints, film_name, film_year, streamer, game, title, other_channels)


def _fallback_youtube_description(
    channel: str,
    hints: str,
    film_name: str,
    film_year: str,
    streamer: str,
    game: str,
    title: str,
    other_channels: str,
) -> str:
    """DeepSeek yoksa template tabanlı açıklama üret."""
    hashtags = _build_hashtag_block(channel, 20)

    if channel == "poster_loop_cinema":
        desc = (
            f"Bu sahneyi daha önce hiç böyle gördünüz mü? 🎬\n\n"
            f"{film_name or 'Bu film'} ({film_year or 'yıl bilinmiyor'}) "
            f"filminden unutulmaz bir an. Sinema tarihine geçen bu sahne, "
            f"her izleyişte farklı bir duygu bırakıyor. Yönetmenin dehası, "
            f"oyuncunun performansı ve görsel anlatımın gücü bir arada.\n\n"
            f"Bu filmi izlediyseniz bu sahneyi hatırlarsınız. İzlemediyseniz, "
            f"bu kısa klip size film hakkında fikir verecek. Sinema sadece "
            f"bir eğlence değil, aynı zamanda bir sanat formu. Her kare, "
            f"her diyalog, her bakış bir hikaye anlatıyor.\n\n"
            f"Sizce bu filmdeki en etkileyici sahne hangisi? Yorumlarda "
            f"buluşalım! 👇\n\n"
            f"📌 Diğer kanallarımız:\n{other_channels}\n\n"
            f"Beğenmeyi, takip etmeyi ve bildirimleri açmayı unutmayın! 🔔\n\n"
            f"{hashtags}"
        )
    elif channel == "sahnebaddiestr":
        desc = (
            f"Bu anın aurasını hissettiniz mi? 🔥\n\n"
            f"Ekran duruşu, mimikler, o enerji... İşte bu yüzden bu sahne "
            f"akıllardan silinmiyor. Karakterin o anki duygusu, bakışlarındaki "
            f"ifade, her şeyi anlatıyor. Türk televizyon tarihine geçen bu an, "
            f"izleyiciyi ekrana kitliyor.\n\n"
            f"Bu sahneyi izlerken neler hissettiniz? Sizce bu karakterin "
            f"yerinde olsaydınız ne yapardınız? Yorumlarda buluşalım! 💬\n\n"
            f"📌 Diğer kanallarımız:\n{other_channels}\n\n"
            f"Beğenmeyi, takip etmeyi ve bildirimleri açmayı unutmayın! 🔔\n\n"
            f"{hashtags}"
        )
    elif channel == "chatkesti":
        desc = (
            f"Yayıncı bu anda resmen koptu! 😂\n\n"
            f"{streamer or 'Yayıncı'}, {game or 'oyun'} oynarken "
            f"beklenmedik bir anda yaşanan bu olay karşısında ne yapacağını "
            f"şaşırdı. Chat'in çıldırdığı an, yayın tarihine geçen bir "
            f"kesit. Bu tür anlar yayıncılığın en güzel yanı: anlık, samimi "
            f"ve tamamen gerçek.\n\n"
            f"Sizce bu anın şiddeti kaç/10? Yorumlarda değerlendirin! 👇\n\n"
            f"📌 Diğer kanallarımız:\n{other_channels}\n\n"
            f"Beğenmeyi, takip etmeyi ve bildirimleri açmayı unutmayın! 🔔\n\n"
            f"{hashtags}"
        )
    else:
        desc = (
            f"Bu anı kaçırmayın! 🎬\n\n"
            f"{hints}\n\n"
            f"📌 Diğer kanallarımız:\n{other_channels}\n\n"
            f"Beğenmeyi, takip etmeyi ve bildirimleri açmayı unutmayın! 🔔\n\n"
            f"{hashtags}"
        )

    # Minimum 800 karakter kontrolü
    if len(desc) < 800:
        # Eksik karakter kadar hashtag ekle
        extra_hashtags = " #shorts #viral #trending #keşfet #fyp #explore"
        while len(desc) < 800:
            desc += extra_hashtags
            if len(desc) >= 800:
                break
            desc += " #film #sinema #movie #cinema"

    return desc[:5000]  # YouTube limiti


def generate_instagram_caption(
    channel: str,
    scene_summary: str = "",
    film_name: str = "",
    streamer: str = "",
    hook: str = "",
    item: dict[str, Any] | None = None,
) -> str:
    """Instagram caption üret (500+ karakter, story-telling, emoji destekli)."""
    hints = scene_summary
    if item:
        hints = _extract_clean_hints(item)

    hashtags = _build_hashtag_block(channel, 25)

    if channel == "poster_loop_cinema":
        caption = (
            f"🎬 {film_name or 'Bu film'} sinema tarihine geçen bir sahneyle karşınızda!\n\n"
            f"{hints}\n\n"
            f"Sinema sadece izlemek değil, hissetmektir. Bu kare, o duyguyu "
            f"bir anda size geçiriyor. Yönetmenin vizyonu, oyuncunun performansı "
            f"ve görsel anlatımın büyüsü...\n\n"
            f"Sizce bu filmdeki en iyi sahne hangisi? Yorumlara yazın! 👇\n\n"
            f"Beğen + Takip et + Bildirim aç 🔔\n\n"
            f"{hashtags}"
        )
    elif channel == "sahnebaddiestr":
        caption = (
            f"🔥 Bu anın aurası 10/10!\n\n"
            f"{hints}\n\n"
            f"Bazen bir bakış, bir mimik, bir duruş her şeyi anlatır. "
            f"İşte bu sahne tam olarak öyle bir an. Türk televizyonunun "
            f"en unutulmaz anlarından biri.\n\n"
            f"Sizce bu sahne kaç puan? 🎯\n\n"
            f"Beğen + Takip et + Bildirim aç 🔔\n\n"
            f"{hashtags}"
        )
    elif channel == "chatkesti":
        caption = (
            f"😂 Yayıncı bu anda resmen dağıldı!\n\n"
            f"{hints}\n\n"
            f"Canlı yayınların en güzel yanı anlık tepkiler. Bu kesit, "
            f"o anı tekrar yaşatıyor. Chat'in çıldırdığı, yayıncının "
            f"kendini tutamadığı o an...\n\n"
            f"Sizce bu anın komiklik seviyesi kaç/10? 🎮\n\n"
            f"Beğen + Takip et + Bildirim aç 🔔\n\n"
            f"{hashtags}"
        )
    else:
        caption = (
            f"🎬 Bu anı kaçırmayın!\n\n"
            f"{hints}\n\n"
            f"Beğen + Takip et + Bildirim aç 🔔\n\n"
            f"{hashtags}"
        )

    # Instagram limiti: 2200 karakter
    if len(caption) > 2200:
        caption = caption[:2197] + "..."

    # Minimum 500 karakter kontrolü
    if len(caption) < 500:
        extra = "\n\n#shorts #viral #trending #keşfet #fyp #explore #film #sinema"
        while len(caption) < 500:
            caption += extra
            if len(caption) >= 500:
                break

    return caption


def generate_tiktok_caption(
    channel: str,
    scene_summary: str = "",
    hook: str = "",
    item: dict[str, Any] | None = None,
) -> str:
    """TikTok caption üret (150-200 karakter, viral hook + 5-8 hashtag)."""
    hints = scene_summary
    if item:
        hints = _extract_clean_hints(item)

    hashtags = _build_hashtag_block(channel, 8)

    if channel == "poster_loop_cinema":
        caption = (
            f"Bu sahneyi daha önce böyle görmediniz! 🎬 "
            f"{hints[:80]} "
            f"{hashtags}"
        )
    elif channel == "sahnebaddiestr":
        caption = (
            f"Bu anın aurasına bak 😎 "
            f"{hints[:80]} "
            f"{hashtags}"
        )
    elif channel == "chatkesti":
        caption = (
            f"Yayıncı bu anda koptu! 😂 "
            f"{hints[:80]} "
            f"{hashtags}"
        )
    else:
        caption = (
            f"Bu anı kaçırma! 🎬 "
            f"{hints[:80]} "
            f"{hashtags}"
        )

    # TikTok limiti: 2200 ama Shorts için 150-200 ideal
    if len(caption) > 200:
        caption = caption[:197] + "..."

    return caption
