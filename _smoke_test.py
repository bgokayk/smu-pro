import urllib.request
import json
import re


def call(path):
    try:
        r = urllib.request.urlopen(f"http://localhost:5000{path}", timeout=10)
        return r.status, json.loads(r.read())
    except Exception as e:
        return "HATA", str(e)


# /
try:
    r = urllib.request.urlopen("http://localhost:5000/", timeout=10)
    html = r.read().decode("utf-8")
    m = re.search(r"const scheduleData = (\{.*?\});", html, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        print(f"[/]            slots={len(data.get('slots', []))} past={len(data.get('past_slots', []))}")
    else:
        print("[/]            schedule_json HTML icinde bulunamadi")
except Exception as e:
    print(f"[/]            HATA: {e}")

st, d = call("/api/data")
print(f"[/api/data]    status={st} slots={len(d.get('slots', []))} past={len(d.get('past_slots', []))} total={d.get('total')}")

st, d = call("/api/followers")
print(f"[/api/followers] status={st} payload={d}")

st, d = call("/api/comments")
keys = list(d.keys())[:5] if isinstance(d, dict) else str(d)[:80]
print(f"[/api/comments] status={st} top_keys={keys}")

st, d = call("/api/logs")
if isinstance(d, dict):
    print(f"[/api/logs]    status={st} satir={d.get('total')}")
else:
    print(f"[/api/logs]    {st} {d}")

st, d = call("/api/data")
if isinstance(d, dict) and d.get("slots"):
    s = d["slots"][0]
    print(f"Ilk slot: publishAtLocal={s.get('publishAtLocal')} status={s.get('status')} channel={s.get('channel')} title={(s.get('youtubeTitle') or '')[:40]}")
