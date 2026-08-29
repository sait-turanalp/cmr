# `/ext` — sunucudan sunucuya entegrasyon kapısı

Dış sistemlerin (iç yönetim paneli gibi) CMR motorunu doğrudan çağırması için.
Tarayıcı arayüzü ve `yedek.opik.online` bundan etkilenmez.

## Neden ayrı bir kapı

Mevcut `/api/proxy/*` yolları **NextAuth çerezi** ister. Sunucudan sunucuya
konuşan bir istemci çerez taşıyamaz, bu yüzden kendi yolu var.

Kapı **kendi token'ını** doğrular ve backend'e giderken `API_KEY`'i Caddy'nin
kendisi ekler. İki sonucu var:

- Dış taraf `API_KEY`'i **hiç görmez** — anahtar sunucudan çıkmaz.
- `EXT_TOKEN` silinince **yalnız o entegrasyon durur**, site etkilenmez.

Token'ı kapıda zorunlu tutmak şarttı: backend'de `/api/download/<dosya>`,
`/api/active` ve `/health` bilerek auth'suzdur ve bugüne kadar yalnızca dışarı
kapalı oldukları için güvendeydiler. Düz bir `reverse_proxy` onları internete
açardı — özellikle indirme ucunu.

## Kimlik doğrulama

Her istekte:

```
Authorization: Bearer <EXT_TOKEN>
```

Eksik, bozuk ya da yanlış token → **401** (istek backend'e hiç ulaşmaz).

## Uçlar

Taban adres: `https://yedek.opik.online/ext`

| Uç | Metot | Ne yapar |
|---|---|---|
| `/process-pdf` | POST | PDF üretir, senkron döner |
| `/api/progress` | GET | `?job_id=…` — üretim sırasında ilerleme |
| `/api/isfree` | GET | `{"is_processing": bool}` |
| `/api/active` | GET | Anlık yük ve kapasite |
| `/api/download/<dosya>` | GET | PDF'i indirir — **tek kullanımlık** |

### `POST /process-pdf`

```json
{ "data": [ { "CMR NO:": "122", "DATE:": "19.12.2024", "...": "..." } ],
  "currency": "$",
  "mode": "turbo" }
```

`data` — satır dizisi. Anahtarlar Excel başlıklarıdır; tanınmayan anahtar
sessizce atlanır. Eşleme `backend/app.py` içindeki `key_map`'tedir.
`mode` — `"turbo"` (paralel) ya da `"normal"` (kasıtlı yavaş). Varsayılan normal.

Yanıt:

```json
{ "filename": "out_<ad>_<8hex>.pdf", "download_url": "...", "job_id": "...",
  "pages": 5, "size_mb": 0.96, "processing_time_sec": 0.5,
  "workers_used": 3, "rebalanced": 0, "timings": { } }
```

### `GET /api/download/<dosya>`

Dosya adı `out_<ad>_<8hex>.pdf` kalıbına uymalı, aksi hâlde 400.
**İndirme tamamlanınca dosya diskten silinir** — ikinci istek 404 döner.
İndirilmeyen dosyalar `PDF_MAX_AGE_HOURS` (varsayılan 1 saat) sonra süpürülür.

## Hata kodları

| Kod | Anlamı |
|---|---|
| 401 | Token yok/yanlış (kapıdan döner) |
| 400 | Boş dizi, dizi olmayan gövde, geçersiz dosya adı |
| 413 | `MAX_ROWS_PER_REQUEST` (2000) aşıldı |
| 503 | `MAX_CONCURRENT_JOBS` (8) dolu — sonra tekrar dene |
| 404 | Dosya yok ya da zaten indirilmiş |

## Tavanlar

Ayrı bir hız sınırı **yok**; iki tavan zaten koruyor: tek istekte 2000 satır,
aynı anda 8 iş. Beklenen yük (birkaç kişilik ekip) bunun çok altında.

Eşzamanlı işler çekirdek bütçesini paylaşır — kimse kuyrukta beklemez, herkesin
payı küçülür. 8 iş dolu ise yeni istek 503 alır.

## Token yönetimi

Token `/opt/cmr/.env` içinde `EXT_TOKEN` olarak durur. Repoya **girmez**.

```sh
# Okumak
ssh root@<sunucu> 'grep ^EXT_TOKEN= /opt/cmr/.env | cut -d= -f2-'

# Yenilemek / iptal etmek
ssh root@<sunucu> 'cd /opt/cmr \
  && sed -i "s/^EXT_TOKEN=.*/EXT_TOKEN=cmrext_$(head -c24 /dev/urandom | od -An -tx1 | tr -d " \n")/" .env \
  && flock /var/lock/cmr-ops.lock docker compose up -d caddy'
```

İki foot-gun:

- **`docker restart cmr-caddy` yeterli DEĞİL.** Ortam değişkeni yalnızca
  container oluşturulurken okunur; `docker compose up -d caddy` gerekir.
- **`compose`'a dokunan her şey `flock /var/lock/cmr-ops.lock` almalı.**
  Watchdog aynı anda devreye girerse iki `compose` yarışır ve stack bozulur
  (ölçüldü: `cmr-backend` tamamen kaybolmuştu).

## Doğrulama

```sh
T=$(ssh root@<sunucu> 'grep ^EXT_TOKEN= /opt/cmr/.env | cut -d= -f2-')
B=https://yedek.opik.online/ext
curl -s -o /dev/null -w '%{http_code}\n' $B/api/isfree                        # 401
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $T" $B/api/isfree   # 200
```

## Ölçülmüş davranış

27 testlik takım koşuldu (kapı · sızıntı/traversal · sınırlar · uçtan uca ·
eşzamanlılık · regresyon · gecikme), **27/27**.

| Ölçüm | Sonuç |
|---|---|
| Kapı gecikmesi | `/ext` **20 ms** · `/api/proxy` 35 ms (Next.js atlandığı için daha hızlı) |
| 5 satır turbo, uçtan uca | 0.5 sn |
| 3 eşzamanlı iş | 3× 200, hata yok |
| Backend doğrudan (`:5001`) | Bağlantı reddedildi — dışarı kapalı |
| Mevcut site ve oturum akışı | Değişmedi (`/api/proxy/*` aynen) |
