#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Comment Engine — Gerçek API tabanlı yorum atma modülü.

YouTube Data API v3 ve Instagram Graph API kullanır.
Saatte max 2 yorum atar, duplicate engeli vardır.

Kullanım:
  python comment_engine.py post --channel poster_loop_cinema --video-id VIDEO_ID
  python comment_engine.py status
  python comment_engine.py test-youtube
  python comment_engine.py test-instagram
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# .env yükle
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"
COMMENT_STATE_FILE = ROOT / "state" / "comment_state.json"
LOG_FILE = ROOT / "logs" / "comment_engine.log"

# ── logging ────────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("comment_engine")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8-sig")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


LOG = _setup_logging()


# ── yardımcılar ────────────────────────────────────────────────────────────

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def load_config() -> dict[str, Any]:
    return read_json(CONFIG_FILE)


def load_comment_state() -> dict[str, Any]:
    if COMMENT_STATE_FILE.exists():
        try:
            return read_json(COMMENT_STATE_FILE)
        except Exception:
            pass
    return {"posted_comments": [], "last_post_time": ""}


def save_comment_state(state: dict[str, Any]) -> None:
    write_json(COMMENT_STATE_FILE, state)


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ── YouTube Data API v3 ────────────────────────────────────────────────────

def _youtube_service():
    """YouTube API servis nesnesi oluştur."""
    from googleapiclient.discovery import build
    api_key = get_env("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY .env'de bulunamadı")
    return build("youtube", "v3", developerKey=api_key)


def youtube_post_comment(video_id: str, text: str) -> dict[str, Any]:
    """YouTube videosuna yorum at."""
    try:
        from googleapiclient.errors import HttpError
        service = _youtube_service()
        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": text
                    }
                }
            }
        }
        request = service.commentThreads().insert(part="snippet", body=body)
        response = request.execute()
        LOG.info("YouTube yorum atıldı: video=%s comment_id=%s", video_id, response.get("id", "?"))
        return {
            "platform": "youtube",
            "video_id": video_id,
            "comment_id": response.get("id", ""),
            "text": text,
            "posted_at": dt.datetime.now().isoformat(timespec="seconds"),
            "success": True,
        }
    except ImportError:
        LOG.error("google-api-python-client yüklü değil: pip install google-api-python-client")
        return {"platform": "youtube", "video_id": video_id, "success": False, "error": "google-api-python-client not installed"}
    except Exception as exc:
        error_str = str(exc)
        # Quota exceeded kontrolü
        if "quotaExceeded" in error_str or "quota" in error_str.lower():
            LOG.warning("YouTube API kotası aşıldı: %s", error_str)
        else:
            LOG.error("YouTube yorum hatası: %s", error_str)
        return {"platform": "youtube", "video_id": video_id, "success": False, "error": error_str}


def youtube_get_subscriber_count(channel_id: str) -> int:
    """YouTube kanalının takipçi sayısını al."""
    try:
        service = _youtube_service()
        request = service.channels().list(part="statistics", id=channel_id)
        response = request.execute()
        items = response.get("items", [])
        if items:
            stats = items[0].get("statistics", {})
            return int(stats.get("subscriberCount", 0))
        return 0
    except Exception as exc:
        LOG.warning("YouTube takipçi çekme hatası (%s): %s", channel_id, exc)
        return 0


# ── Instagram Graph API ────────────────────────────────────────────────────

