#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SMU Downloader — yt-dlp based source video downloader.

Her kanal için kaynak sayfalarda yeni video arar, belirtilen limitte indirir,
.json sidecar oluşturur ve sourceBucket'a kaydeder.

Kullanım:
  python downloader.py run --channel poster_loop_cinema --limit 10
  python downloader.py run --channel sahnebaddiestr --limit 10
  python downloader.py run --channel all --limit 10
  python downloader.py list-sources --channel poster_loop_cinema
  python downloader.py check  # yt-dlp kurulu mu?
"""

from __future__ import annotations

import io
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "smu_config.json"
SOURCES_DIR = ROOT / "sources"
AUDIT_FREEZE_FILE = ROOT / "state" / "audit_freeze.json"
MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


# ── yardımcı ────────────────────────────────────────────────────────────────

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


def audit_freeze_active() -> bool:
    return AUDIT_FREEZE_FILE.exists()


def audit_freeze_reason() -> str:
    if not AUDIT_FREEZE_FILE.exists():
        return ""
    try:
        data = read_json(AUDIT_FREEZE_FILE)
        return str(data.get("reason") or data.get("note") or "audit freeze active")
    except Exception:
        return "audit freeze active"


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def ytdlp_path() -> str:
    """yt-dlp PATH'ini bul."""
    for candidate in ["yt-dlp", "yt-dlp.exe", str(Path.home() / ".local/bin/yt-dlp")]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, OSError):
            continue
    return ""


def ensure_ytdlp() -> str:
    path = ytdlp_path()
    if path:
        return path
    print("yt-dlp bulunamadı. Kurmak için: pip install yt-dlp", file=sys.stderr)
    raise SystemExit(1)


def load_sources(channel_id: str) -> list[dict[str, Any]]:
    """channels/{channel_id}_sources.json dosyasını oku."""
    path = SOURCES_DIR / f"{channel_id}_sources.json"
    if not path.exists():
        return []
    data = read_json(path)
    if isinstance(data, list):
        return data
    return data.get("sources", [])


def already_downloaded(bucket: Path) -> set[str]:
    """sourceBucket'ta olan dosyaların stem kümesini döndür."""
    if not bucket.exists():
        return set()
    return {
        f.stem
        for f in bucket.iterdir()
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS
    }


def build_ydl_args(
    ytdlp: str,
    source: dict[str, Any],
    out_dir: Path,
    limit: int,
) -> list[str]:
    """Kaynak tipine göre yt-dlp argümanları oluştur."""
    url = source.get("url", "")
    max_items = int(source.get("maxItems", limit))
    is_search = url.startswith("ytsearch")

    args = [
        ytdlp,
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4",
        "--match-filter", "duration < 180 & duration > 5",
        "--output", str(out_dir / "%(id)s.%(ext)s"),
        "--write-info-json",
        "--no-write-thumbnail",
        "--no-progress",
        "--quiet",
        "--no-warnings",
        "--ignore-errors",
        "--restrict-filenames",
    ]

    if is_search:
        # ytsearch: formatında playlist-end değil, URL'de sayı var (ytsearch8:query)
        # Zaten URL'de kaç sonuç alacağı belirtilmiş
        pass
    elif source.get("noPlaylist"):
        args.append("--no-playlist")
    else:
        args += ["--playlist-end", str(max_items)]

    # Çerez desteği
    cookies_from = source.get("cookiesFrom", "")
    if cookies_from:
        args += ["--cookies-from-browser", cookies_from]

    cookies_file = source.get("cookiesFile", "")
    if cookies_file and Path(cookies_file).exists():
        args += ["--cookies", cookies_file]

    args.append(url)
    return args


