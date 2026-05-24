#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Schedule Yeniden Üretim Scripti — V2.0

Her slot için DeepSeek API ile benzersiz, anlamlı başlık/açıklama/caption üretir.
Duplicate kontrolü: published_ledger.is_duplicate() (Levenshtein >0.85)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = ROOT / "schedules" / "2026-05-24_smu_schedule.json"
BACKUP_FILE = ROOT / "schedules" / "2026-05-24_smu_schedule.json.bak"
LEDGER_FILE = ROOT / "state" / "published_ledger.json"

# DeepSeek API
DEEPSEEK_API_KEY = ""
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# İstatistik
stats = {
    "total_slots": 0,
    "deepseek_calls": 0,
    "deepseek_errors": 0,
    "duplicate_retries": 0,
    "ledger_entries": 0,
    "channels": {},
}


def load_config() -> dict:
    try:
        cfg = json.loads((ROOT / "smu_config.json").read_text(encoding="utf-8"))
        return cfg
    except Exception:
        return {}


def load_schedule() -> dict:
    return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8-sig"))


def save_schedule(data: dict) -> None:
    SCHEDULE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_ledger() -> list[dict]:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_ledger(entries: list[dict]) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def levenshtein_ratio(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    s1 = re.sub(r"\s+", " ", s1.lower()).strip()
    s2 = re.sub(r"\s+", " ", s2.lower()).strip()
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1
    prev_row = list(range(len2 + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost,
            ))
        prev_row = curr_row
    max_len = max(len1, len2)
    return 1.0 - (prev_row[-1] / max_len) if max_len > 0 else 1.0


def is_duplicate_in_ledger(text: str, ledger: list[dict], threshold: float = 0.85) -> bool:
    for entry in ledger:
        for field in ["title", "description", "caption"]:
            existing = entry.get(field, "")
            if existing and levenshtein_ratio(text, existing) > threshold:
                return True
    return False


def extract_hints_from_file(file_path: str, channel: str) -> str:
    """Dosya adından anlamlı ipuçları çıkar — agresif temizlik."""
    stem = Path(file_path).stem
    # Tüm ID desenlerini temizle (baştaki sayı-ID kombinasyonları)
    stem = re.sub(r'^\d{2,3}-[A-Za-z0-9]{6,}[-_]?', '', stem)
    stem = re.sub(r'^\d{2,3}\s+[A-Za-z0-9]{3,}\s+', '', stem)
    # Kalan ID benzeri kısımları temizle
    stem = re.sub(r'\b[A-Za-z0-9]{8,}\b', '', stem)
    stem = re.sub(r'\b[A-Za-z0-9]{6,}\d{2,}\b', '', stem)
    stem = re.sub(r'[-_]', ' ', stem)
    stem = re.sub(r'\s+', ' ', stem).strip()
    # Kanal bazlı temizlik
    if channel == "poster_loop_cinema":
        stem = re.sub(r'(?i)poster\s*loop', '', stem).strip()
        stem = re.sub(r'(?i)posterloop', '', stem).strip()
    elif channel == "sahnebaddiestr":
        stem = re.sub(r'(?i)sahne\s*baddies', '', stem).strip()
        stem = re.sub(r'(?i)sahnebaddies', '', stem).strip()
    elif channel == "chatkesti":
        stem = re.sub(r'(?i)chatkesti', '', stem).strip()
    stem = re.sub(r'\s+', ' ', stem).strip()
    # Hala anlamsız kısaltmalar varsa veya çok kısaysa boş dön
    if len(stem) < 8 or re.match(r'^[a-zA-Z0-9\s]{1,15}$', stem):
        return ""
    return stem


def call_deepseek(prompt: str, max_tokens: int = 300, temperature: float = 0.8) -> str | None:
    """DeepSeek API'ye istek gönder."""
    global stats
    stats["deepseek_calls"] += 1

    if not DEEPSEEK_API_KEY:
        print("  ⚠️  DeepSeek API anahtarı yok, template kullanılıyor.")
        return None

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"  ⚠️  DeepSeek hata {resp.status_code}: {resp.text[:200]}")
            stats["deepseek_errors"] += 1
            return None
    except Exception as e:
        print(f"  ⚠️  DeepSeek bağlantı hatası: {e}")
        stats["deepseek_errors"] += 1
        return None


