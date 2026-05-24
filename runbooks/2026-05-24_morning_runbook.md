# SMU Morning Runbook - 2026-05-24

Timezone: `Europe/Istanbul`
No-post window: `01:00` - `07:00`
Cadence: hourly fixed minutes `05, 25, 40`

## Rules

- Only rights-confirmed sources enter the publish queue.
- Do not remove, hide, or crop out watermarks to disguise source ownership.
- Comments are manual drafts, not spam automation.
- ChatKesti stays disabled until its separate workflow is finalized.

## Browser Map

- Chrome: Poster Loop Cinema
- Edge: SahneBaddiesTR
- Firefox: ChatKesti

## Start

```powershell
cd C:\Users\User\.codex\content-ops
python content_ops.py launch-browsers --channel all
python smu.py plan-day --date 2026-05-24
python smu.py comment-plan --date 2026-05-24
```

## Channel Targets

### poster_loop_cinema

- Browser: `Chrome`
- Daily videos: `30`
- Comment drafts: `10`
- Source bucket: `C:/Users/User/.codex/analog-neo-moving-poster/source-videos`
- Ready buckets: `C:/Users/User/.codex/analog-neo-moving-poster/exports-with-video`
- Notes: Film clips only.

### sahnebaddiestr

- Browser: `Edge`
- Daily videos: `30`
- Comment drafts: `10`
- Source bucket: `C:/Users/User/.codex/sahne-baddies-auto/source-videos`
- Ready buckets: `C:/Users/User/.codex/sahne-baddies-auto/exports`
- Notes: Celebrity clips only.

### chatkesti

- Browser: `Firefox`
- Daily videos: `30`
- Comment drafts: `10`
- Source bucket: `C:/Users/User/.codex/yayinci-kesitleri-auto/source-clips`
- Ready buckets: `C:/Users/User/.codex/yayinci-kesitleri-auto/exports`
- Notes: Stream clips.

