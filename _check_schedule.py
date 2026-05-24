import json
d = json.load(open('schedules/2026-05-24_smu_schedule.json', encoding='utf-8-sig'))
print(f"Toplam slot: {len(d['slots'])}")
print(f"Regenerated at: {d.get('regenerated_at','N/A')}")
print(f"Stats: {json.dumps(d.get('regeneration_stats',{}), indent=2)}")
from collections import Counter
titles = [s.get('youtubeTitle','') for s in d['slots']]
unique = len(Counter(titles))
print(f"Unique titles: {unique}/{len(d['slots'])}")
descs = [s.get('youtubeDescription','') for s in d['slots']]
avg_desc = sum(len(d) for d in descs)/len(descs) if descs else 0
print(f"Avg desc length: {avg_desc:.0f}")