def write_sidecar(
    channel_id: str,
    source: dict[str, Any],
    video_meta: dict[str, Any],
    video_path: Path,
    rights: str,
) -> Path:
    """Video için .json sidecar oluştur."""
    title = video_meta.get("title", video_path.stem)
    uploader = video_meta.get("uploader", "") or video_meta.get("channel", "")
    webpage_url = video_meta.get("webpage_url", "") or video_meta.get("url", "")
    duration = video_meta.get("duration", 0)
    upload_date = video_meta.get("upload_date", "")

    sidecar: dict[str, Any] = {
        "id": slugify(video_path.stem),
        "source_path": str(video_path),
        "source_rights": rights,
        "source_link": webpage_url,
        "downloaded_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_page": source.get("url", ""),
        "source_label": source.get("label", ""),
        "raw_title": title,
        "uploader": uploader,
        "duration_seconds": duration,
        "upload_date": upload_date,
    }

    if channel_id == "poster_loop_cinema":
        # film ipuçlarını çıkar
        sidecar["film_hint"] = source.get("filmHint") or _extract_film_hint(title)
        sidecar["year_hint"] = source.get("yearHint", "")
        sidecar["director_hint"] = source.get("directorHint", "")
        sidecar["scene_hint"] = source.get("sceneHint", "")
        sidecar["summary_hint"] = video_meta.get("description", "")[:400]

    elif channel_id == "sahnebaddiestr":
        sidecar["person_hint"] = source.get("personHint") or _extract_person_hint(title)
        sidecar["program_hint"] = source.get("programHint", "")
        sidecar["hook"] = "Bu sahnenin enerjisi ayrı."
        sidecar["question"] = "Sence bu anın aurası kaç/10?"

    elif channel_id == "chatkesti":
        sidecar["streamer"] = source.get("streamer") or uploader
        sidecar["platform"] = source.get("platform", "")
        sidecar["game"] = source.get("game", "")
        sidecar["hook"] = "Yayın burada koptu."
        sidecar["question"] = "Bir sonraki hangi yayıncı gelsin?"

    sidecar_path = video_path.with_suffix(".json")
    write_json(sidecar_path, sidecar)
    return sidecar_path


def _extract_film_hint(title: str) -> str:
    # "Film Name (2023)" → "Film Name"
    match = re.match(r"^(.+?)\s*[\(\[]\d{4}[\)\]]", title)
    if match:
        return match.group(1).strip()
    return title.split("|")[0].split("-")[0].strip()


def _extract_person_hint(title: str) -> str:
    # "Ad Soyad | Program" → "Ad Soyad"
    return title.split("|")[0].split("-")[0].strip()


