#!/usr/bin/env python3
"""Claude AI istemcisi — sadece gerçekten gerektiğinde çağrılır.

Öncelik sırası:
  1. Disk cache'i kontrol et  (ücretsiz, anlık)
  2. Template ile doldur       (ücretsiz, anlık)
  3. [YUKARIDAKİLER YETERSİZ] Claude Haiku'yu çağır
  4. Sonucu cache'e kaydet    (bir daha sorulmaz)

Nasıl kullanılır:
  from claude_client import ClaudeClient
  client = ClaudeClient()
  result = client.identify_and_caption("poster_loop_cinema", item_dict)
  # result: {"status": "ok"|"fallback", "film_identity": {...}, "youtube": {...}, ...}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache" / "ai_outputs"
ENV_FILE  = ROOT / ".env"

# Kanal başına sistem promptu — cache_control ile bir kez yüklenir, sonra bedava
SYSTEM_PROMPTS: dict[str, str] = {
    "poster_loop_cinema": """\
Sen PosterLoopCinema içerik asistanısın.
Kanal: @posterloopcinema | Minimal film posters with scenes moving inside them.
Stil: clean museum poster, cult cinema archive, quiet premium.
Kural: Film yılı/yönetmen/oyuncu bilmiyorsan VERIFY_NEEDED yaz. Spoiler verme. Uzun analiz yazma.
JSON dışında HİÇBİR ŞEY yazma. Sadece JSON döndür.""",

    "sahnebaddiestr": """\
Sen SahneBaddiesTR içerik asistanısın.
Kanal: @sahnebaddiestr | Pop, bright, Y2K, clean magazine energy.
Kural: ifşa, hakaret, vücut yorumu, özel hayat ima yok. Aura/stil/vibe dilini kullan.
JSON dışında HİÇBİR ŞEY yazma. Sadece JSON döndür.""",

    "chatkesti": """\
Sen ChatKesti içerik asistanısın.
Kanal: Türk Twitch/Kick yayıncı kesimleri. Yayıncı üstte, olay/oyun altta. 1080x1920.
Kural: drama/ifşa/hakaret yok. Klip dilini kullan.
JSON dışında HİÇBİR ŞEY yazma. Sadece JSON döndür.""",
}

USER_PROMPTS: dict[str, str] = {
    "poster_loop_cinema": """\
Film ipucu: {film_hint}
Yıl ipucu: {year_hint}
Yönetmen ipucu: {director_hint}
Sahne ipucu: {scene_hint}
Özet ipucu: {summary_hint}

Aşağıdaki JSON'u doldur:
{{
  "film_identity": {{
    "title": "",
    "year": "",
    "director": "",
    "screenplay": "",
    "cast": [],
    "confidence": "high|medium|low"
  }},
  "poster_brief": {{
    "swatches": [],
    "moving_scene_note": ""
  }},
  "youtube": {{
    "title": "",
    "description": ""
  }},
  "instagram": {{
    "caption": ""
  }},
  "assumptions": []
}}

YouTube başlık formatı: "[Film Adı] ([Yıl]) — Moving Poster"
YouTube açıklama formatı: 3-4 cümle film konusu (Türkçe veya İngilizce), ardından "Minimal moving poster edit. Which film next?"
Instagram caption: "[Film Adı] ([Yıl]) as a moving poster. Which film next?"
Hashtag ekleme — content_ops ekler.""",

    "sahnebaddiestr": """\
Kişi ipucu: {person_hint}
Program ipucu: {program_hint}
Sahne açıklaması: {scene_description}

Aşağıdaki JSON'u doldur:
{{
  "person_identity": {{
    "name": "",
    "program": "",
    "confidence": "high|medium|low"
  }},
  "youtube": {{
    "title": "",
    "description": ""
  }},
  "instagram": {{
    "caption": ""
  }},
  "safety_flags": [],
  "assumptions": []
}}

YouTube başlık: "[Kişi Adı] — [kısa vibe/aura kelimesi] #shorts"
YouTube açıklama: 1-2 cümle sahne bağlamı + "Bu sahnenin enerjisi ayrı." + soru
Instagram caption: kısa, vibe odaklı, soru ile biter
Kural: vücut/yaş yorumu, özel hayat ima YOK.""",

    "chatkesti": """\
Yayıncı: {streamer}
Platform: {platform}
Oyun/bağlam: {game}
Klip açıklaması: {clip_description}

