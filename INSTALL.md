# CMR — Standalone Kurulum

Dokploy'dan bağımsız, herhangi bir **Ubuntu 20.04+** sunucuda tek komutla tam stack kurulumu.

## Dosyalar

| Dosya | Ne yapar |
|---|---|
| `install.sh` | Akıllı kurulum scripti |
| `docker-compose.yml` | Self-contained compose (Caddy + frontend + backend + redis) |
| `Caddyfile` | Script çalışırken üretilir |
| `.env` | Script çalışırken üretilir, secret'lar içinde |
| `deploy/setup-host.sh` | Host tarafı: Docker GC/log rotation + `cmr-watchdog` ve `cmr-commander` systemd birimleri + bildirim/komut konularını üretir |

## Akıllı özellikler

Script bunları otomatik yapıyor:

- 🌐 **Dil seçimi** — TR / EN, başta sorar
- 🩺 **Sistem kontrolleri** — Ubuntu sürümü, RAM, disk, NTP saat senkronizasyonu
- 💾 **Swap önerisi** — RAM < 2GB ve swap yoksa 2GB swap eklemeyi önerir
- 🐳 **Docker** — yoksa resmi repo'dan kurar
- 🔍 **DNS doğrulama** — domain'in IP'si sunucunun IP'si ile eşleşiyor mu kontrol eder
  - Eşleşmiyorsa: 5 dk bekleyip tekrar dene / HTTP-only moduna geç / yine de devam et / iptal
  - **Cloudflare proxy** tespit edilirse ayrı uyarı verir
- 🚪 **Port çakışması** — 80/443 zaten kullanımdaysa hangi process'in tuttuğunu söyler
- 🔐 **SSH failsafe** — SSH ile bağlı olduğun IP'yi UFW whitelist'e koyar (kilitlenme koruması)
- 🔑 **Otomatik secret üretimi** — `API_KEY` ve `NEXTAUTH_SECRET` openssl ile rastgele
- 💾 **Yedek** — eski `.env` varsa `.env.bak.<timestamp>` olarak yedeklenir
- ⚡ **Caddy otomatik TLS** — Let's Encrypt HTTP-01 challenge
- 🔥 **UFW firewall** — sadece SSH portu + 80 + 443 açık
- 🩹 **Autoheal** — unhealthy container'ları otomatik restart eder
- 🎁 **Final summary** — secret'ları son ekrana basar (tek seferlik)
- ⏱ **Spinner + süre** — uzun çalışan apt/docker adımlarında canlı progress (`⠋ Docker indirme + kurulum (1-3 dk)... ✓ (47s)`)

## Çalıştırma modları

```bash
# Mod 1 — tek satır (curl|bash) — en hızlı
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/very6778/cmr/main/install.sh \
  | REPO_URL=https://github.com/very6778/cmr.git bash'

# Mod 2 — repo'yu klonladıktan sonra
git clone https://github.com/very6778/cmr.git /opt/cmr
cd /opt/cmr && sudo bash install.sh

# Otomatik mod (CI/CD için, hiç soru sormaz)
sudo LANG_SEL=tr DOMAIN=cmr.example.com EMAIL=admin@example.com \
  bash -c 'curl -fsSL https://raw.githubusercontent.com/very6778/cmr/main/install.sh \
    | REPO_URL=https://github.com/very6778/cmr.git bash'

# TLS'siz mod (Cloudflare Tunnel arkasında)
sudo NO_TLS=1 bash install.sh

# Private repo (token ile)
sudo GITHUB_TOKEN='ghp_xxx' REPO_URL=https://github.com/very6778/cmr.git \
  bash install.sh
```

## Ortam değişkenleri

| Değişken | Default | Açıklama |
|---|---|---|
| `LANG_SEL` | (sorulur) | `tr` veya `en` |
| `REPO_URL` | (sorulur) | Git repo URL (curl\|bash modunda) |
| `INSTALL_DIR` | `/opt/cmr` | Hedef dizin |
| `DOMAIN` | (sorulur) | Sitenin domain'i |
| `EMAIL` | (sorulur) | Let's Encrypt admin email |
| `NO_TLS` | `0` | `1` = sadece HTTP (CF Tunnel için) |
| `SKIP_DNS_CHECK` | `0` | `1` = DNS doğrulamasını atla |
| `GITHUB_TOKEN` | (yok) | Private repo clone'lamak için GitHub token |

## TUI önizleme

```
  ╔══════════════════════════════════════════════╗
  ║            CMR Installer  v1.1               ║
  ╚══════════════════════════════════════════════╝

  Language / Dil:
    1) Türkçe
    2) English
  [1-2, default=1]: 1

  Bu script şunları yapacak:
    1. Sistem kontrolleri (OS, RAM, disk, saat)
    2. Docker + Compose kurulumu (yoksa)
    3. Repo'yu INSTALL_DIR'e yerleştir
    4. Secret'ları üret, DNS'i doğrula
    5. Caddy (otomatik TLS) + firewall
    6. Servisleri build & başlat, health-check

▸ [1/8] Sistem kontrolü
  ✓ root
  ✓ Ubuntu 22.04 (jammy)
  ✓ RAM: 4096MB
  ✓ Disk: 18450MB free
  ✓ Time synchronized

▸ [2/8] Bağımlılıklar
  ✓ apt update
  ✓ curl, git, ufw, openssl, dnsutils
  ✓ Docker 27.3.1

...

▸ [5/8] DNS & TLS kontrolü
  · Sunucu IP: 46.37.115.41
  · cmr.example.com → 1.2.3.4
  ✗ DNS uyuşmazlığı tespit edildi
    1) 5 dakika bekle ve tekrar dene
    2) Sadece HTTP ile devam et (TLS yok)
    3) Yine de devam et (TLS muhtemelen başarısız olacak)
    4) İptal
  [1-4]: 1
  · Bekleniyor (5 dk)... attempt 1
  ..............................

▸ [6/8] Firewall
  ✓ Failsafe: 78.x.x.x whitelisted
  ✓ UFW: 22, 80, 443

...

  ✓ Kurulum tamamlandı

  URL:    https://cmr.example.com
  Dir:    /opt/cmr
  Logs:   cd /opt/cmr && docker compose logs -f
  Stop:   cd /opt/cmr && docker compose down

  Üretilen secret'lar (şimdi kaydet, bir daha gösterilmeyecek):
    API_KEY=a73fdad20b66...
    NEXTAUTH_SECRET=661d1e5ea2...
```

## Sonrası

```bash
# Logları izle
cd /opt/cmr && docker compose logs -f

# Durdur
cd /opt/cmr && docker compose down

# Güncelle (git pull + rebuild + restart)
cd /opt/cmr && git pull && \
  docker compose up -d --build
```

## Sorun giderme

- **TLS sertifikası alınamadı:** Domain'in A kaydı bu sunucuya işaret etmiyor olabilir, ya da Cloudflare proxy açık. `dig +short DOMAIN` ile kontrol et.
- **Port 80/443 dolu:** `ss -tlnp | grep -E ':(80|443)'` ile hangi process'in tuttuğuna bak. nginx/apache çalışıyorsa durdur: `sudo systemctl stop nginx apache2`.
- **Healthcheck timeout:** `docker compose logs backend` ile backend hatalarına bak.
- **SSH bağlantı kesildi:** Failsafe IP eklendiği için kaynak IP'nden geri girebilirsin; değilse provider VNC.