def generate_title(hints: str, channel: str, slot_num: int, ledger: list[dict]) -> str:
    """Benzersiz başlık üret — max 3 retry."""
    channel_prompts = {
        "poster_loop_cinema": "Film sahnesi moving poster. Sinematik, etkileyici, kısa.",
        "sahnebaddiestr": "Ünlü/ fenomen sahnesi. Enerjik, dikkat çekici, magazin.",
        "chatkesti": "Yayıncı kesiti. Komik/şaşırtıcı an, samimi, akılda kalıcı.",
    }
    tone = channel_prompts.get(channel, "İlgi çekici, kısa.")

    for attempt in range(3):
        prompt = f"""Bir YouTube Shorts başlığı üret. KESİNLİKTE şu kurallara uy:
- 70-100 karakter arası
- Türkçe, akılda kalıcı, hook'lu
- #shorts ile bitsin
- Dosya adı, ID, VERIFY_NEEDED, sayı dizileri İÇERMESİN
- Kanal tonu: {tone}
- Video ipucu: {hints[:100]}
- Slot #{slot_num}

Sadece başlık metnini yaz, açıklama yapma."""

        title = call_deepseek(prompt, max_tokens=80, temperature=0.8)
        if not title:
            # Fallback: template kullan
            title = _fallback_title(hints, channel, slot_num)

        # Temizlik
        title = title.strip().strip('"').strip("'")
        title = re.sub(r'\s+', ' ', title).strip()
        if not title.endswith("#shorts"):
            title = re.sub(r'#shorts.*$', '', title, flags=re.IGNORECASE).strip()
            title += " #shorts"

        # Uzunluk kontrolü
        if len(title) < 70:
            if attempt < 2:
                continue
            # Pad et
            title = title.replace(" #shorts", "")
            while len(title) < 65:
                title += " 🔥"
            title = title[:95] + " #shorts"

        if len(title) > 100:
            title = title[:96] + " #shorts"

        # Duplicate kontrol
        if is_duplicate_in_ledger(title, ledger):
            stats["duplicate_retries"] += 1
            print(f"  🔄 Duplicate bulundu, yeniden deneniyor (attempt {attempt+2})...")
            continue

        return title

    # Son çare
    return _fallback_title(hints, channel, slot_num)


def _fallback_title(hints: str, channel: str, slot_num: int) -> str:
    """DeepSeek yoksa template kullan — hints hash'ine göre seçim yap."""
    hints_clean = hints[:50] if hints else ""
    # hints'e göre deterministik index (böylece aynı hint farklı template alır)
    idx = abs(hash(hints + str(slot_num))) % 10 if hints else slot_num % 10
    
    templates = {
        "poster_loop_cinema": [
            f"Sinematik Bir An: {hints_clean} #shorts",
            f"Bu Film Sahnesi Büyüleyici: {hints_clean} #shorts",
            f"Sinema Tarihine Geçen Kare: {hints_clean} #shorts",
            f"İzleyiciyi Ekrana Kilitleyen Sahne: {hints_clean} #shorts",
            f"Bu Kare Film Afişi Olmayı Hak Ediyor: {hints_clean} #shorts",
            f"Görsel Şölen: {hints_clean} #shorts",
            f"Sinematografinin Zirvesi: {hints_clean} #shorts",
            f"Her Karesi Tablo: {hints_clean} #shorts",
            f"Bu Filmden Alınacak Ders: {hints_clean} #shorts",
            f"Unutulmaz Film Anı: {hints_clean} #shorts",
        ],
        "sahnebaddiestr": [
            f"İşte Bu Anın Aurası: {hints_clean} #shorts",
            f"Ekranı Kıran An: {hints_clean} #shorts",
            f"Bu Vibe Başka Seviye: {hints_clean} #shorts",
            f"Stil ve Duruşun Buluştuğu An: {hints_clean} #shorts",
            f"Bu Sahnede Her Şey Var: {hints_clean} #shorts",
            f"Ekran Enerjisi Dorukta: {hints_clean} #shorts",
            f"Bu Anı Kaçıran Çok Şey Kaçırır: {hints_clean} #shorts",
            f"Magazin Dünyasının En İyi Anı: {hints_clean} #shorts",
            f"Bu Kadar Karizma Az Bulunur: {hints_clean} #shorts",
            f"İzlerken Büyülenmemek Elde Değil: {hints_clean} #shorts",
        ],
        "chatkesti": [
            f"Yayında Kopma Anı 😂: {hints_clean} #shorts",
            f"İzlerken Küçük Dilini Yutacaksın: {hints_clean} #shorts",
            f"Bu Anı Kaçırma: {hints_clean} #shorts",
            f"Yayıncı Burada Kendini Aştı: {hints_clean} #shorts",
            f"Chat Bunu Çok Sevdi ❤️: {hints_clean} #shorts",
            f"Gülmekten Kırıldığımız An: {hints_clean} #shorts",
            f"Bu Kesit Olay Oldu: {hints_clean} #shorts",
            f"Yayın Tarihine Geçen An: {hints_clean} #shorts",
            f"Tepkiler Mükemmel: {hints_clean} #shorts",
            f"Bu Anı İzlemeden Ölmeyin: {hints_clean} #shorts",
        ],
    }
    t = templates.get(channel, templates["poster_loop_cinema"])
    return t[idx % len(t)]


