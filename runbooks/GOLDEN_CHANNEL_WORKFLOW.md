# Golden Channel Workflow

Bu dosya SMU icin ana gercektir. Yeni Claude/Codex session'i baslarken once bunu oku.

SMU'nun amaci sifirdan rastgele icerik uretmek degil; mevcut kanallarin kanitlanmis yayin hattini guvenli sekilde devralmaktir. Yanlis queue, yanlis template veya default worker kullanimi tekrar eden/bozuk gonderi uretir.

## Kanal Duzeni

### Poster Loop Cinema

Dogru gorsel duzen:

- Beyaz poster sayfasi.
- Ust solda kucuk renk paleti.
- Ust sagda film yili.
- Ust orta/sag bolgede okunur yonetmen/senaryo/oyuncu kredileri.
- Buyuk film basligi.
- Orta-alt bolgede film sahnesi hareketli video cercevesi.
- Alt bolgede kucuk `POSTER LOOP CINEMA` imzasi.
- Tum sayfa beyaz kalir; gri placeholder, numara etiketi, `01` benzeri seri etiketi yoktur.
- Turkce karakterler bozulmayacak: `ç, ğ, ı, İ, ö, ş, ü` korunur.

Dogru teknik hat:

1. Kaynak video secilir.
2. Film kimligi kesinlestirilir: film adi, yil, yonetmen, oyuncular.
3. Poster PNG/template dogru metadata ile uretilir.
4. Video posterin sahne alanina gomulur.
5. Export MP4 uretilir.
6. Sadece bu export MP4 yayinlanir.

Kesinlikle yapma:

- Ham film klibini PosterLoop'a oldugu gibi yukleme.
- Eski `posterloop_queue_first20.json`, eski 21-50 queue veya daha once yayinlanmis batch'i tekrar kullanma.
- Worker'i queue/state/log path vermeden calistirma.
- Bir batch bittikten sonra ayni state'i yeni batch'e tasima.

### SahneBaddiesTR

Dogru gorsel duzen:

- Dikey tam ekran video.
- Poster/template yok.
- Beyaz poster cercevesi yok.
- Film metadata basligi/kredi blogu yok.
- Kaynak goruntu temiz dikey crop ile akar.
- Marka/logotype altta kucuk ve tutarli gorunur.

Dogru teknik hat:

1. Kaynak video secilir.
2. Filigran veya kaynak riski varsa video atlanir.
3. Baddies render hatti sadece crop/logo/renk-temizlik uygular.
4. Export MP4 uretilir.
5. Sadece bu export MP4 yayinlanir.

Kesinlikle yapma:

- Baddies videosuna PosterLoop poster sablonu uygulama.
- Baddies'i film metadata sistemiyle calistirma.
- Ozel hayat iddiasi, beden yorumu, asagilama, yas/mahremiyet imasi yazma.

## Yayin Guvenligi

Her yayin isi tek item olarak calismali.

Zorunlu kural:

- Schedule slotu geldiyse worker'a tek itemlik gecici queue ver.
- Her slot icin ayri state dosyasi kullan.
- Her slot icin ayri log dosyasi kullan.
- Worker default queue'ya dusmemeli.

PosterLoop env zorunlu:

```powershell
POSTERLOOP_QUEUE_PATH=<tek item queue>
POSTERLOOP_STATE_PATH=<tek slot state>
POSTERLOOP_LOG_PATH=<tek slot log>
POSTERLOOP_DEBUG_ENDPOINT=http://127.0.0.1:9222
```

Baddies env zorunlu:

```powershell
BADDIES_QUEUE_PATH=<tek item queue>
BADDIES_STATE_PATH=<tek slot state>
BADDIES_LOG_PATH=<tek slot log>
BADDIES_DEBUG_ENDPOINT=http://127.0.0.1:9223
```

## Tarayici Haritasi

- Poster Loop Cinema: Chrome, CDP port `9222`.
- SahneBaddiesTR: Edge, CDP port `9223`.
- ChatKesti: pasif.

Yayin/silme/yukleme oncesi port kontrolu yap:

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
Invoke-RestMethod http://127.0.0.1:9223/json/version
```

Port kapaliysa yayin otomasyonu baslatma; once browser'i ac.

## Schedule Kurali

- Eski schedule dosyasi dogrudan guvenilir degildir.
- `status=scheduled` ama queueItem daha once yayinlanmis batch'ten geliyorsa slotu `blocked_legacy_smu_review` yap.
- `needs_queue_item` olan kanali otomatik doldurma; once kanal pipeline'i dogru export uretmis mi kontrol et.
- Past slotlari "sonraki event" sayma.

## Hak ve Buyume Kurallari

- Sadece hak durumu onayli kaynaklari yayinla.
- Gorunur filigranli videoyu alma; filigrani kapatacak crop/ortme yapma.
- Yorum/takip spam otomasyonu yapma.
- Yorum tarafinda sadece manuel, alakali ve sinirli taslak hazirla.

## Claude/Codex Devralma Promptu

```text
C:\Users\User\.codex\content-ops\AI_INSTRUCTIONS.md dosyasini oku.
Ardindan C:\Users\User\.codex\content-ops\runbooks\GOLDEN_CHANNEL_WORKFLOW.md dosyasini oku.
Sonra:
1. python needs_help.py list
2. python smu_daemon.py status
3. schedules klasorundeki bugunku schedule'i kontrol et.
4. Chrome 9222 ve Edge 9223 portlarini kontrol et.

Onemli:
- PosterLoop sadece beyaz poster/moving-poster exportlarini yayinlar.
- Baddies sadece dikey full-screen crop/logo exportlarini yayinlar.
- Worker'i asla default queue ile calistirma.
- Her schedule slotu icin tek item queue + ayri state + ayri log kullan.
- Eski batch veya daha once yayinlanmis queue gorursen yayinlama, blocked_legacy_smu_review yap.
- Spam yorum/takip otomasyonu yapma.

Once sistemi guvenli moda al, sonra hangi slotlarin gercekten yayina hazir oldugunu raporla.
```
