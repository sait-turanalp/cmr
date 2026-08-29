# CMR — çalışma notları

XLSX → toplu CMR PDF üreten servis. Mimari için `ARCHITECTURE.md` (gerektiğinde oku, her oturumda değil).

## Nerede ne var

- `backend/app.py` — HTTP + PDF hattı, tek dosya. Değişikliklerin çoğu burada.
- `frontend/src/app/components/convertForm.tsx` — üretim akışı, turbo toggle
- `frontend/src/app/components/resultPage.tsx` — sonuç ekranı
- `docker-compose.yml` — tek ve gerçek deploy tanımı
- `deploy/setup-host.sh` — yeni sunucuya taşırken bir kez
- `deploy/cmr-watchdog.sh` — ölü container toparlayıcı + bellek eşiği uyarısı
- `deploy/cmr-commander.py` — telefondaki yeniden başlat/resetle butonlarını dinler
- `deploy/notify.sh` — ntfy bildirimi (buton/etiket/susturma burada)

Sunucu: `root@178.208.187.74`, uygulama `/opt/cmr`, alan adı `yedek.opik.online`.

## Deploy

```
tar czf /tmp/cmr-src.tar.gz --exclude=node_modules --exclude=.next --exclude=venv \
    --exclude=.git --exclude=__pycache__ --exclude='.DS_Store' \
    backend frontend Dockerfile.* docker-compose.yml deploy
scp /tmp/cmr-src.tar.gz root@178.208.187.74:/opt/cmr/
ssh root@178.208.187.74 "cd /opt/cmr && tar xzf cmr-src.tar.gz && find . -name '._*' -delete \
    && docker compose build && docker compose up -d"
```

Rollback: `/opt/cmr/_rollback/` altında container config yedekleri, `cmr-*:rollback-YYYYMMDD` imajları.

## Doğrulama

| Ne | Komut |
|---|---|
| Servisler ayakta | `ssh root@… "docker compose -f /opt/cmr/docker-compose.yml ps"` |
| Site cevap veriyor | `curl -s -o /dev/null -w '%{http_code}' https://yedek.opik.online` |
| Aşama süreleri | `docker logs cmr-backend \| grep TIMING \| tail -3` |
| PDF silinme davranışı | üret → indir → `ls /opt/cmr/backend/outputs` boş olmalı |
| Disk | `df -h /` ve `docker system df` |
| Anlık yük | `curl -s https://yedek.opik.online/api/proxy/active` |
| Zamanlayıcılar | `systemctl list-timers 'cmr-*'` |
| Watchdog günlüğü | `journalctl -t cmr-watchdog --since '1 day ago'` |
| Bildirim testi | `sh /opt/cmr/deploy/notify.sh 'test' 'deneme'` |
| Bellek uyarısı | `rm -f /var/tmp/.cmr-mem-alert; CMR_MEM_THRESHOLD=1 sh …/cmr-watchdog.sh` (sonra damgayı sil) |
| Uzaktan buton | `curl -H 'Cache: no' -d restart "https://ntfy.sh/$NTFY_CMD_TOPIC"` → `journalctl -u cmr-commander` |
| Komut dinleyicisi | `systemctl is-active cmr-commander` |
| Giden bildirimleri oku | `curl -s "https://ntfy.sh/$NTFY_TOPIC/json?poll=1&since=15m"` |
| Eşzamanlılık | `scratchpad/load_test.py all` (1-4 kullanıcı) · `resilience_test.py` (kesme/kapasite) |

Watchdog'u test ederken **timer'ı bekleme** — script'i doğrudan çağır
(`sh /opt/cmr/deploy/cmr-watchdog.sh`); dakikalık timer'ı beklemek her turda
60 sn'ye kadar boşuna bekleme demektir.

Performans referansı: 182 satır turbo ≈ 9-10 sn (render ~7, save ~2.5).
Bunun iki katına çıktıysa altyapı sorunudur, kod değil.

## Foot-gun'lar (hepsi bu projede canımızı yaktı)

**Docker**
- `--env-file` yalnızca container *oluşturulurken* okunur. `docker restart` yeni env'i almaz — `.env` değiştiyse **recreate** şart. `PARALLEL_MIN_ROWS` bir kez sessizce `9999`'da kalıp turbo modu tamamen kapattı.
- Docker daemon restart'ından sonra eski container'lar kirli kalabiliyor: pipeline 11 sn'den 22 sn'ye çıktı, recreate ile düzeldi. Daemon'a dokunduysan container'ları recreate et.
- Frontend imajı `node:alpine` — içinde `python3` **yok**. Healthcheck'i `node -e` ile yaz.
- Karmaşık `--health-cmd` tırnak cehennemi. Script dosyası yazıp `docker cp` ile koymak daha temiz.
- macOS'ta `tar` AppleDouble (`._*`) dosyaları üretir, sunucuya sızar. Açtıktan sonra `find . -name '._*' -delete`.
- **Named volume, PDF çıktısı için bind mount'tan belirgin yavaş.** Aynı iş: named volume'de save 9.8 sn / toplam 21 sn, bind mount'ta save 2.5 sn / toplam 9.9 sn. `outputs` bind mount kalmalı.

