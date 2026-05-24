import json, datetime
try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo('Europe/Istanbul')
    now = datetime.datetime.now(tz=tz)
except Exception:
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

fmt = "%H:%M:%S"
print("Now (Istanbul):", now.strftime(fmt))
print()

data = json.loads(open(r'C:\Users\User\.codex\content-ops\schedules\2026-05-21_smu_schedule.json', encoding='utf-8').read())
print("AKSAM SLOTLARI (file var, 22:00+):")
header = "%-20s %-5s %-17s %-12s %s" % ("Channel", "Slot", "Time", "Status", "File")
print(header)
print("-" * 90)
for s in data['slots']:
    t = s.get('publishAtLocal','')
    if t >= '2026-05-21 22:00' and s.get('file'):
        ch = s['channel'][:18]
        status = s.get('status','')[:10]
        fname = s.get('file','').split('/')[-1][:35]
        print("%-20s %-5d %-17s %-12s %s" % (ch, s['slot'], t, status, fname))