Aşağıdaki JSON'u doldur:
{{
  "streamer_identity": {{
    "name": "",
    "platform": "",
    "game": "",
    "confidence": "high|medium|low"
  }},
  "youtube": {{
    "title": "",
    "description": ""
  }},
  "instagram": {{
    "caption": ""
  }},
  "assumptions": []
}}

YouTube başlık: "[Yayıncı] — [kısa olay] #shorts"
YouTube açıklama: klip bağlamı + "Bir sonraki hangi yayıncı gelsin?"
Instagram caption: kısa, klip diliyle, soru ile biter""",
}


# ── env / API key ─────────────────────────────────────────────────────────────

def _load_env() -> None:
    """ROOT/.env dosyasından ortam değişkenlerini yükle."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_api_key() -> str:
    _load_env()
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ── cache ─────────────────────────────────────────────────────────────────────

def _cache_key(channel_id: str, item: dict[str, Any]) -> str:
    relevant = {
        k: item.get(k, "")
        for k in ["film_hint", "year_hint", "director_hint",
                  "person_hint", "program_hint",
                  "streamer", "game",
                  "raw_title", "id"]
    }
    raw = channel_id + json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _cache_path(channel_id: str, key: str) -> Path:
    return CACHE_DIR / channel_id / f"{key}.json"