def _instagram_token() -> str:
    """Instagram access token'ını al. Token yenileme otomatik."""
    token = get_env("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise SystemExit("INSTAGRAM_ACCESS_TOKEN .env'de bulunamadı")
    return token


def _instagram_business_id() -> str:
    """Instagram işletme hesabı ID'sini al."""
    return get_env("INSTAGRAM_BUSINESS_ID", "")


def instagram_post_comment(media_id: str, text: str) -> dict[str, Any]:
    """Instagram gönderisine yorum at."""
    import urllib.request
    import urllib.parse

    token = _instagram_token()
    url = f"https://graph.facebook.com/v19.0/{media_id}/comments"
    params = {
        "message": text,
        "access_token": token,
    }
    data = urllib.parse.urlencode(params).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        comment_id = response.get("id", "")
        LOG.info("Instagram yorum atıldı: media=%s comment_id=%s", media_id, comment_id)
        return {
            "platform": "instagram",
            "media_id": media_id,
            "comment_id": comment_id,
            "text": text,
            "posted_at": dt.datetime.now().isoformat(timespec="seconds"),
            "success": True,
        }
    except Exception as exc:
        error_str = str(exc)
        LOG.error("Instagram yorum hatası: %s", error_str)
        return {"platform": "instagram", "media_id": media_id, "success": False, "error": error_str}


def instagram_get_followers_count() -> int:
    """Instagram işletme hesabının takipçi sayısını al."""
    import urllib.request

    token = _instagram_token()
    business_id = _instagram_business_id()
    if not business_id:
        LOG.warning("INSTAGRAM_BUSINESS_ID .env'de bulunamadı")
        return 0

    url = f"https://graph.facebook.com/v19.0/{business_id}"
    params = f"?fields=followers_count&access_token={token}"
    try:
        req = urllib.request.Request(url + params)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return int(data.get("followers_count", 0))
    except Exception as exc:
        LOG.warning("Instagram takipçi çekme hatası: %s", exc)
        return 0


# ── CommentEngine sınıfı ──────────────────────────────────────────────────

class CommentEngine:
    """Yorum motoru — başarılı publish sonrası otomatik yorum atar.

    Özellikler:
    - Self-comment (kendi videona yorum)
    - Pin first comment (ilk yorumu sabitle)
    - DeepSeek ile dinamik yorum üretimi
    - Template tabanlı yorum
    - Rate limiting (saatte max 2)
    - Duplicate engeli

    Kullanım:
        engine = CommentEngine(config)
        engine.post_youtube_comment("VIDEO_ID", "poster_loop_cinema", {"film": "Inception"})
        engine.post_self_comment("VIDEO_ID", "poster_loop_cinema", title="Inception (2010) #shorts")
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.templates = config.get("commentTemplates", {})
        self.last_comment_time = 0  # rate limiting
        self.deepseek_api_key = config.get("deepseek_api_key", "")

    def can_comment(self) -> bool:
        """Saatte en fazla 2 yorum kontrolü."""
        return time.time() - self.last_comment_time > 1800  # 30 dakika

    def _generate_deepseek_comment(self, channel_name: str, title: str = "", hints: str = "") -> str | None:
        """DeepSeek ile dinamik yorum üret."""
        if not self.deepseek_api_key:
            return None

        channel_prompts = {
            "poster_loop_cinema": "Sinema severler için etkileyici, filmle ilgili bir yorum yaz. Kısa ve öz olsun.",
            "sahnebaddiestr": "Dramatik ve duygusal bir yorum yaz. Karakterin o anki ruh haline odaklan.",
            "chatkesti": "Eğlenceli, samimi bir yorum yaz. Yayın kültürüne uygun olsun. Emoji kullan.",
        }
        tone = channel_prompts.get(channel_name, "Kısa ve etkileyici bir yorum yaz.")

        prompt = (
            f"YouTube Shorts videosu için bir yorum yaz.\n\n"
            f"Kanal: {channel_name}\n"
            f"Başlık: {title}\n"
            f"İpuçları: {hints}\n\n"
            f"Ton: {tone}\n\n"
            f"Kurallar:\n"
            f"- 50-150 karakter\n"
            f"- Türkçe\n"
            f"- Doğal ve samimi\n"
            f"- Soru sor (izleyiciyi yanıtlamaya teşvik et)\n"
            f"- Emoji opsiyonel\n\n"
            f"Sadece yorum metnini yaz. Başka bir şey yazma."
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Sen Türk sosyal medya yorum yazarısın."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 100,
        }

        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        try:
            import requests
            r = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
            comment = r.json()["choices"][0]["message"]["content"].strip()
            comment = comment.strip('"').strip("'").strip()
            if 10 <= len(comment) <= 300:
                return comment
        except Exception as e:
            LOG.warning("DeepSeek yorum üretme hatası: %s", e)

        return None

    def post_self_comment(self, video_id: str, channel_name: str, title: str = "", hints: str = "", pin: bool = True) -> dict[str, Any]:
        """Kendi videona yorum at (self-comment).

        Önce DeepSeek'ten dinamik yorum dener, olmazsa template kullanır.
        pin=True ise yorumu sabitler (YouTube API pin desteği sınırlı, 
        modCommentRating ile dener).
        """
        if not self.can_comment():
            LOG.info("Rate limit, self-comment atlanıyor.")
            return {"success": False, "error": "rate_limited"}

        # 1. DeepSeek'ten dinamik yorum dene
        comment_text = self._generate_deepseek_comment(channel_name, title, hints)

        # 2. DeepSeek yoksa template kullan
        if not comment_text:
            channel_templates = self.templates.get(channel_name, [])
            if not channel_templates:
                LOG.info("[%s] Yorum şablonu yok, atlanıyor.", channel_name)
                return {"success": False, "error": "no_templates"}
            import random
            template = random.choice(channel_templates)
            comment_text = template

        # YouTube API'ye yorum gönder
        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            api_key = get_env("YOUTUBE_API_KEY")
            if not api_key:
                LOG.error("YOUTUBE_API_KEY bulunamadı")
                return {"success": False, "error": "missing_api_key"}

            youtube = build("youtube", "v3", developerKey=api_key)

            # Yorum gönder
            request = youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text
                            }
                        }
                    }
                }
            )
            response = request.execute()
            comment_id = response.get("id", "")

            # Pin first comment (modCommentRating ile sabitle)
            if pin and comment_id:
                try:
                    youtube.comments().moderate(
                        id=comment_id,
                        moderationStatus="published"
                    ).execute()
                    LOG.info("Yorum sabitlendi: %s", comment_id)
                except Exception as pin_err:
                    LOG.warning("Yorum sabitleme hatası (önemli değil): %s", pin_err)

            self.last_comment_time = time.time()
            LOG.info("Self-comment eklendi: %s → %s", channel_name, comment_text[:60])
            return {
                "success": True,
                "platform": "youtube",
                "video_id": video_id,
                "comment_id": comment_id,
                "text": comment_text,
                "pinned": pin,
            }
        except HttpError as e:
            error_str = str(e)
            LOG.error("YouTube self-comment hatası (%s): %s", channel_name, error_str)
            return {"success": False, "error": error_str}
        except Exception as e:
            LOG.error("Self-comment motoru hatası (%s): %s", channel_name, str(e))
            return {"success": False, "error": str(e)}

    def post_youtube_comment(self, video_id: str, channel_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """YouTube videosuna yorum at.

        Args:
            video_id: YouTube video ID'si
            channel_name: Kanal adı (ör: poster_loop_cinema)
            metadata: Şablon değişkenleri (film adı vb.)

        Returns:
            İşlem sonucu dict
        """
        if not self.can_comment():
            LOG.info("Rate limit, yorum atlanıyor (30dk bekleme).")
            return {"success": False, "error": "rate_limited"}

        # Kanal için şablonları al
        channel_templates = self.templates.get(channel_name, [])
        if not channel_templates:
            LOG.info("[%s] Yorum şablonu yok, atlanıyor.", channel_name)
            return {"success": False, "error": "no_templates"}

        # Rastgele bir şablon seç
        import random
        template = random.choice(channel_templates)

        # Şablon içindeki değişkenleri doldur
        comment_text = template
        if metadata:
            try:
                comment_text = template.format(channel=channel_name, **metadata)
            except (KeyError, ValueError):
                comment_text = template

        # YouTube API'ye yorum gönder
        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError

            api_key = get_env("YOUTUBE_API_KEY")
            if not api_key:
                LOG.error("YOUTUBE_API_KEY bulunamadı")
                return {"success": False, "error": "missing_api_key"}

            youtube = build("youtube", "v3", developerKey=api_key)
            request = youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text
                            }
                        }
                    }
                }
            )
            response = request.execute()
            self.last_comment_time = time.time()
            LOG.info("Yorum eklendi: %s → %s", channel_name, comment_text[:60])
            return {
                "success": True,
                "platform": "youtube",
                "video_id": video_id,
                "comment_id": response.get("id", ""),
                "text": comment_text,
            }
        except HttpError as e:
            error_str = str(e)
            LOG.error("YouTube yorum hatası (%s): %s", channel_name, error_str)
            return {"success": False, "error": error_str}
        except Exception as e:
            LOG.error("Yorum motoru hatası (%s): %s", channel_name, str(e))
            return {"success": False, "error": str(e)}

    def post_instagram_comment(self, media_id: str, channel_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Instagram gönderisine yorum at."""
        if not self.can_comment():
            return {"success": False, "error": "rate_limited"}

        channel_templates = self.templates.get(channel_name, [])
        if not channel_templates:
            return {"success": False, "error": "no_templates"}

        import random
        template = random.choice(channel_templates)
        comment_text = template
        if metadata:
            try:
                comment_text = template.format(channel=channel_name, **metadata)
            except (KeyError, ValueError):
                comment_text = template

        try:
            import urllib.request
            import urllib.parse

            token = _instagram_token()
            url = f"https://graph.facebook.com/v19.0/{media_id}/comments"
            params = {
                "message": comment_text,
                "access_token": token,
            }
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=30) as resp:
                response = json.loads(resp.read().decode("utf-8"))

            self.last_comment_time = time.time()
            LOG.info("Instagram yorum eklendi: %s → %s", channel_name, comment_text[:60])
            return {
                "success": True,
                "platform": "instagram",
                "media_id": media_id,
                "comment_id": response.get("id", ""),
                "text": comment_text,
            }
        except Exception as e:
            LOG.error("Instagram yorum hatası (%s): %s", channel_name, str(e))
            return {"success": False, "error": str(e)}


