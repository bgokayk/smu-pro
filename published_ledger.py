#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Published Ledger — Gelişmiş duplicate paylaşım koruması.

published_registry.json'dan farkı:
- clip_id, channel, platform, url, publishedAt, title_hash, description_hash kaydeder
- Levenshtein benzerlik kontrolü (>0.85 ise duplicate)
- Aynı gün içinde aynı kanala aynı film/yayıncı 2 kez girerse cooldown
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEDGER_FILE = ROOT / "state" / "published_ledger.json"


def _hash_text(text: str) -> str:
    """Metnin SHA256 hash'ini döndür."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """İki metin arasındaki Levenshtein benzerlik oranı (0.0 - 1.0)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Küçült ve temizle
    s1 = re.sub(r"\s+", " ", s1.lower()).strip()
    s2 = re.sub(r"\s+", " ", s2.lower()).strip()

    if s1 == s2:
        return 1.0

    # Levenshtein mesafesi
    len1, len2 = len(s1), len(s2)
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    prev_row = list(range(len2 + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(
                min(
                    prev_row[j + 1] + 1,  # deletion
                    curr_row[j] + 1,       # insertion
                    prev_row[j] + cost,    # substitution
                )
            )
        prev_row = curr_row

    distance = prev_row[len2]
    max_len = max(len1, len2)
    if max_len == 0:
        return 1.0
    return 1.0 - (distance / max_len)


def _extract_film_or_streamer(item: dict[str, Any]) -> str:
    """Item'dan film adı veya yayıncı adı çıkar."""
    # Metadata'dan dene
    meta = item.get("metadata", {})
    film_identity = meta.get("film_identity", {})
    if film_identity.get("title"):
        title = film_identity["title"]
        title = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", title)
        title = re.sub(r"[-_]", " ", title)
        title = re.sub(r"-poster-loop.*$", "", title)
        return title.strip()

    # ID'den dene
    item_id = item.get("id", "")
    if item_id:
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", item_id)
        clean = re.sub(r"[-_]", " ", clean)
        if clean and len(clean) > 5:
            return clean

    # Dosya adından dene
    file_path = item.get("file", "")
    if file_path:
        stem = Path(file_path).stem
        clean = re.sub(r"^\d{2,3}-[A-Za-z0-9]+-", "", stem)
        clean = re.sub(r"[-_]", " ", clean)
        clean = re.sub(r"-poster-loop.*$", "", clean)
        if clean and len(clean) > 5:
            return clean

    return ""


class PublishedLedger:
    """Gelişmiş duplicate engelleyici ledger."""

    def __init__(self):
        self.file_path = LEDGER_FILE
        self.entries: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.file_path.exists():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8-sig"))
                if isinstance(data, list):
                    self.entries = data
                elif isinstance(data, dict):
                    self.entries = data.get("entries", [])
            except Exception:
                self.entries = []

    def save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(
                {"entries": self.entries[-5000:]},  # Son 5000 kayıt
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8-sig",
        )

    def add_entry(
        self,
        clip_id: str,
        channel: str,
        platform: str = "youtube",
        url: str = "",
        title: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Yeni yayın kaydı ekle."""
        entry = {
            "clip_id": clip_id,
            "channel": channel,
            "platform": platform,
            "url": url,
            "title": title,
            "description": description,
            "title_hash": _hash_text(title),
            "description_hash": _hash_text(description),
            "film_or_streamer": _extract_film_or_streamer(metadata or {}),
            "publishedAt": datetime.now().isoformat(timespec="seconds"),
            "publishedDate": date.today().isoformat(),
        }
        self.entries.append(entry)
        self.save()

    def is_duplicate(
        self,
        clip_id: str,
        channel: str,
        title: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        similarity_threshold: float = 0.85,
    ) -> tuple[bool, str]:
        """Duplicate kontrolü.

        Returns:
            (is_duplicate: bool, reason: str)
        """
        # 1. Birebir clip_id kontrolü
        for entry in self.entries:
            if entry.get("clip_id") == clip_id and entry.get("channel") == channel:
                return True, f"clip_id '{clip_id}' daha önce {channel}'da yayınlanmış"

        # 2. Title hash benzerlik kontrolü
        if title:
            new_title_hash = _hash_text(title)
            for entry in self.entries:
                if entry.get("channel") != channel:
                    continue
                old_title = entry.get("title", "")
                if old_title and _levenshtein_ratio(title, old_title) > similarity_threshold:
                    return True, f"Başlık benzerliği >{similarity_threshold}: '{title[:50]}' ≈ '{old_title[:50]}'"

        # 3. Description hash benzerlik kontrolü
        if description:
            new_desc_hash = _hash_text(description)
            for entry in self.entries:
                if entry.get("channel") != channel:
                    continue
                old_desc = entry.get("description", "")
                if old_desc and _levenshtein_ratio(description, old_desc) > similarity_threshold:
                    return True, f"Açıklama benzerliği >{similarity_threshold}"

        # 4. Aynı gün aynı film/yayıncı cooldown
        if metadata:
            film = _extract_film_or_streamer(metadata)
            if film:
                today = date.today().isoformat()
                for entry in self.entries:
                    if (
                        entry.get("channel") == channel
                        and entry.get("publishedDate") == today
                        and entry.get("film_or_streamer")
                        and _levenshtein_ratio(film, entry["film_or_streamer"]) > 0.8
                    ):
                        return True, f"Aynı film/yayıncı bugün daha önce yayınlanmış: '{film}'"

        return False, ""

    def get_channel_stats(self, channel: str) -> dict[str, Any]:
        """Kanal istatistiklerini döndür."""
        channel_entries = [e for e in self.entries if e.get("channel") == channel]
        return {
            "total_published": len(channel_entries),
            "today_published": sum(
                1 for e in channel_entries if e.get("publishedDate") == date.today().isoformat()
            ),
            "last_published": channel_entries[-1] if channel_entries else None,
        }

    def get_all_stats(self) -> dict[str, Any]:
        """Tüm istatistikleri döndür."""
        channels = set(e.get("channel", "unknown") for e in self.entries)
        return {
            "total_entries": len(self.entries),
            "channels": {ch: self.get_channel_stats(ch) for ch in sorted(channels)},
        }


# Singleton
_ledger_instance: PublishedLedger | None = None


def get_ledger() -> PublishedLedger:
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = PublishedLedger()
    return _ledger_instance
