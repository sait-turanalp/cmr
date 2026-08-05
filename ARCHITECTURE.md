# CMR — Mimari

XLSX listesinden toplu CMR (uluslararası taşıma irsaliyesi) PDF'i üreten tek amaçlı servis.
Kullanıcı Excel yükler, her satır bir PDF sayfasına dönüşür, birleşik PDF indirilir.

## Sistemin şekli

```
tarayıcı
   │  HTTPS
   ▼
Caddy  ──────────── TLS (Let's Encrypt, otomatik yenilenir)
   │  reverse_proxy cmr-frontend:3000
   ▼
Next.js (frontend)
   │  ├─ XLSX'i TARAYICIDA parse eder (ExcelJS) → JSON
   │  └─ /api/proxy/* route'ları server-side, backend'e Bearer ile gider
   ▼
Flask + Gunicorn (backend)
   │  ├─ PyMuPDF ile şablon PDF'i doldurur
   │  ├─ multiprocessing fork havuzu (turbo modda)
   │  └─ birleşik PDF'i diske yazar, URL döner
   ▼
Redis ── iş ilerlemesi (progress), memory fallback'i var
```

## Bileşenler

| Servis | İmaj | Rolü |
|---|---|---|
| `cmr-caddy` | `caddy:2-alpine` | TLS sonlandırma, tek giriş noktası (80/443) |
| `cmr-frontend` | repo'dan build | Next.js standalone; UI + backend'e giden proxy route'lar |
| `cmr-backend` | repo'dan build | Flask/Gunicorn; PDF üretimi |
| `cmr-redis` | `redis:7-alpine` | Progress state (kalıcılık yok, `--save ""`) |
| `cmr-autoheal` | `willfarrell/autoheal` | Unhealthy container'ı 30 sn'de bir restart eder |

Hepsi `cmr-net` bridge ağında. Dışarıya açık tek port: Caddy'nin 80/443'ü.

## Dizinler

```
backend/          Flask uygulaması
  app.py            HTTP katmanı + PDF pipeline (tek dosya, ~500 satır)
  jobs_store.py     Progress state — Redis veya memory
  cleanup_pdfs.py   İndirilmemiş PDF'leri süpüren arka plan thread'i
  database.py       SQLite (yalnızca `users` tablosu; auth henüz kullanmıyor)
  entrypoint.sh     Gunicorn + health monitoring
  *.pdf             CMR şablonu
frontend/         Next.js App Router
  src/app/
    page.tsx              Giriş
    dashboard/            Ana ekran
    components/           convertForm (üretim akışı) · resultPage (sonuç)
    api/proxy/            Backend'e giden server-side proxy
    api/auth/             NextAuth (credentials)
  middleware.ts     Auth guard + şüpheli istek filtresi
deploy/           Host kurulumu (docker daemon config, setup script)
```

## PDF üretim hattı

1. **Tarayıcı** XLSX'i parse eder → JSON satırlar (sunucu Excel görmez)
2. **`/api/proxy/process-pdf`** → backend'e Bearer ile iletir
3. **Backend** başlangıçta şablonun boşaltılmış halini bir kez hesaplar (`_precompute_blanked_template`) — koordinatlar fork'lanan işçilere kopyalanır
4. **Render**: satır sayısı ve moda göre
   - *normal*: sıralı, satır başına yapay 0.55 sn gecikme (CPU dostu)
   - *turbo*: `PARALLEL_WORKERS` kadar fork havuzu, eşik `PARALLEL_MIN_ROWS`
5. **Birleştirme**: sayfalar geldikçe `insert_pdf` ile akıtılır (bellekte biriktirilmez)
6. **Kaydetme**: `garbage=4` tekrarlanan font/logo objelerini tekilleştirir — dosyayı 5 katı küçültür
7. **İndirme**: dosya diske yazılır, URL döner; indirme bitince **silinir**

## Değişmezler

- **Üretilen PDF diskte kalmaz.** İndirme tamamlanınca `after_this_request` ile silinir; indirilmeyenleri `cleanup_pdfs` `PDF_MAX_AGE_HOURS` sonra süpürür.
- **Kalıcı veri yok.** Redis persistence kapalı, SQLite'da yalnızca boş `users` tablosu. Sistem yeniden kurulsa kaybolacak bir şey yok.
- **Backend hep senkron.** `job_id` PDF bittikten *sonra* döner; progress ayrı endpoint'ten okunur.
- **Turbo yalnızca istek başına.** `mode` gövdede gelir, global env'i değiştirmez.
- **Kod imaja girer.** Deploy = build + `compose up -d`. Çalışan container'a dosya kopyalanmaz.
- **`outputs` bind mount'tur, named volume değil** — ölçüldü, named volume aynı işi 2 kat yavaş yapıyor.

## Yapılandırma

Tümü `/opt/cmr/.env` (sunucuda) — compose bunu okur.

| Değişken | Anlamı |
|---|---|
| `CMR_DOMAIN` / `CMR_EMAIL` | Caddy TLS |
| `API_KEY` | Backend Bearer anahtarı |
| `PARALLEL_WORKERS` | Turbo'da fork sayısı — 4 çekirdekte **3** optimal |
| `PARALLEL_MIN_ROWS` | Bu satırdan azsa havuz açılmaz (fork maliyeti > kazanç) |
| `PDF_MAX_AGE_HOURS` | İndirilmemiş PDF'in ömrü |
| `MAX_ROWS_PER_REQUEST` | Üst sınır (aşılırsa 413) |
| `NEXT_PUBLIC_*` | **Tarayıcıya gömülür** — gizli değer koymayın |

## Ölçülmüş davranış

182 satır, 4 çekirdekli Xeon, turbo mod:

| Aşama | Süre |
|---|---|
| render (3 işçi) | ~7 sn |
| kaydetme + sıkıştırma | ~2.5 sn |
| ağ + proxy | ~0.5 sn |
| **toplam** | **~9.5 sn** |

Normal modda aynı dosya ~123 sn (kasıtlı yavaşlatma).

## Bilinen zayıflıklar

- `NEXT_PUBLIC_API_KEY` istemci paketine gömülür — API anahtarı tarayıcıdan okunabilir.
- Giriş sabit kodlanmış (`admin`/`1234`); `users` tablosu kullanılmıyor.
- Hız sınırlama yok.
- Yedekleme ve uyarı mekanizması yok (autoheal restart eder ama kimseye haber vermez).