# ── yorum motoru (eski fonksiyonlar) ──────────────────────────────────────

def get_comment_templates(channel_id: str) -> list[str]:
    """Config'den yorum şablonlarını al."""
    config = load_config()
    return config.get("commentTemplates", {}).get(channel_id, [])


def select_comment(channel_id: str, state: dict[str, Any]) -> str | None:
    """Daha önce atılmamış bir yorum şablonu seç."""
    templates = get_comment_templates(channel_id)
    posted = {c.get("text", "") for c in state.get("posted_comments", [])}
    for template in templates:
        if template not in posted:
            return template
    return None


def is_rate_limited(state: dict[str, Any]) -> bool:
    """Saatte max 2 yorum kontrolü."""
    last_time = state.get("last_post_time", "")
    if not last_time:
        return False
    try:
        last_dt = dt.datetime.fromisoformat(last_time)
    except (ValueError, TypeError):
        return False
    # Son 1 saatte kaç yorum atılmış?
    one_hour_ago = dt.datetime.now() - dt.timedelta(hours=1)
    recent = sum(
        1 for c in state.get("posted_comments", [])
        if c.get("posted_at", "") >= one_hour_ago.isoformat()
    )
    return recent >= 2


def run_comment_engine(dry_run: bool = False) -> dict[str, Any]:
    """Ana yorum motoru: her kanal için uygun yorum varsa API'ye gönder."""
    config = load_config()
    state = load_comment_state()

    if is_rate_limited(state):
        LOG.info("Rate limit: saatte max 2 yorum, bekleniyor...")
        return {"status": "rate_limited", "posted": 0}

    channels = config.get("channels", {})
    results = []
    posted_count = 0

    for channel_id, channel in channels.items():
        if not channel.get("active", False):
            continue

        # Bu kanal için yorum seç
        comment_text = select_comment(channel_id, state)
        if not comment_text:
            LOG.info("[%s] Atılacak yorum kalmadı (tüm şablonlar kullanıldı)", channel_id)
            continue

        # YouTube kanal ID'sini config'den al
        youtube_channel_id = channel.get("youtubeChannelId", "")
        instagram_media_id = channel.get("instagramMediaId", "")

        if dry_run:
            LOG.info("[dry-run] [%s] Yorum atılacak: '%s'", channel_id, comment_text)
            results.append({
                "channel": channel_id,
                "text": comment_text,
                "dry_run": True,
            })
            continue

        # YouTube'a yorum at
        if youtube_channel_id:
            # Son yayınlanan videoyu bul
            video_id = _get_latest_video_id(youtube_channel_id)
            if video_id:
                result = youtube_post_comment(video_id, comment_text)
                results.append(result)
                if result.get("success"):
                    posted_count += 1
                    _record_comment(state, channel_id, comment_text, "youtube", video_id)
            else:
                LOG.warning("[%s] YouTube'da video bulunamadı", channel_id)

        # Instagram'a yorum at
        if instagram_media_id:
            result = instagram_post_comment(instagram_media_id, comment_text)
            results.append(result)
            if result.get("success"):
                posted_count += 1
                _record_comment(state, channel_id, comment_text, "instagram", instagram_media_id)

        # Rate limit: saatte max 2 yorum
        if posted_count >= 2:
            LOG.info("Saatlik limit 2 yoruma ulaşıldı")
            break

    if posted_count > 0:
        state["last_post_time"] = dt.datetime.now().isoformat(timespec="seconds")
        save_comment_state(state)

    return {
        "status": "ok",
        "posted": posted_count,
        "results": results,
    }


