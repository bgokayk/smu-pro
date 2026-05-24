"""3 ornek slot uzerinde generator testi."""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\.codex\content-ops")

from title_generator import generate_title
from description_generator import (
    generate_youtube_description,
    generate_instagram_caption,
    generate_tiktok_caption,
)

# Her kanaldan 1 ornek
TEST_CASES = [
    {
        "channel": "poster_loop_cinema",
        "scene_summary": "Bir adam imkansiz dediler ama ilk denemede sattigi bir ev sahnesi",
        "film_name": "The Pursuit of Happyness",
        "film_year": "2006",
    },
    {
        "channel": "sahnebaddiestr",
        "scene_summary": "Ana karakter butun aileyi karsisina aliyor, kararli bir bakisla",
        "film_name": "",
        "film_year": "",
    },
    {
        "channel": "chatkesti",
        "scene_summary": "Yayinci oyun oynarken aniden ekrana donup chatten yardim istiyor",
        "streamer": "Bilinmeyen yayinci",
        "game": "FPS oyunu",
    },
]

for i, tc in enumerate(TEST_CASES):
    print(f"\n{'='*60}")
    print(f"TEST {i+1}: {tc['channel']}")
    print(f"{'='*60}")
    print(f"Sahne: {tc['scene_summary']}")

    t0 = time.time()
    title = generate_title(**tc)
    t1 = time.time() - t0
    print(f"\nBaslik ({len(title)} char, {t1:.1f}s):")
    print(f"  {title}")

    t0 = time.time()
    yt_desc = generate_youtube_description(title=title, **tc)
    t1 = time.time() - t0
    print(f"\nYT Aciklama ({len(yt_desc)} char, {t1:.1f}s, hedef 800+):")
    print(f"  {yt_desc[:200]}...")

    t0 = time.time()
    ig = generate_instagram_caption(title=title, **tc)
    t1 = time.time() - t0
    print(f"\nIG Caption ({len(ig)} char, {t1:.1f}s, hedef 500+):")
    print(f"  {ig[:200]}...")

    t0 = time.time()
    tt = generate_tiktok_caption(title=title, **tc)
    t1 = time.time() - t0
    print(f"\nTT Caption ({len(tt)} char, {t1:.1f}s, hedef 150-200):")
    print(f"  {tt}")
