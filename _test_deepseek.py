"""DeepSeek key gercekten calisiyor mu — kucuk bir baslik uret, gercek API response al."""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\.codex\content-ops")

from title_generator import generate_title

# Test 1: poster_loop_cinema
print("Test 1: poster_loop_cinema baslik uretimi")
t0 = time.time()
title = generate_title(
    channel="poster_loop_cinema",
    scene_summary="Bir adam yokus tirmaniyor ve nefes nefese kalmis ama vazgecmiyor",
    film_name="Rocky",
    film_year="1976",
)
elapsed = time.time() - t0
print(f"  Sure: {elapsed:.2f}s")
print(f"  Uzunluk: {len(title)} char")
print(f"  Baslik: {title}")
print(f"  KARAR: {'DeepSeek calisti' if elapsed > 0.5 else 'Fallback kullanildi (DeepSeek calismadi)'}")
print()

# Test 2: sahnebaddiestr
print("Test 2: sahnebaddiestr baslik uretimi")
t0 = time.time()
title = generate_title(
    channel="sahnebaddiestr",
    scene_summary="Ana karakter masaya yumrugunu vurarak butun aileyi karsisina aliyor",
    hook="O an gozlerindeki ifadeyi gormeniz lazim",
)
elapsed = time.time() - t0
print(f"  Sure: {elapsed:.2f}s")
print(f"  Uzunluk: {len(title)} char")
print(f"  Baslik: {title}")
print()

# Test 3: chatkesti
print("Test 3: chatkesti baslik uretimi")
t0 = time.time()
title = generate_title(
    channel="chatkesti",
    scene_summary="Yayinci CSGO oynarken aniden chate donup kacmaya basliyor",
    streamer="Wtcn",
    game="Counter-Strike 2",
)
elapsed = time.time() - t0
print(f"  Sure: {elapsed:.2f}s")
print(f"  Uzunluk: {len(title)} char")
print(f"  Baslik: {title}")