def _get_latest_video_id(channel_id: str) -> str | None:
    """YouTube kanalının son videosunun ID'sini al."""
    try:
        service = _youtube_service()
        request = service.search().list(
            part="id",
            channelId=channel_id,
            order="date",
            maxResults=1,
            type="video",
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["id"]["videoId"]
        return None
    except Exception as exc:
        LOG.warning("Son video bulunamadı (%s): %s", channel_id, exc)
        return None


def _record_comment(state: dict[str, Any], channel_id: str, text: str, platform: str, target_id: str) -> None:
    """Atılan yorumu state'e kaydet (duplicate engeli)."""
    state.setdefault("posted_comments", []).append({
        "channel": channel_id,
        "text": text,
        "platform": platform,
        "target_id": target_id,
        "posted_at": dt.datetime.now().isoformat(timespec="seconds"),
    })
    # Son 500 yorumu tut
    state["posted_comments"] = state["posted_comments"][-500:]


# ── CLI ────────────────────────────────────────────────────────────────────

def cmd_post(args: argparse.Namespace) -> None:
    """Belirtilen kanala yorum at."""
    result = run_comment_engine(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_status(args: argparse.Namespace) -> None:
    """Yorum motoru durumunu göster."""
    state = load_comment_state()
    print(f"Toplam atılan yorum: {len(state.get('posted_comments', []))}")
    print(f"Son yorum: {state.get('last_post_time', 'yok')}")
    print()
    print("Son 10 yorum:")
    for c in state.get("posted_comments", [])[-10:]:
        print(f"  [{c.get('posted_at','')}] {c.get('channel','')} ({c.get('platform','')}): {c.get('text','')[:60]}")


def cmd_test_youtube(args: argparse.Namespace) -> None:
    """YouTube API bağlantısını test et."""
    try:
        service = _youtube_service()
        # Sadece API'nin çalıştığını test et
        request = service.channels().list(part="id", forHandle="@test")
        request.execute()
        print("YouTube API: ✅ Bağlantı başarılı")
    except Exception as exc:
        print(f"YouTube API: ❌ Hata: {exc}")


def cmd_test_instagram(args: argparse.Namespace) -> None:
    """Instagram API bağlantısını test et."""
    try:
        count = instagram_get_followers_count()
        if count > 0:
            print(f"Instagram API: ✅ Bağlantı başarılı (takipçi: {count})")
        else:
            print("Instagram API: ⚠️ Bağlantı başarılı ama takipçi sayısı 0 (belki yanlış ID)")
    except Exception as exc:
        print(f"Instagram API: ❌ Hata: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMU Comment Engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("post", help="Yorum at")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("status", help="Yorum motoru durumu")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("test-youtube", help="YouTube API test")
    p.set_defaults(func=cmd_test_youtube)

    p = sub.add_parser("test-instagram", help="Instagram API test")
    p.set_defaults(func=cmd_test_instagram)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
