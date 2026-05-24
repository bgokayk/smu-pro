#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Published Registry — Duplicate paylaşım koruması için kalıcı kayıt sistemi.

Her kanal için hangi content_id'lerin daha önce yayınlandığını JSON dosyasında tutar.
Daemon yeniden başlasa bile aynı içerik tekrar yayınlanmaz.

Kullanım:
    from published_registry import PublishedRegistry
    registry = PublishedRegistry()
    if not registry.is_published("poster_loop_cinema", "video123"):
        registry.mark_published("poster_loop_cinema", "video123")
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


PUBLISHED_REGISTRY_FILE = Path(__file__).resolve().parent / "published_registry.json"
DEFAULT_CHANNELS = ["poster_loop_cinema", "sahnebaddiestr", "chatkesti"]


class PublishedRegistry:
    """Published Registry — JSON dosyasında {channel_name: [content_id_list]} şeklinde tutulur."""

    def __init__(self, file_path: str | Path | None = None):
        self.file_path = Path(file_path) if file_path else PUBLISHED_REGISTRY_FILE
        self.data: dict[str, list[str]] = {}
        self.load()

    def load(self) -> None:
        """Registry dosyasını yükle, eksik kanalları ekle."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, PermissionError, OSError):
                self.data = {}
        else:
            self.data = {}

        # Eksik kanalları ekle
        for channel in DEFAULT_CHANNELS:
            if channel not in self.data:
                self.data[channel] = []

    def save(self) -> None:
        """Registry dosyasını atomik yaz."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file_path.with_name(f".{self.file_path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            tmp.replace(self.file_path)
        except Exception:
            # Fallback: doğrudan yaz
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    def is_published(self, channel: str, content_id: str) -> bool:
        """Bu içerik daha önce yayınlanmış mı?"""
        return content_id in self.data.get(channel, [])

    def mark_published(self, channel: str, content_id: str) -> None:
        """İçeriği yayınlanmış olarak işaretle."""
        if channel not in self.data:
            self.data[channel] = []
        if content_id not in self.data[channel]:
            self.data[channel].append(content_id)
            self.save()

    def mark_published_batch(self, channel: str, content_ids: list[str]) -> None:
        """Toplu olarak içerikleri yayınlanmış işaretle."""
        if channel not in self.data:
            self.data[channel] = []
        added = False
        for cid in content_ids:
            if cid not in self.data[channel]:
                self.data[channel].append(cid)
                added = True
        if added:
            self.save()

    def get_published(self, channel: str) -> list[str]:
        """Kanala ait yayınlanmış içerik ID'lerini döndür."""
        return self.data.get(channel, [])

    def get_all(self) -> dict[str, list[str]]:
        """Tüm registry verisini döndür."""
        return dict(self.data)

    def clear_channel(self, channel: str) -> None:
        """Bir kanalın kaydını temizle (test için)."""
        if channel in self.data:
            self.data[channel] = []
            self.save()

    def reset(self) -> None:
        """Tüm registry'yi sıfırla (test için)."""
        self.data = {ch: [] for ch in DEFAULT_CHANNELS}
        self.save()

    def __contains__(self, item: tuple[str, str]) -> bool:
        """'poster_loop_cinema', 'video123' in registry şeklinde kullanım."""
        channel, content_id = item
        return self.is_published(channel, content_id)

    def __len__(self) -> int:
        """Toplam kayıtlı içerik sayısı."""
        return sum(len(ids) for ids in self.data.values())

    def __repr__(self) -> str:
        return f"PublishedRegistry({len(self)} items, {len(self.data)} channels)"


# Singleton instance — modül seviyesinde tek bir örnek
_registry_instance: PublishedRegistry | None = None


def get_registry() -> PublishedRegistry:
    """Singleton registry instance'ını döndür."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = PublishedRegistry()
    return _registry_instance


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Published Registry Manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Registry durumunu göster")
    p.set_defaults(func=lambda a: print(json.dumps(get_registry().get_all(), ensure_ascii=False, indent=2)))

    p = sub.add_parser("check", help="Bir içeriğin yayınlanıp yayınlanmadığını kontrol et")
    p.add_argument("--channel", required=True)
    p.add_argument("--content-id", required=True)
    p.set_defaults(func=lambda a: print(get_registry().is_published(a.channel, a.content_id)))

    p = sub.add_parser("mark", help="Bir içeriği yayınlanmış olarak işaretle")
    p.add_argument("--channel", required=True)
    p.add_argument("--content-id", required=True)
    p.set_defaults(func=lambda a: (get_registry().mark_published(a.channel, a.content_id), print("OK")))

    p = sub.add_parser("reset", help="Registry'yi sıfırla")
    p.add_argument("--channel", default="")
    p.set_defaults(func=lambda a: (get_registry().clear_channel(a.channel) if a.channel else get_registry().reset(), print("OK")))

    args = parser.parse_args()
    args.func(args)
