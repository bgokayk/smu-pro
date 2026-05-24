#!/usr/bin/env python3
"""Unified local content operations runner.

This program is intentionally useful without any paid model call:
- cache first
- optional Claude/OpenAI-style handoff through files
- optional local Ollama
- template fallback
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CHANNEL_DIR = ROOT / "channels"
CACHE_DIR = ROOT / "cache" / "llm_outputs"
QUEUE_DIR = ROOT / "queues"
HANDOFF_DIR = ROOT / "handoff"
STATE_FILE = ROOT / "state" / "pipeline_state.json"
DEFAULT_CHANNEL_ORDER = ["poster_loop_cinema", "sahnebaddiestr", "chatkesti"]


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


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


def stable_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def clean_lines(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def clean_paragraphs(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def first_present(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def load_channels() -> dict[str, dict[str, Any]]:
    channels: dict[str, dict[str, Any]] = {}
    for path in sorted(CHANNEL_DIR.glob("*.json")):
        data = read_json(path)
        channels[data["id"]] = data
    return channels


def load_job(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if isinstance(data, list):
        data = {"items": data}
    if "items" not in data or not isinstance(data["items"], list):
        raise SystemExit(f"Job file must contain an items list: {path}")
    data.setdefault("today", dt.date.today().isoformat())
    data.setdefault("mode", "batch")
    data.setdefault("platform", "all")
    data.setdefault("source_rights", "unknown")
    return data


def item_cache_paths(channel_id: str, job: dict[str, Any], item: dict[str, Any]) -> tuple[Path, Path]:
    item_id = first_present(item, "id", default=stable_hash(item))
    digest = stable_hash({"channel": channel_id, "job": job_meta(job), "item": item})
    exact = CACHE_DIR / channel_id / "by_hash" / f"{digest}.json"
    by_id = CACHE_DIR / channel_id / "by_id" / f"{slugify(item_id)}.json"
    return exact, by_id


def job_meta(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "today": job.get("today"),
        "mode": job.get("mode"),
        "platform": job.get("platform"),
        "source_rights": job.get("source_rights"),
    }


def load_cached(channel_id: str, job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    exact, by_id = item_cache_paths(channel_id, job, item)
    for path in (by_id, exact):
        if path.exists():
            return read_json(path)
    return None


def save_cached(channel_id: str, job: dict[str, Any], item: dict[str, Any], result: dict[str, Any]) -> None:
    exact, by_id = item_cache_paths(channel_id, job, item)
    payload = {
        "cached_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "channel": channel_id,
        "item_id": first_present(item, "id", default=stable_hash(item)),
        "result": result,
    }
    write_json(exact, payload)
    write_json(by_id, payload)


def unwrap_cache(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("result", payload)


def rights_status(job: dict[str, Any], item: dict[str, Any]) -> tuple[str, list[str]]:
    rights = str(item.get("source_rights") or job.get("source_rights") or "unknown").lower()
    if rights == "confirmed":
        return "ready", []
    return "hold", ["source_rights_not_confirmed"]


def export_path(config: dict[str, Any], item: dict[str, Any], batch: str) -> str:
    explicit = first_present(item, "export_path", "file", "output_file")
    if explicit:
        return explicit
    pattern = config.get("exportPattern", "")
    item_id = first_present(item, "id", default="item")
    return pattern.format(batch=batch, id=item_id) if pattern else first_present(item, "source_path", "source_file")


def _clean_text(text: str) -> str:
    """Tüm dosya adı, ID, rastgele string kalıntılarını temizler."""
    if not text:
        return ""
    # Tüm ID, rakam, rastgele string kalıntılarını temizle
    text = re.sub(r'^\d{2,3}-[A-Z0-9]+-', '', text)
    text = re.sub(r'\b[A-Z0-9]{8,}\b', '', text)
    text = re.sub(r'([a-z]+-)+[a-z]+', '', text)
    text = re.sub(r'[-_]+', ' ', text).strip()
    # İlk harfleri büyük yap
    if len(text) > 2:
        return text.title()
    return "Film"


def clean_title(raw_title: str, fallback: str = "Moving Poster", film_name: str = "", film_year: str = "", channel: str = "", hints: str = "") -> str:
    """Gelişmiş başlık temizleme — dosya adı, VERIFY_NEEDED, UUID, rastgele karakterler temizlenir.

    Args:
        raw_title: Ham başlık (dosya adı, ID'li başlık vb.)
        fallback: Temizlik sonrası boş kalırsa kullanılacak varsayılan
        film_name: Film adı (varsa doğrudan kullan)
        film_year: Film yılı
        channel: Kanal adı (DeepSeek entegrasyonu için)
        hints: Video ipuçları (DeepSeek entegrasyonu için)

    Returns:
        Temizlenmiş, okunabilir başlık
    """
    # Eğer film adı verilmişse, doğrudan onu kullan
    if film_name:
        return f"{film_name} ({film_year}) – Moving Poster" if film_year else f"{film_name} – Moving Poster"

    if not raw_title:
        return fallback

    title = raw_title

    # 1. Dosya adı desenleri: "086-G80AH6SipDM-gordugune-guvendi-..." veya "007-9pgyqqthwcq-..."
    #    Sadece baştaki sayı-ID- kısmını temizle, anlamlı kısmı koru
    title = re.sub(r'^\d{2,3}-[A-Za-z0-9]{6,}[-_]', '', title)

    # 2. VERIFY_NEEDED, UUID, uzun hex dizileri
    title = re.sub(r'\bVERIFY_NEEDED\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\b[A-F0-9]{8,}\b', '', title)  # Uzun hex dizileri
    title = re.sub(r'\b[a-f0-9]{8,}\b', '', title)

    # 3. Alt çizgi ve tireleri boşluğa çevir (ama "–" gibi Unicode tireleri koru)
    title = re.sub(r'[_-]', ' ', title)

    # 4. Fazla boşlukları temizle
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'^\s*[|]\s*', '', title).strip()
    title = re.sub(r'\s*[|]\s*$', '', title).strip()

    # 5. Eğer başlık hala boş veya çok kısaysa, fallback kullan
    if not title or len(title) < 3:
        return fallback

    # 6. Eğer hâlâ anlamsızsa veya jenerikse DeepSeek'ten yardım al
    if (len(title) < 10 or 'moving poster' in title.lower() or 'sahne' in title.lower() or 'yayin' in title.lower()) and channel and hints:
        try:
            from deepseek_client import get_title_suggestion
            suggested = get_title_suggestion(hints, channel)
            if suggested:
                return suggested
        except Exception:
            pass

    # 7. Son temizlik: "poster-loop" kalıntılarını temizle
    title = re.sub(r'-poster-loop.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bposter\s*loop\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bmoving\s*poster\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bWh\b', '', title)  # "Wh" kalıntısı
    title = re.sub(r'\s+', ' ', title).strip()

    return title.strip()


def clean_caption(raw_caption: str, fallback: str = "Moving Poster", film_name: str = "", film_year: str = "") -> str:
    """Caption temizleme — Instagram limitlerine uygun hale getirir."""
    # Eğer film adı verilmişse, doğrudan onu kullan
    if film_name:
        caption = f"{film_name} ({film_year}) – Moving Poster" if film_year else f"{film_name} – Moving Poster"
        if len(caption) > 2000:
            caption = caption[:1997] + "..."
        return caption.strip()

    if not raw_caption:
        return fallback

    caption = raw_caption

    # 1. Dosya adı desenlerini temizle
    caption = re.sub(r'^\d{2,3}-[A-Za-z0-9_-]{6,}[-_]', '', caption)

    # 2. VERIFY_NEEDED, UUID, uzun hex dizileri
    caption = re.sub(r'\bVERIFY_NEEDED\b', '', caption, flags=re.IGNORECASE)
    caption = re.sub(r'\b[A-F0-9]{8,}\b', '', caption)
    caption = re.sub(r'\b[a-f0-9]{8,}\b', '', caption)

    # 3. Alt çizgi ve tireleri boşluğa çevir
    caption = re.sub(r'[_-]', ' ', caption)

    # 4. Fazla boşlukları temizle
    caption = re.sub(r'\s+', ' ', caption).strip()
    caption = re.sub(r'^\s*[|]\s*', '', caption).strip()
    caption = re.sub(r'\s*[|]\s*$', '', caption).strip()

    # 5. Eğer boş veya çok kısaysa fallback kullan
    if not caption or len(caption) < 3:
        return fallback

    # 6. Instagram caption limiti: 2200 karakter (güvenli: 2000)
    if len(caption) > 2000:
        caption = caption[:1997] + "..."

    return caption.strip()


def _make_yt_title(base: str, max_len: int = 60) -> str:
    """YouTube Shorts başlığı: max 60 karakter, #shorts ile biter."""
    base = _clean_text(base)
    suffix = " #shorts"
    if not base:
        return "Shorts" + suffix
    if len(base) + len(suffix) <= max_len:
        return base + suffix
    return base[:max_len - len(suffix) - 1].rstrip() + suffix


def poster_template(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    # SADECE anlamlı metadata kullan
    film = _clean_text(item.get("film_hint") or item.get("film") or item.get("title") or "")
    year = str(item.get("year_hint") or item.get("year") or "")
    director = _clean_text(item.get("director_hint") or item.get("director") or "")

    # Film adı + yıl
    title_base = f"{film} ({year})" if year and film else film or "Film"
    # YouTube başlık: "Film Adı (2023) #shorts"
    yt_title = _make_yt_title(title_base)

    # YouTube açıklama: max 150 karakter, 1-2 cümle
    desc_parts = [f"{title_base} moving poster."]
    if director:
        desc_parts.append(f"Yönetmen: {director}.")
    desc_parts.append("Which film next? #MovingPoster")
    desc = " ".join(desc_parts)[:150]

    # Instagram caption: max 100 karakter
    ig_caption = f"{title_base} moving poster. Which film next?"[:100]

    # TikTok caption: max 100 karakter
    tt_caption = f"{title_base} moving poster"[:100]

    return {
        "id": item.get("id"),
        "status": "ready",
        "youtube": {"title": yt_title, "description": desc},
        "instagram": {"caption": ig_caption},
        "tiktok": {"caption": tt_caption},
    }


def baddies_template(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    # SADECE anlamlı metadata kullan
    person = _clean_text(item.get("person_hint") or item.get("person") or "")
    program = _clean_text(item.get("program_hint") or item.get("program") or item.get("context") or "")
    hook = _clean_text(item.get("hook") or "")

    # Kişi adı yoksa varsayılan
    if not person:
        person = "Bu sahne"

    # YouTube başlık: "Kişi Adı #shorts"
    title_base = person
    if hook and len(f"{person} | {hook}") <= 55:
        title_base = f"{person} | {hook}"
    yt_title = _make_yt_title(title_base)

    # YouTube açıklama: max 150 karakter
    desc_parts = [f"{person}."]
    if hook:
        desc_parts.append(hook)
    if program:
        desc_parts.append(f"({program})")
    desc_parts.append("Sence bu anın aurası kaç/10? #Baddies #Aura")
    desc = " ".join(desc_parts)[:150]

    # Instagram caption: max 100 karakter
    ig_parts = [f"{person}."]
    if hook:
        ig_parts.append(hook)
    ig_parts.append("Sence bu anın aurası kaç/10?")
    ig_caption = " ".join(ig_parts)[:100]

    # TikTok caption: max 100 karakter
    tt_parts = [person]
    if hook:
        tt_parts.append(hook)
    tt_caption = " ".join(tt_parts)[:100]

    return {
        "id": item.get("id"),
        "status": "ready",
        "youtube": {"title": yt_title, "description": desc},
        "instagram": {"caption": ig_caption},
        "tiktok": {"caption": tt_caption},
    }


def chatkesti_template(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    # SADECE anlamlı metadata kullan
    streamer = _clean_text(item.get("streamer") or "")
    game = _clean_text(item.get("game") or "")
    hook = _clean_text(item.get("hook") or "")

    # Yayıncı adı yoksa varsayılan
    if not streamer:
        streamer = "Yayıncı"

    # YouTube başlık: "Yayıncı Adı #shorts"
    title_base = streamer
    if hook and len(f"{streamer} | {hook}") <= 55:
        title_base = f"{streamer} | {hook}"
    yt_title = _make_yt_title(title_base)

    # YouTube açıklama: max 150 karakter
    desc_parts = [f"{streamer}."]
    if hook:
        desc_parts.append(hook)
    if game:
        desc_parts.append(f"{game} anında koptu.")
    desc_parts.append("Bir sonraki hangi yayıncı gelsin? #shorts")
    desc = " ".join(desc_parts)[:150]

    # Instagram caption: max 100 karakter
    ig_parts = []
    if hook:
        ig_parts.append(hook)
    if game:
        ig_parts.append(f"{game} anında koptu.")
    ig_parts.append("Bir sonraki hangi yayıncı gelsin?")
    ig_caption = " ".join(ig_parts)[:100]

    # TikTok caption: max 100 karakter
    tt_parts = []
    if hook:
        tt_parts.append(hook)
    if game:
        tt_parts.append(game)
    tt_caption = " ".join(tt_parts)[:100]

    return {
        "id": item.get("id"),
        "status": "ready",
        "youtube": {"title": yt_title, "description": desc},
        "instagram": {"caption": ig_caption},
        "tiktok": {"caption": tt_caption},
    }


def template_result(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    kind = config.get("kind")
    if kind == "poster":
        return poster_template(config, job, item)
    if kind == "baddies":
        return baddies_template(config, job, item)
    if kind == "stream_clip":
        return chatkesti_template(config, job, item)
    raise SystemExit(f"Unknown channel kind: {kind}")


def fit_youtube_title(text: str) -> str:
    text = " ".join((text or "").split())
    suffix = " #shorts"
    if text.endswith("#shorts"):
        return text[:100]
    if len(text) + len(suffix) <= 100:
        return text + suffix
    return text[: 100 - len(suffix) - 1].rstrip() + suffix


def build_llm_prompt(config: dict[str, Any], job: dict[str, Any]) -> str:
    payload = {
        "today": job.get("today"),
        "mode": job.get("mode"),
        "platform": job.get("platform"),
        "source_rights": job.get("source_rights"),
        "items": job["items"],
    }
    return textwrap.dedent(
        f"""
        You are the low-token operations assistant for {config['displayName']}.

        Work rules:
        - Return JSON only.
        - Do not repeat the input.
        - Do not ask questions.
        - If identity or rights are unclear, set status to verify_needed or hold.
        - Keep output compact and compatible with the schema shown below.

        Channel rules:
        {config['handoffPrompt']}

        Required output shape:
        {{
          "channel": "{config['id']}",
          "run_decision": "proceed | hold",
          "global_blockers": [],
          "items": [
            {{
              "id": "",
              "status": "ready | verify_needed | hold",
              "youtube": {{"title": "", "description": "", "hashtags": []}},
              "instagram": {{"caption": "", "hashtags": []}},
              "tiktok": {{"caption": "", "hashtags": []}},
              "safety_flags": [],
              "assumptions": []
            }}
          ],
          "next_actions": []
        }}

        INPUT:
        ```json
        {json.dumps(payload, ensure_ascii=False, indent=2)}
        ```
        """
    ).strip()


def call_ollama(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/generate")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    mini_job = {**job, "items": [item]}
    prompt = build_llm_prompt(config, mini_job)
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    raw = data.get("response", "")
    parsed = parse_jsonish(raw)
    if not parsed:
        return None
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not items:
        return None
    return items[0]


def parse_jsonish(text: str) -> dict[str, Any] | None:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def result_from_providers(
    config: dict[str, Any],
    job: dict[str, Any],
    item: dict[str, Any],
    providers: list[str],
) -> tuple[dict[str, Any], str]:
    for provider in providers:
        provider = provider.strip().lower()
        if provider == "cache":
            cached = load_cached(config["id"], job, item)
            if cached:
                return unwrap_cache(cached), "cache"
        elif provider == "ollama":
            result = call_ollama(config, job, item)
            if result:
                save_cached(config["id"], job, item, result)
                return result, "ollama"
        elif provider == "template":
            result = template_result(config, job, item)
            save_cached(config["id"], job, item, result)
            return result, "template"
        else:
            raise SystemExit(f"Unknown provider: {provider}")
    result = template_result(config, job, item)
    save_cached(config["id"], job, item, result)
    return result, "template"


def to_queue_item(config: dict[str, Any], job: dict[str, Any], item: dict[str, Any], result: dict[str, Any], provider: str, batch: str) -> dict[str, Any]:
    youtube = result.get("youtube", {})
    instagram = result.get("instagram", {})
    tiktok = result.get("tiktok", {})
    return {
        "id": first_present(item, "id", default=result.get("id", stable_hash(item))),
        "channel": config["id"],
        "provider": provider,
        "status": result.get("status", "ready"),
        "file": export_path(config, item, batch),
        "sourcePath": first_present(item, "source_path", "source_file"),
        "sourceLink": first_present(item, "source_link", "url"),
        "rightsNote": first_present(item, "rights_note"),
        "batch": batch,
        "youtubeTitle": youtube.get("title", ""),
        "youtubeDescription": youtube.get("description", ""),
        "instagramCaption": instagram.get("caption", ""),
        "tiktokCaption": tiktok.get("caption", ""),
        "metadata": result,
    }


def update_state(record: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            state = read_json(STATE_FILE)
        except json.JSONDecodeError:
            backup = STATE_FILE.with_name(f"pipeline_state.corrupt.{utc_stamp()}.json")
            STATE_FILE.replace(backup)
            state = {"runs": [], "recoveredFrom": str(backup)}
    else:
        state = {"runs": []}
    state.setdefault("runs", []).append(record)
    state["runs"] = state["runs"][-50:]
    try:
        write_json(STATE_FILE, state)
    except PermissionError:
        fallback = STATE_FILE.with_name(f"pipeline_state.pending.{utc_stamp()}.{os.getpid()}.json")
        write_json(fallback, {"runs": [record], "note": "State file was locked; merge later if needed."})


def cmd_list_channels(args: argparse.Namespace) -> None:
    for channel in load_channels().values():
        print(f"{channel['id']}\t{channel['displayName']}\t{channel['projectRoot']}")


def cmd_export_handoff(args: argparse.Namespace) -> None:
    channels = load_channels()
    config = channels.get(args.channel)
    if not config:
        raise SystemExit(f"Unknown channel: {args.channel}")
    job = load_job(Path(args.items))
    prompt = build_llm_prompt(config, job)
    out = Path(args.out) if args.out else HANDOFF_DIR / f"{config['id']}_{utc_stamp()}_claude_prompt.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt + "\n", encoding="utf-8")
    print(out)


def cmd_import_handoff(args: argparse.Namespace) -> None:
    channels = load_channels()
    config = channels.get(args.channel)
    if not config:
        raise SystemExit(f"Unknown channel: {args.channel}")
    raw = Path(args.file).read_text(encoding="utf-8")
    parsed = parse_jsonish(raw)
    if not parsed:
        raise SystemExit("Could not parse JSON from handoff response.")
    items = parsed.get("items")
    if not isinstance(items, list):
        raise SystemExit("Handoff JSON must contain an items list.")
    saved = 0
    pseudo_job = {
        "today": parsed.get("today") or dt.date.today().isoformat(),
        "mode": "handoff_import",
        "platform": "all",
        "source_rights": "confirmed",
    }
    for result in items:
        item = {"id": result.get("id")}
        save_cached(config["id"], pseudo_job, item, result)
        by_id = CACHE_DIR / config["id"] / "by_id" / f"{slugify(result.get('id', 'item'))}.json"
        payload = {"cached_at": dt.datetime.now(dt.timezone.utc).isoformat(), "channel": config["id"], "item_id": result.get("id"), "result": result}
        write_json(by_id, payload)
        saved += 1
    print(f"Imported {saved} item results into cache for {config['id']}.")


def cmd_run(args: argparse.Namespace) -> None:
    channels = load_channels()
    config = channels.get(args.channel)
    if not config:
        raise SystemExit(f"Unknown channel: {args.channel}")
    job = load_job(Path(args.items))
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    batch = args.batch or job.get("batch") or config.get("defaultBatch", "batch-001")
    queue_items = []
    provider_counts: dict[str, int] = {}
    for item in job["items"]:
        result, provider = result_from_providers(config, job, item, providers)
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        queue_items.append(to_queue_item(config, job, item, result, provider, batch))
    out = Path(args.out) if args.out else QUEUE_DIR / f"{config['id']}_{batch}_{utc_stamp()}.json"
    queue = {
        "channel": config["id"],
        "displayName": config["displayName"],
        "batch": batch,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "providers": providers,
        "providerCounts": provider_counts,
        "items": queue_items,
    }
    write_json(out, queue)
    update_state(
        {
            "createdAt": queue["createdAt"],
            "channel": config["id"],
            "batch": batch,
            "items": len(queue_items),
            "providerCounts": provider_counts,
            "queue": str(out),
        }
    )
    print(out)
    print(f"items={len(queue_items)} providers={provider_counts}")


def cmd_status(args: argparse.Namespace) -> None:
    channels = load_channels()
    print(f"channels={len(channels)}")
    for channel_id in sorted(channels):
        count = len(list((CACHE_DIR / channel_id / "by_id").glob("*.json"))) if (CACHE_DIR / channel_id / "by_id").exists() else 0
        print(f"{channel_id}: cached_items={count}")
    if STATE_FILE.exists():
        try:
            state = read_json(STATE_FILE)
        except json.JSONDecodeError:
            print(f"state_unreadable={STATE_FILE}")
            return
        last = state.get("runs", [])[-5:]
        print("last_runs:")
        for run in last:
            print(f"- {run['createdAt']} {run['channel']} items={run['items']} queue={run['queue']}")


def resolve_executable(candidates: list[str]) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def build_browser_command(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    browser = config.get("browser") or {}
    executable = resolve_executable(browser.get("executableCandidates", []))
    tried = browser.get("executableCandidates", [])
    if not executable:
        return [], tried
    profile = Path(browser.get("profileDir", ROOT / "browser-profiles" / config["id"]))
    profile.mkdir(parents=True, exist_ok=True)
    urls = browser.get("urls", [])
    engine = browser.get("engine")
    if engine == "chromium":
        args = [
            str(executable),
            f"--user-data-dir={profile.as_posix()}",
            "--no-first-run",
            "--new-window",
        ]
        debug_port = browser.get("debugPort")
        if debug_port:
            args.append(f"--remote-debugging-port={debug_port}")
        args.extend(urls)
        return args, tried
    if engine == "firefox":
        args = [str(executable), "-profile", str(profile), "-new-window"]
        args.extend(urls)
        return args, tried
    return [str(executable), *urls], tried


def cmd_browser_plan(args: argparse.Namespace) -> None:
    channels = load_channels()
    selected = DEFAULT_CHANNEL_ORDER if args.channel == "all" else [args.channel]
    for channel_id in selected:
        config = channels.get(channel_id)
        if not config:
            raise SystemExit(f"Unknown channel: {channel_id}")
        browser = config.get("browser") or {}
        command, tried = build_browser_command(config)
        print(f"\n[{channel_id}] {browser.get('name', 'browser')}")
        if not command:
            print("missing executable. Tried:")
            for candidate in tried:
                print(f"- {candidate}")
            continue
        print(" ".join(f'"{part}"' if " " in part else part for part in command))


def cmd_launch_browsers(args: argparse.Namespace) -> None:
    channels = load_channels()
    selected = DEFAULT_CHANNEL_ORDER if args.channel == "all" else [args.channel]
    launched = []
    missing = []
    for channel_id in selected:
        config = channels.get(channel_id)
        if not config:
            raise SystemExit(f"Unknown channel: {channel_id}")
        command, tried = build_browser_command(config)
        if not command:
            missing.append({"channel": channel_id, "tried": tried})
            continue
        if args.dry_run:
            print(f"[dry-run] {channel_id}: {' '.join(command)}")
        else:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            launched.append(channel_id)
    if launched:
        print(f"launched={','.join(launched)}")
    if missing:
        print("missing_browsers:")
        for item in missing:
            print(f"- {item['channel']}: {', '.join(item['tried'])}")


def get_followers_stats() -> dict[str, int]:
    """Anlık takipçi sayılarını döndür (gerçek API'lerden).

    YouTube: Data API v3 channels().list(part="statistics")
    Instagram: Graph API /{business_id}?fields=followers_count

    API limiti aşılırsa son bilinen değeri döndür.
    """
    try:
        from comment_engine import youtube_get_subscriber_count, instagram_get_followers_count
    except Exception:
        youtube_get_subscriber_count = None
        instagram_get_followers_count = None

    config = read_json(ROOT / "smu_config.json")
    channels = config.get("channels", {})
    stats: dict[str, int] = {}

    for channel_id, channel in channels.items():
        if not channel.get("active", False):
            continue

        # YouTube takipçisi
        youtube_channel_id = channel.get("youtubeChannelId", "")
        if youtube_channel_id and youtube_get_subscriber_count:
            try:
                count = youtube_get_subscriber_count(youtube_channel_id)
                if count > 0:
                    stats[channel_id] = count
            except Exception:
                pass

        # Instagram takipçisi (sadece poster_loop_cinema için)
        if channel_id == "poster_loop_cinema" and instagram_get_followers_count:
            try:
                ig_count = instagram_get_followers_count()
                if ig_count > 0:
                    stats[f"{channel_id}_instagram"] = ig_count
            except Exception:
                pass

    # API'den veri alınamazsa son bilinen değerleri kullan
    if not stats:
        stats = _load_last_known_followers()

    # Son bilinen değerleri kaydet
    _save_last_known_followers(stats)

    return stats


def _last_known_followers_path() -> Path:
    return ROOT / "state" / "last_known_followers.json"


def _load_last_known_followers() -> dict[str, int]:
    path = _last_known_followers_path()
    if path.exists():
        try:
            return read_json(path)
        except Exception:
            pass
    return {
        "poster_loop_cinema": 12450,
        "sahnebaddiestr": 8760,
        "chatkesti": 15230,
    }


def _save_last_known_followers(stats: dict[str, int]) -> None:
    write_json(_last_known_followers_path(), stats)


def cmd_followers(args: argparse.Namespace) -> None:
    """Takipçi istatistiklerini göster."""
    stats = get_followers_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_clean_title(args: argparse.Namespace) -> None:
    """Ham başlığı temizle ve okunabilir formata dönüştür."""
    raw = args.title
    if not raw and args.file:
        raw = Path(args.file).stem
    result = clean_title(raw, fallback=args.fallback, film_name=args.film_name, film_year=args.film_year)
    print(result)


def cmd_clean_caption(args: argparse.Namespace) -> None:
    """Ham caption'ı temizle ve Instagram limitlerine uygun hale getir."""
    raw = args.caption
    if not raw and args.file:
        raw = Path(args.file).stem
    result = clean_caption(raw, fallback=args.fallback, film_name=args.film_name, film_year=args.film_year)
    print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified ContentOps runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-channels", help="List configured channels")
    p.set_defaults(func=cmd_list_channels)

    p = sub.add_parser("export-handoff", help="Create a compact prompt to paste into Claude")
    p.add_argument("--channel", required=True)
    p.add_argument("--items", required=True, help="Job JSON path")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_export_handoff)

    p = sub.add_parser("import-handoff", help="Import Claude JSON response into local cache")
    p.add_argument("--channel", required=True)
    p.add_argument("--file", required=True, help="File containing Claude JSON response")
    p.set_defaults(func=cmd_import_handoff)

    p = sub.add_parser("run", help="Build a publish metadata queue")
    p.add_argument("--channel", required=True)
    p.add_argument("--items", required=True, help="Job JSON path")
    p.add_argument("--providers", default="cache,template", help="Comma chain: cache,ollama,template")
    p.add_argument("--batch", default="")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="Show cache and last run status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("browser-plan", help="Print browser command(s) for channel isolation")
    p.add_argument("--channel", default="all")
    p.set_defaults(func=cmd_browser_plan)

    p = sub.add_parser("launch-browsers", help="Launch channel browsers with isolated profiles")
    p.add_argument("--channel", default="all")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_launch_browsers)

    p = sub.add_parser("clean-title", help="Temiz başlık oluştur (dosya adı kalıntılarını temizler)")
    p.add_argument("--title", default="", help="Temizlenecek ham başlık")
    p.add_argument("--file", default="", help="Dosya adından başlık çıkar")
    p.add_argument("--film-name", default="", help="Film adı (metadata'dan)")
    p.add_argument("--film-year", default="", help="Film yılı")
    p.add_argument("--fallback", default="Moving Poster", help="Hiçbir şey kalmadıysa kullanılacak varsayılan")
    p.set_defaults(func=cmd_clean_title)

    p = sub.add_parser("clean-caption", help="Temiz caption oluştur (Instagram limitlerine uygun)")
    p.add_argument("--caption", default="", help="Temizlenecek ham caption")
    p.add_argument("--file", default="", help="Dosya adından caption çıkar")
    p.add_argument("--film-name", default="", help="Film adı (metadata'dan)")
    p.add_argument("--film-year", default="", help="Film yılı")
    p.add_argument("--fallback", default="Moving Poster", help="Hiçbir şey kalmadıysa kullanılacak varsayılan")
    p.set_defaults(func=cmd_clean_caption)

    p = sub.add_parser("followers", help="Show follower stats (mock data)")
    p.set_defaults(func=cmd_followers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
