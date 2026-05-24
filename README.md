# ContentOps

Tek lokal program, uc kanal:

- `poster_loop_cinema`
- `sahnebaddiestr`
- `chatkesti`

Amac: surekli model kotasi yakmadan metadata, caption, handoff ve publish queue uretmek.

## Mantik

Program su sirayla calisir:

1. `cache`: daha once uretilen sonucu kullanir.
2. `ollama`: istersen lokal model dener.
3. `template`: kota yoksa sablonla devam eder.

Claude web sohbetiyle calismak icin:

1. Program Claude'a yapistirilacak prompt dosyasini uretir.
2. Claude JSON doner.
3. O JSON `inbox` icine kaydedilir.
4. Program JSON'u cache'e alir.
5. Sonraki run artik kota harcamadan cache'ten ilerler.

## Komutlar

```powershell
cd C:\Users\User\.codex\content-ops
python content_ops.py list-channels
python content_ops.py run --channel chatkesti --items jobs\sample_chatkesti.json --providers cache,template
python content_ops.py run --channel sahnebaddiestr --items jobs\sample_sahnebaddiestr.json --providers cache,template
python content_ops.py run --channel poster_loop_cinema --items jobs\sample_poster_loop_cinema.json --providers cache,template
```

## Tarayici izolasyonu

Kanal eslesmesi:

- Chrome: `poster_loop_cinema`
- Edge: `sahnebaddiestr`
- Firefox: `chatkesti`

Komutlari gormek:

```powershell
python content_ops.py browser-plan --channel all
```

Uc tarayiciyi ayri profil klasorleriyle acmak:

```powershell
python content_ops.py launch-browsers --channel all
```

Profil klasorleri:

```text
C:\Users\User\.codex\browser-profiles\poster-loop-chrome
C:\Users\User\.codex\browser-profiles\sahnebaddies-edge
C:\Users\User\.codex\browser-profiles\chatkesti-firefox
```

Debug portlari:

```text
Chrome / Poster Loop Cinema: 9222
Edge / SahneBaddiesTR: 9223
Firefox / ChatKesti: profil izole; CDP port kullanmaz
```

Claude handoff:

```powershell
python content_ops.py export-handoff --channel chatkesti --items jobs\sample_chatkesti.json
```

Cikan `.md` dosyasini Claude'a yapistir. Claude'un JSON cevabini mesela:

```text
inbox\chatkesti_claude_response.json
```

icine koy. Sonra:

```powershell
python content_ops.py import-handoff --channel chatkesti --file inbox\chatkesti_claude_response.json
python content_ops.py run --channel chatkesti --items jobs\sample_chatkesti.json --providers cache,template
```

## Lokal model

Ollama varsa:

```powershell
$env:OLLAMA_MODEL="llama3.1"
python content_ops.py run --channel chatkesti --items jobs\sample_chatkesti.json --providers cache,ollama,template
```

Ollama yoksa otomatik template'e duser.

## Job formati

```json
{
  "today": "2026-05-21",
  "mode": "batch",
  "platform": "all",
  "source_rights": "confirmed",
  "batch": "batch-001",
  "items": [
    {
      "id": "item-001",
      "source_path": "C:/path/video.mp4",
      "hook": "Yayin burada koptu."
    }
  ]
}
```

## Cikti

Queue dosyalari:

```text
queues/
```

Cache:

```text
cache/llm_outputs/
```

Son kosular:

```text
state/pipeline_state.json
```

## SMU

SMU, ContentOps'un gunluk operasyon katmanidir.

Hedef:

- Aktif kanallarda gunde 10 video.
- `01:00-07:00` arasinda paylasim yok.
- Sabah hazirlik, gun icinde zamanli yayin.
- Yorum tarafinda otomatik spam degil, manuel yorum taslak kuyrugu.
- ChatKesti simdilik config'te durur ama pasiftir.

Komutlar:

```powershell
cd C:\Users\User\.codex\content-ops
python smu.py morning-runbook --date 2026-05-21
python smu.py plan-day --date 2026-05-21
python smu.py comment-plan --date 2026-05-21
python smu.py status --date 2026-05-21
```

Olusan dosyalar:

```text
schedules\2026-05-21_smu_schedule.json
comments\2026-05-21_comment_drafts.json
runbooks\2026-05-21_morning_runbook.md
```

Kaynak ve otomasyon kurallari:

```text
policies\RIGHTS_AND_AUTOMATION_RULES.md
```