def generate_description(hints: str, channel: str, title: str, slot_num: int, ledger: list[dict]) -> str:
    """800+ karakter açıklama üret."""
    channel_info = {
        "poster_loop_cinema": "film sahnesi, sinematik atmosfer, moving poster estetiği",
        "sahnebaddiestr": "ünlü sahnesi, magazin anı, stil ve duruş",
        "chatkesti": "yayıncı kesiti, komik an, şaşırtıcı tepki",
    }
    info = channel_info.get(channel, "video")

    for attempt in range(3):
        prompt = f"""Bir YouTube Shorts video açıklaması yaz. KESİNLİKLE şu kurallara uy:
- En az 800 karakter, en fazla 1200 karakter
- Türkçe, akıcı, ilgi çekici
- ID, VERIFY_NEEDED, dosya adı İÇERMESİN
- Kanal: {channel}
- İçerik: {info}
- Video ipucu: {hints[:100]}
- Başlık: {title}
- 3-5 satır arası, her satır 1-2 cümle
- Son satırda 5-8 hashtag (#shorts, #kanaladi vb.)
- İzleyiciyi yorum yapmaya teşvik et

Sadece açıklama metnini yaz."""

        desc = call_deepseek(prompt, max_tokens=600, temperature=0.7)
        if not desc:
            desc = _fallback_description(hints, channel, title, slot_num)

        # Temizlik
        desc = re.sub(r'^\d{2,3}-[A-Za-z0-9]{6,}[-_]', '', desc)
        desc = re.sub(r'\bVERIFY_NEEDED\b', '', desc, flags=re.IGNORECASE)
        desc = re.sub(r'\b[A-F0-9]{8,}\b', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()

        if len(desc) < 800:
            if attempt < 2:
                continue
            # Pad
            while len(desc) < 800:
                desc += f"\nBu {info} kaçırılmaması gereken anlardan biri. Sizce nasıl?"
            desc = desc[:1200]

        if is_duplicate_in_ledger(desc, ledger):
            stats["duplicate_retries"] += 1
            continue

        return desc

    return _fallback_description(hints, channel, title, slot_num)


def _fallback_description(hints: str, channel: str, title: str, slot_num: int) -> str:
    info = {
        "poster_loop_cinema": "Bu film sahnesi, sinematik atmosferi ve görsel estetiğiyle moving poster formatında yeniden yorumlandı. Her kare, filmin ruhunu yansıtan bir başyapıt.",
        "sahnebaddiestr": "Bu ünlü sahnesi, stil ve duruşun mükemmel birleşimi. Ekran enerjisi ve aura dolu bu anı kaçırmayın.",
        "chatkesti": "Bu yayıncı kesiti, anlık tepkilerin ve eğlenceli anların en saf hali. İzlerken gülmemek elde değil.",
    }
    base = info.get(channel, info["poster_loop_cinema"])
    desc = f"""{title.replace(' #shorts', '')}

{base}

Bu tarz içeriklerin devamı için beğenmeyi ve yorum yapmayı unutmayın! Sizce bir sonraki videoda hangi sahne olmalı?

#shorts #{channel} #viral #kesfet #izlenmesigereken
"""
    return desc.strip()


def generate_caption(hints: str, channel: str, title: str, slot_num: int, platform: str, ledger: list[dict]) -> str:
    """Instagram (500+ char) veya TikTok (150-200 char) caption üret."""
    max_len = 500 if platform == "instagram" else 200
    min_len = 500 if platform == "instagram" else 150

    channel_info = {
        "poster_loop_cinema": "film sahnesi, sinema, moving poster",
        "sahnebaddiestr": "ünlü, magazin, stil",
        "chatkesti": "yayıncı, komedi, tepki",
    }
    info = channel_info.get(channel, "video")

    for attempt in range(3):
        prompt = f"""Bir {'Instagram' if platform == 'instagram' else 'TikTok'} caption'ı yaz. KESİNLİKLE:
- {'500-800 karakter' if platform == 'instagram' else '150-200 karakter'}
- Türkçe, samimi, etkileşim odaklı
- ID, VERIFY_NEEDED, dosya adı İÇERMESİN
- Kanal: {channel} ({info})
- Başlık: {title}
- {'3-5 satır, son satırda 5-8 hashtag' if platform == 'instagram' else '1-2 satır, sonunda 3-5 hashtag'}
- İzleyiciyi yorum yapmaya teşvik et

Sadece caption metnini yaz."""

        caption = call_deepseek(prompt, max_tokens=400 if platform == "instagram" else 150, temperature=0.7)
        if not caption:
            caption = _fallback_caption(hints, channel, title, platform)

        # Temizlik
        caption = re.sub(r'^\d{2,3}-[A-Za-z0-9]{6,}[-_]', '', caption)
        caption = re.sub(r'\bVERIFY_NEEDED\b', '', caption, flags=re.IGNORECASE)
        caption = re.sub(r'\s+', ' ', caption).strip()

        if len(caption) < min_len:
            if attempt < 2:
                continue
            while len(caption) < min_len:
                caption += f"\nBu anı nasıl buldunuz? Yorumlara yazın!"
            caption = caption[:max_len + 100]

        if len(caption) > max_len + 100:
            caption = caption[:max_len + 97] + "..."

        if is_duplicate_in_ledger(caption, ledger):
            stats["duplicate_retries"] += 1
            continue

        return caption

    return _fallback_caption(hints, channel, title, platform)


def _fallback_caption(hints: str, channel: str, title: str, platform: str) -> str:
    title_clean = title.replace(" #shorts", "")
    if platform == "instagram":
        return f"""{title_clean}

Bu anı izlerken hissettiklerinizi yorumlara yazın! Sizce bir sonraki videoda hangi sahne olmalı?

Beğenmeyi ve takip etmeyi unutmayın! ❤️

#shorts #{channel} #viral #kesfet #izlenmesigereken #trend
"""
    else:
        return f"{title_clean} Bu an kaçmaz! #shorts #{channel} #viral"


def process_slot(slot: dict, ledger: list[dict]) -> dict:
    """Tek bir slot'u yeniden üret."""
    channel = slot.get("channel", "")
    slot_num = slot.get("slot", 0)
    file_path = slot.get("file", "")
    queue_item_id = slot.get("queueItemId", "")

    # Dosya adından ipuçları çıkar
    hints = extract_hints_from_file(file_path, channel)
    if not hints:
        hints = queue_item_id

    print(f"\n  [{channel}] Slot #{slot_num}: {hints[:60]}...")

    # Başlık üret
    title = generate_title(hints, channel, slot_num, ledger)
    slot["youtubeTitle"] = title
    print(f"    Başlık ({len(title)} char): {title}")

    # Açıklama üret
    desc = generate_description(hints, channel, title, slot_num, ledger)
    slot["youtubeDescription"] = desc
    print(f"    Açıklama ({len(desc)} char)")

    # Instagram caption üret
    ig_caption = generate_caption(hints, channel, title, slot_num, "instagram", ledger)
    slot["instagramCaption"] = ig_caption
    print(f"    IG Caption ({len(ig_caption)} char)")

    # TikTok caption üret
    tt_caption = generate_caption(hints, channel, title, slot_num, "tiktok", ledger)
    slot["tiktokCaption"] = tt_caption
    print(f"    TT Caption ({len(tt_caption)} char)")

    # Ledger'a ekle
    ledger.append({
        "title": title,
        "description": desc[:100],
        "caption": ig_caption[:100],
        "channel": channel,
        "slot": slot_num,
        "generated_at": datetime.now().isoformat(),
    })

    return slot


def main():
    global DEEPSEEK_API_KEY, stats

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Sadece ilk N slot")
    parser.add_argument("--dry-run", action="store_true", help="Her kanaldan 1 ornek, kaydetme")
    parser.add_argument("--channel", help="Sadece bu kanal")
    args = parser.parse_args()

    print("=" * 60)
    print("SMU SCHEDULE YENIDEN URETIM V2.0")
    print("=" * 60)

    # Config'den API anahtarini al
    config = load_config()
    DEEPSEEK_API_KEY = config.get("deepseek_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    if DEEPSEEK_API_KEY:
        print(f"DeepSeek API anahtari bulundu (...{DEEPSEEK_API_KEY[-4:]})")
    else:
        print("UYARI: DeepSeek API anahtari YOK")

    # Schedule'u yukle
    schedule = load_schedule()
    all_slots = schedule.get("slots", [])

    # Filtre uygula
    slots = all_slots
    if args.channel:
        slots = [s for s in all_slots if s.get("channel") == args.channel]
    if args.dry_run:
        sample = []
        seen = set()
        for s in slots:
            ch = s.get("channel")
            if ch not in seen:
                sample.append(s)
                seen.add(ch)
            if len(seen) == 3:
                break
        slots = sample
        print(f"DRY-RUN MODU: {len(slots)} slot test edilecek (kaydedilmeyecek)")
    elif args.limit:
        slots = slots[:args.limit]
        print(f"LIMIT: {len(slots)} slot")

    stats["total_slots"] = len(slots)
    print(f"\nIslenecek slot: {len(slots)} / toplam {len(all_slots)}")

    # Ledger'i yukle
    ledger = load_ledger()
    print(f"Ledger girisi: {len(ledger)}")

    # Kanal bazinda say
    for slot in slots:
        ch = slot.get("channel", "unknown")
        stats["channels"][ch] = stats["channels"].get(ch, 0) + 1

    for ch, count in stats["channels"].items():
        print(f"  {ch}: {count} slot")

    # Her slot'u isle
    print("\n" + "=" * 60)
    print("ISLEME BASLIYOR...")
    print("=" * 60)

    # Index map (orjinal slot konumu)
    slot_id_to_idx = {f"{s.get('channel')}-{s.get('slot', i)}": i for i, s in enumerate(all_slots)}

    processed = 0
    for i, slot in enumerate(slots):
        try:
            slot = process_slot(slot, ledger)
            slots[i] = slot
            # Orjinal listeye de yaz
            key = f"{slot.get('channel')}-{slot.get('slot')}"
            if key in slot_id_to_idx:
                all_slots[slot_id_to_idx[key]] = slot
            processed += 1
            # Her 10 slot'ta bir kaydet
            if not args.dry_run and (i + 1) % 10 == 0:
                schedule["slots"] = all_slots
                save_schedule(schedule)
                save_ledger(ledger)
                print(f"\n  CHECKPOINT: {i+1}/{len(slots)} kaydedildi")
            time.sleep(0.3)
        except Exception as e:
            print(f"  HATA: Slot #{slot.get('slot', '?')} ({slot.get('channel', '?')}): {e}")
            stats["deepseek_errors"] += 1

    # Son kaydet
    if not args.dry_run:
        schedule["slots"] = all_slots
        schedule["regenerated_at"] = datetime.now().isoformat()
        schedule["regeneration_stats"] = stats
        save_schedule(schedule)
        save_ledger(ledger)

    stats["ledger_entries"] = len(ledger)

    print("\n" + "=" * 60)
    print("İŞLEM TAMAMLANDI")
    print("=" * 60)
    print(f"✅ İşlenen slot: {processed}/{stats['total_slots']}")
    print(f"📞 DeepSeek çağrısı: {stats['deepseek_calls']}")
    print(f"❌ DeepSeek hatası: {stats['deepseek_errors']}")
    print(f"🔄 Duplicate retry: {stats['duplicate_retries']}")
    print(f"📝 Ledger girişi: {stats['ledger_entries']}")
    print(f"💾 Schedule kaydedildi: {SCHEDULE_FILE}")
    print(f"💾 Ledger kaydedildi: {LEDGER_FILE}")


if __name__ == "__main__":
    main()