def download_channel(
    channel_id: str,
    channel_cfg: dict[str, Any],
    limit: int,
    rights: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    ytdlp = ensure_ytdlp()
    bucket = Path(channel_cfg.get("sourceBucket", ""))
    bucket.mkdir(parents=True, exist_ok=True)

    sources = load_sources(channel_id)
    if not sources:
        return {"channel": channel_id, "status": "no_sources", "downloaded": 0}

    already = already_downloaded(bucket)
    downloaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    remaining = limit

    for source in sources:
        if remaining <= 0:
            break
        if not source.get("active", True):
            continue

        src_limit = min(remaining, int(source.get("maxItems", limit)))
        args = build_ydl_args(ytdlp, source, bucket, src_limit)

        if dry_run:
            print(f"[dry-run] {channel_id}/{source.get('label','')} → {' '.join(args[:5])}…")
            continue

        print(f"→ {channel_id}: {source.get('label', source.get('url', '')[:60])}")
        result = subprocess.run(args, capture_output=True, text=True, timeout=600)

        if result.returncode not in (0, 1):  # 1 = bazı video atlandı, normal
            err_msg = f"{source.get('label', '')}: exit {result.returncode}"
            errors.append(err_msg)
            # Takıldık — AI yardım kuyruğuna ekle
            try:
                from needs_help import add_task  # noqa: PLC0415
                add_task(
                    category="download",
                    title=f"İndirme başarısız: {source.get('label', url[:40])}",
                    detail=f"Hata: {result.stderr[-300:] if result.stderr else err_msg}",
                    channel=channel_id,
                    priority="high",
                    context={"url": source.get("url"), "exit_code": result.returncode},
                )
            except Exception:
                pass

        # yt-dlp'nin indirdiği dosyaları bul
        for video_file in sorted(bucket.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if video_file.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            if video_file.stem in already:
                skipped.append(video_file.stem)
                continue
            if video_file.stem in downloaded:
                continue

            # .info.json sidecar'ı oku
            info_json = bucket / f"{video_file.stem}.info.json"
            meta: dict[str, Any] = {}
            if info_json.exists():
                try:
                    meta = read_json(info_json)
                except Exception:
                    pass

            write_sidecar(channel_id, source, meta, video_file, rights)
            downloaded.append(video_file.stem)
            already.add(video_file.stem)
            remaining -= 1

            if remaining <= 0:
                break

    return {
        "channel": channel_id,
        "bucket": str(bucket),
        "downloaded": len(downloaded),
        "skipped_existing": len(skipped),
        "errors": errors,
        "items": downloaded,
    }


# ── alt komutlar ─────────────────────────────────────────────────────────────

def cmd_check(args: argparse.Namespace) -> None:
    path = ytdlp_path()
    if path:
        result = subprocess.run([path, "--version"], capture_output=True, text=True)
        print(f"yt-dlp: {path}  version: {result.stdout.strip()}")
    else:
        print("yt-dlp bulunamadı. Kurmak için: pip install yt-dlp")
        raise SystemExit(1)


def cmd_list_sources(args: argparse.Namespace) -> None:
    sources = load_sources(args.channel)
    if not sources:
        print(f"Kaynak yok: sources/{args.channel}_sources.json")
        return
    for source in sources:
        active = "[OK]" if source.get("active", True) else "[--]"
        print(f"  {active} [{source.get('label', '')}] {source.get('url', '')}")


def cmd_run(args: argparse.Namespace) -> None:
    override = os.environ.get("SMU_ALLOW_AUDIT_DOWNLOAD") == "1"
    if audit_freeze_active() and not args.dry_run and not override:
        print(
            f"[blocked] audit freeze active; downloader run skipped: {audit_freeze_reason()}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    config = read_json(CONFIG_FILE)
    channels = config["channels"]
    rights = "confirmed" if args.assume_confirmed else "unknown"

    targets = list(channels.keys()) if args.channel == "all" else [args.channel]

    for channel_id in targets:
        ch = channels.get(channel_id)
        if not ch:
            print(f"Bilinmeyen kanal: {channel_id}", file=sys.stderr)
            continue
        if not ch.get("active") and not args.include_disabled:
            print(f"[skip] {channel_id} devre dışı")
            continue
        result = download_channel(channel_id, ch, args.limit, rights, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False))


def cmd_create_sources(args: argparse.Namespace) -> None:
    """Örnek sources dosyası oluştur."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    templates: dict[str, list[dict[str, Any]]] = {
        "poster_loop_cinema": [
            {
                "label": "filmmax-clips",
                "url": "https://www.youtube.com/@FilmMax/videos",
                "active": True,
                "maxItems": 15,
                "filmHint": "",
                "yearHint": "",
                "directorHint": "",
                "sceneHint": "opening scene",
                "cookiesFrom": "",
                "noPlaylist": False,
            },
            {
                "label": "cult-cinema-channel",
                "url": "https://www.youtube.com/@CHANNEL/shorts",
                "active": False,
                "maxItems": 10,
                "filmHint": "",
                "yearHint": "",
            },
        ],
        "sahnebaddiestr": [
            {
                "label": "magazin-clips",
                "url": "https://www.youtube.com/@CHANNEL/videos",
                "active": True,
                "maxItems": 15,
                "personHint": "",
                "programHint": "",
                "cookiesFrom": "",
                "noPlaylist": False,
            },
            {
                "label": "tv-show-clips",
                "url": "https://www.youtube.com/@CHANNEL/shorts",
                "active": False,
                "maxItems": 10,
                "personHint": "",
                "programHint": "",
            },
        ],
        "chatkesti": [
            {
                "label": "elraenn",
                "url": "https://www.twitch.tv/elraenn/clips?filter=top&range=30d",
                "active": True,
                "maxItems": 5,
                "streamer": "Elraenn",
                "platform": "twitch",
                "game": "",
                "cookiesFrom": "",
            },
            {
                "label": "kendine-muzisyen",
                "url": "https://www.youtube.com/@KendineMuzisyen/shorts",
                "active": True,
                "maxItems": 5,
                "streamer": "Kendine Müzisyen",
                "platform": "kick",
                "game": "",
            },
        ],
    }

    channels = [args.channel] if args.channel != "all" else list(templates.keys())
    for ch_id in channels:
        if ch_id not in templates:
            print(f"Template yok: {ch_id}")
            continue
        path = SOURCES_DIR / f"{ch_id}_sources.json"
        if path.exists() and not args.force:
            print(f"Var zaten: {path}  (--force ile üzerine yaz)")
            continue
        write_json(path, {"channel": ch_id, "sources": templates[ch_id]})
        print(f"Oluşturuldu: {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMU Downloader")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="yt-dlp kurulu mu kontrol et")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("list-sources", help="Kanal kaynaklarını listele")
    p.add_argument("--channel", required=True)
    p.set_defaults(func=cmd_list_sources)

    p = sub.add_parser("create-sources", help="Örnek sources dosyası oluştur")
    p.add_argument("--channel", default="all")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_create_sources)

    p = sub.add_parser("run", help="İçerik indir")
    p.add_argument("--channel", default="all", help="Kanal ID veya 'all'")
    p.add_argument("--limit", type=int, default=12, help="Kanal başına max video")
    p.add_argument("--assume-confirmed", action="store_true")
    p.add_argument("--include-disabled", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Gerçekten indirme, komutları göster")
    p.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