**PyMuPDF**
- `save(clean=True)` **kullanma**: 182 sayfada 6.5 sn ve boyut kazancı sıfır. Kaldırınca 3.3 sn, dosya biraz daha küçük.
- `garbage=4` **şart**. 3'e veya 2'ye düşürmek dosyayı 24 MB'dan 127 MB'a çıkarır (tekrarlanan font/logo objeleri tekilleşmiyor).
- Aynı doküman üzerinde ardışık `save()` ölçmek yanıltır — `save` dokümanı yerinde değiştirir, ikinci varyant zaten temizlenmiş belge üzerinde çalışır. Her varyant için baştan render et.

**Eşzamanlılık**
- Pay iş başlarken sabitlenirse son gelen 1 işçide kilitli kalır — ölçüldü: 4 kullanıcıda en yavaş/en hızlı farkı 1.94x. Çözüm, payı her 40 satırda yeniden hesaplamak (1.28x'e indi).
- Aktif iş sayacı sızarsa herkese hak ettiğinden az işçi düşer. `active_count()` orphan kayıtları (hash'i kaybolmuş ZSET girdileri) ayıklar — SIGKILL sonrası bile sayaç doğru.

**Paralellik**
- 4 çekirdekte `PARALLEL_WORKERS=3` optimum. 4 yapınca ana süreçteki birleştirme işi (`insert_pdf`) çekirdek için yarışıyor, %7 yavaşlıyor.
- Küçük dosyalarda havuz açmak zararlı — fork maliyeti render'dan uzun. Eşik `PARALLEL_MIN_ROWS=40`.

**Kimlik doğrulama**
- `middleware.ts`'te korumalı API'ye çerezsiz gelince **401 JSON** dönmeli, yönlendirme değil — istemci JSON bekliyor, HTML gelirse parse hatası alır.
- Kötü tarayıcı ajanı filtresi yalnızca **oturumsuz** isteklerde çalışır (`!token && isBlockedRequest`). Oturumlu test yaparsan engellenmediğini görürsün, bu normaldir.
- Tarayıcıda `fetch()` varsayılan `credentials: 'same-origin'` — çerez otomatik gider, `<a href download>` de öyle. Koruma eklerken istemciye dokunmak gerekmedi.

**Dayanıklılık**
- Docker'ın `restart: always` politikası, container API'den durdurulmuşsa (`docker stop`/`kill`, başarısız `docker restart`) **devreye girmez** — `RestartCount` 0'da kalır. 17 saatlik kesintinin mekanizması buydu. `cmr-watchdog.timer` bu boşluğu kapatır (ölçüldü: 33 sn).
- Kaos testinde `docker kill` kullanma — o manuel müdahale sayılır ve gerçek çökmeyi temsil etmez. Gerçek çökme testi: `docker exec <c> pkill -9 -f <süreç>`.
- Frontend'de Node süreci `server.js` değil **`next-server`** adıyla görünür; `pkill -f server.js` hiçbir şey yakalamaz.

**Next.js**
- `localStorage`'ı `useState` başlangıç değerinde okumak hydration mismatch yaratır (sunucu `false`, istemci `true` üretir; React stil'i düzeltmez, öğe yanlış renkte kalır). `useEffect` içinde oku.
- `NEXT_PUBLIC_*` istemci paketine gömülür. Sır koyma.

**Ölçüm**
- Backend `mode=normal`'da satır başına 0.55 sn **kasıtlı** bekler (turbo'yu pazarlanabilir kılmak için). Yavaşlık sanma.
- Lokal M2, sunucudan ~6 kat hızlı. 182 sayfa lokalde 1.6 sn, sunucuda ~9.5 sn. Karşılaştırırken aynı makineyi kullan.

## Disk hijyeni

Zamanlayıcıya bağımlılık yok:
- Build cache → `daemon.json` içindeki `builder.gc`, 2 GB tavan (Docker kendi temizler)
- Container log → `log-opts` + `/etc/logrotate.d/docker-containers`
- Üretilen PDF → indirilince silinir; artığı `cleanup_pdfs` süpürür
- İmaj birikimi → deploy sonrası `docker image prune -f` (eski build katmanları)

Bir kez 40 GB'a çıkmıştı (24.99 GB build cache). `deploy/setup-host.sh` bunu kalıcı olarak engeller.

## Kalan işler

- Giriş sabit kodlanmış (`admin`/`1234`), `users` tablosu kullanılmıyor
- Hız sınırlama yok (oturum zorunlu olduğu için istismar yüzeyi dar)
- `.env` git'te takipli — anahtarlar geçmişte duruyor

### Foot-gun: watchdog ve elle yeniden başlatma aynı anda çalışırsa stack bozulur

`docker compose up -d --force-recreate` sırasında container'lar geçici olarak
`created`/`missing` görünür. Kilit yoksa `cmr-watchdog` bunu çökme sanıp **ikinci
bir `compose up`** başlatır; iki compose yarışır ve stack bozulur — ölçüldü:
`cmr-backend` tamamen kayboldu ve sahte bir "toparlanamadı" acil bildirimi gitti.

Çözüm: her ikisi de `/var/lock/cmr-ops.lock` üzerinde `flock` alır.
`cmr-watchdog.sh` kilidi alamazsa **o turu sessizce atlar** (`flock -n 9 || exit 0`);
`cmr-commander.py` yeniden başlatma boyunca kilidi tutar.

**Kural:** `compose` çağıran yeni bir otomasyon eklersen bu kilidi almadan ekleme.