def _read_cache(channel_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    key = _cache_key(channel_id, item)
    path = _cache_path(channel_id, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(channel_id: str, item: dict[str, Any], result: dict[str, Any]) -> None:
    key = _cache_key(channel_id, item)
    path = _cache_path(channel_id, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cached_at": _now_iso(), "item_id": item.get("id"), **result},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now().isoformat(timespec="seconds")


# ── template fallback ─────────────────────────────────────────────────────────

def _template_result(channel_id: str, item: dict[str, Any]) -> dict[str, Any]:
    """Temel şablonla çıktı üret — AI gerektirmez."""
    if channel_id == "poster_loop_cinema":
        film = item.get("film_hint") or item.get("raw_title") or item.get("id") or "Unknown Film"
        year = item.get("year_hint") or ""
        title_label = f"{film} ({year})" if year else film
        return {
            "source": "template",
            "film_identity": {
                "title": film, "year": year,
                "director": item.get("director_hint", ""),
                "cast": [], "confidence": "low",
            },
            "youtube": {
                "title": f"{title_label} — Moving Poster",
                "description": (
                    f"{title_label}\n\n"
                    "Minimal moving poster edit. Film atmosferi tek sahne ve poster şablonu içinde.\n\n"
                    "Which film next?"
                ),
            },
            "instagram": {"caption": f"{title_label} as a moving poster. Which film next?"},
        }

    if channel_id == "sahnebaddiestr":
        person = item.get("person_hint") or item.get("raw_title") or "Ünlü"
        program = item.get("program_hint") or ""
        label = f"{person} — {program}" if program else person
        return {
            "source": "template",
            "person_identity": {"name": person, "program": program, "confidence": "low"},
            "youtube": {
                "title": f"{person} #shorts",
                "description": f"{label}\n\nBu sahnenin enerjisi ayrı.\n\nSence bu anın aurası kaç/10?",
            },
            "instagram": {"caption": f"{label}\n\nBu vibe direkt editlik.\n\nSence? 👀"},
        }

    if channel_id == "chatkesti":
        streamer = item.get("streamer") or item.get("raw_title") or "Yayıncı"
        game = item.get("game") or ""
        return {
            "source": "template",
            "streamer_identity": {"name": streamer, "platform": item.get("platform", ""), "game": game, "confidence": "low"},
            "youtube": {
                "title": f"{streamer} #shorts",
                "description": f"{streamer}\n\nYayın burada koptu.\n\nBir sonraki hangi yayıncı gelsin?",
            },
            "instagram": {"caption": f"{streamer}\n\nYayın burada koptu.\n\nHangi yayıncı gelsin?"},
        }

    return {"source": "template"}


def _needs_ai(channel_id: str, item: dict[str, Any]) -> bool:
    """AI çağrısına gerek var mı?"""
    if channel_id == "poster_loop_cinema":
        film = item.get("film_hint", "").strip()
        # Dosya adından anlamlı film adı çıkarılamıyorsa
        if not film or film == item.get("id", "") or len(film) < 4:
            return True
        # Yıl ve yönetmen yoksa
        if not item.get("year_hint") and not item.get("director_hint"):
            return True
    if channel_id == "sahnebaddiestr":
        person = item.get("person_hint", "").strip()
        if not person or len(person) < 3:
            return True
    return False


# ── Claude çağrısı ────────────────────────────────────────────────────────────

def _build_user_message(channel_id: str, item: dict[str, Any]) -> str:
    template = USER_PROMPTS.get(channel_id, "")
    return template.format(
        film_hint      = item.get("film_hint", ""),
        year_hint      = item.get("year_hint", ""),
        director_hint  = item.get("director_hint", ""),
        scene_hint     = item.get("scene_hint", ""),
        summary_hint   = (item.get("summary_hint") or "")[:300],
        person_hint    = item.get("person_hint", ""),
        program_hint   = item.get("program_hint", ""),
        scene_description = item.get("scene_description", ""),
        streamer       = item.get("streamer", ""),
        platform       = item.get("platform", ""),
        game           = item.get("game", ""),
        clip_description = item.get("clip_description", ""),
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    # Markdown code block temizle
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # İlk { ... } bloğunu bul
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}


class ClaudeClient:
    MODEL = "claude-haiku-4-5-20251001"  # En ucuz, en hızlı

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key or _get_api_key()
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY bulunamadı. "
                    ".env dosyasına ANTHROPIC_API_KEY=sk-ant-... ekle."
                )
            import anthropic  # noqa: PLC0415
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _call_api(self, channel_id: str, item: dict[str, Any]) -> dict[str, Any]:
        """Claude Haiku çağrısı — prompt caching aktif."""
        client = self._get_client()
        system_text = SYSTEM_PROMPTS.get(channel_id, "Sadece JSON döndür.")
        user_text   = _build_user_message(channel_id, item)

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=self.MODEL,
                    max_tokens=512,
                    system=[
                        {
                            "type": "text",
                            "text": system_text,
                            "cache_control": {"type": "ephemeral"},  # İlk çağrıdan sonra bedava
                        }
                    ],
                    messages=[{"role": "user", "content": user_text}],
                )
                raw = response.content[0].text if response.content else "{}"
                parsed = _parse_json_response(raw)
                if parsed:
                    parsed["source"] = "claude"
                    parsed["model"]  = self.MODEL
                    parsed["usage"]  = {
                        "input_tokens":  response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_read":    getattr(response.usage, "cache_read_input_tokens", 0),
                    }
                    return parsed
            except Exception as exc:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Claude API hatası: {exc}") from exc

        return {}

    def identify_and_caption(
        self,
        channel_id: str,
        item: dict[str, Any],
        force_ai: bool = False,
    ) -> dict[str, Any]:
        """
        Ana metod. Önce cache, sonra template, sonra (gerekirse) Claude.

        Döndürür:
          {"source": "cache"|"template"|"claude", ...metadata...}
        """
        # 1. Cache'e bak
        cached = _read_cache(channel_id, item)
        if cached:
            return {**cached, "source": "cache"}

        # 2. AI gerekli mi?
        use_ai = force_ai or (_get_api_key() and _needs_ai(channel_id, item))

        if use_ai:
            try:
                result = self._call_api(channel_id, item)
                if result:
                    _write_cache(channel_id, item, result)
                    return result
            except Exception as exc:
                # AI başarısız → template'e düş, hata logla
                print(f"[claude_client] API hata, template'e dönülüyor: {exc}")

        # 3. Template
        result = _template_result(channel_id, item)
        # Template'i de cache'e yaz — bir daha sorulmaz
        _write_cache(channel_id, item, result)
        return result

    def batch(
        self,
        channel_id: str,
        items: list[dict[str, Any]],
        force_ai: bool = False,
    ) -> list[dict[str, Any]]:
        """Birden fazla item işle."""
        results = []
        for item in items:
            result = self.identify_and_caption(channel_id, item, force_ai=force_ai)
            results.append({"id": item.get("id"), **result})
            # Rate limit: API çağrısıysa biraz bekle
            if result.get("source") == "claude":
                time.sleep(0.5)
        return results


# ── CLI (test amaçlı) ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Claude istemci testi")
    parser.add_argument("--channel", default="poster_loop_cinema")
    parser.add_argument("--film", default="")
    parser.add_argument("--year", default="")
    parser.add_argument("--person", default="")
    parser.add_argument("--force-ai", action="store_true")
    args = parser.parse_args()

    client = ClaudeClient()
    item: dict[str, Any] = {"id": "test-001"}

    if args.channel == "poster_loop_cinema":
        item["film_hint"] = args.film or "The Matrix"
        item["year_hint"] = args.year or "1999"
    elif args.channel == "sahnebaddiestr":
        item["person_hint"] = args.person or "Hadise"

    result = client.identify_and_caption(args.channel, item, force_ai=args.force_ai)
    print(json.dumps(result, ensure_ascii=False, indent=2))
