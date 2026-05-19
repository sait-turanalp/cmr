#!/usr/bin/env bash
# CMR Installer — Ubuntu 20.04+ icin akilli, tek komutluk kurulum.
#
# Kullanim:
#   1) Repo'dan:   git clone <repo> /opt/cmr && cd /opt/cmr && sudo bash install.sh
#   2) curl|bash:  curl -fsSL https://.../install.sh | sudo REPO_URL=https://github.com/USER/cmr.git bash
#
# Opsiyonel ortam degiskenleri:
#   LANG_SEL     tr|en (sormamasi icin)
#   REPO_URL     Klonlanacak git repo URL'i (curl|bash modunda gerekli)
#   INSTALL_DIR  Hedef dizin (default: /opt/cmr)
#   DOMAIN       Sitenin domain'i
#   EMAIL        Let's Encrypt admin email
#   NO_TLS       1 = TLS yok, sadece HTTP 80
#   SKIP_DNS_CHECK  1 = DNS dogrulamasini atla
#   GITHUB_TOKEN Private repo'lar icin GitHub token (HTTPS clone'da kullanilir)

set -euo pipefail

# ─── renkler ───────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  B='\033[1;34m'; G='\033[1;32m'; R='\033[1;31m'; Y='\033[1;33m'
  D='\033[0;37m'; BD='\033[1m'; X='\033[0m'
else
  B=''; G=''; R=''; Y=''; D=''; BD=''; X=''
fi

# stdin pipe ise terminal'den oku
TTY=/dev/tty
[[ -r /dev/tty ]] || TTY=/dev/stdin
ask() { local prompt="$1" var; read -rp "  $prompt" var < $TTY; echo "$var"; }

INSTALL_DIR="${INSTALL_DIR:-/opt/cmr}"
REPO_URL="${REPO_URL:-}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
NO_TLS="${NO_TLS:-0}"
SKIP_DNS_CHECK="${SKIP_DNS_CHECK:-0}"
LANG_SEL="${LANG_SEL:-}"

# ─── dil secimi ────────────────────────────────────────────────────
clear || true
echo
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║            CMR Installer  v1.1               ║"
echo "  ╚══════════════════════════════════════════════╝"
echo

if [[ -z "$LANG_SEL" ]]; then
  echo "  Language / Dil:"
  echo "    1) Türkçe"
  echo "    2) English"
  ans=$(ask "[1-2, default=1]: ")
  case "${ans:-1}" in
    2|en|EN|English) LANG_SEL="en" ;;
    *) LANG_SEL="tr" ;;
  esac
fi

# ─── ceviriler ─────────────────────────────────────────────────────
load_lang() {
  if [[ "$LANG_SEL" == "en" ]]; then
    M_INTRO_TITLE="This script will do the following:"
    M_S1="System checks (OS, RAM, disk, time)"
    M_S2="Install Docker + Compose (if missing)"
    M_S3="Place repo at INSTALL_DIR"
    M_S4="Configure secrets, validate DNS"
    M_S5="Set up Caddy (auto-TLS) and firewall"
    M_S6="Build & start services, health check"
    M_STEP1="System check"
    M_STEP2="Dependencies"
    M_STEP3="Project files"
    M_STEP4="Configuration"
    M_STEP5="DNS & TLS checks"
    M_STEP6="Firewall"
    M_STEP7="Services"
    M_STEP8="Health"
    M_ASK_DOMAIN="Domain (e.g. cmr.example.com): "
    M_ASK_EMAIL="Let's Encrypt admin email: "
    M_ASK_REPO="Git repo URL: "
    M_DONE="Installation complete"
    M_DNS_OK="DNS resolves to this server"
    M_DNS_MISMATCH="DNS mismatch detected"
    M_DNS_WAIT="Wait 5 minutes and retry"
    M_DNS_OPT1="1) Wait 5 min and retry"
    M_DNS_OPT2="2) Continue with HTTP only (no TLS)"
    M_DNS_OPT3="3) Continue anyway (TLS will likely fail)"
    M_DNS_OPT4="4) Abort"
    M_PORT_BUSY="Port already in use"
    M_TIME_DRIFT="System clock not synchronized (TLS may fail)"
    M_SWAP_LOW="Low RAM and no swap — consider adding swap"
    M_SECRETS_TITLE="Generated secrets (save these now, they won't be shown again):"
  else
    M_INTRO_TITLE="Bu script şunları yapacak:"
    M_S1="Sistem kontrolleri (OS, RAM, disk, saat)"
    M_S2="Docker + Compose kurulumu (yoksa)"
    M_S3="Repo'yu INSTALL_DIR'e yerleştir"
    M_S4="Secret'ları üret, DNS'i doğrula"
    M_S5="Caddy (otomatik TLS) + firewall"
    M_S6="Servisleri build & başlat, health-check"
    M_STEP1="Sistem kontrolü"
    M_STEP2="Bağımlılıklar"
    M_STEP3="Proje dosyaları"
    M_STEP4="Konfigürasyon"
    M_STEP5="DNS & TLS kontrolü"
    M_STEP6="Firewall"
    M_STEP7="Servisler"
    M_STEP8="Sağlık kontrolü"
    M_ASK_DOMAIN="Domain (örn. cmr.example.com): "
    M_ASK_EMAIL="Let's Encrypt admin email: "
    M_ASK_REPO="Git repo URL: "
    M_DONE="Kurulum tamamlandı"
    M_DNS_OK="DNS bu sunucuya yönleniyor"
    M_DNS_MISMATCH="DNS uyuşmazlığı tespit edildi"
    M_DNS_WAIT="5 dakika bekleyip tekrar dene"
    M_DNS_OPT1="1) 5 dakika bekle ve tekrar dene"
    M_DNS_OPT2="2) Sadece HTTP ile devam et (TLS yok)"
    M_DNS_OPT3="3) Yine de devam et (TLS muhtemelen başarısız olacak)"
    M_DNS_OPT4="4) İptal"
    M_PORT_BUSY="Port zaten kullanımda"
    M_TIME_DRIFT="Sistem saati senkron değil (TLS başarısız olabilir)"
    M_SWAP_LOW="Düşük RAM ve swap yok — swap eklemek mantıklı olabilir"
    M_SECRETS_TITLE="Üretilen secret'lar (şimdi kaydet, bir daha gösterilmeyecek):"
  fi
}
load_lang

step() { echo -e "\n${B}▸${X} ${BD}$1${X}"; }
ok()   { echo -e "  ${G}✓${X} $1"; }
warn() { echo -e "  ${Y}!${X} $1"; }
err()  { echo -e "  ${R}✗${X} $1" >&2; }
info() { echo -e "  ${D}·${X} $1"; }
die()  { err "$1"; exit 1; }

# run_step "msg" cmd... — komutu calistirir, yaninda spinner doner,
# bitince sure ile birlikte ✓ ya da ✗ basar. Hata varsa loglari gosterir.
run_step() {
  local msg="$1"; shift
  local logf
  logf=$(mktemp)
  local start=$(date +%s)
  printf "  ${D}·${X} ${msg}... "
  ( "$@" ) >"$logf" 2>&1 &
  local pid=$!
  local sp='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    printf "\b${B}${sp:$((i%10)):1}${X}"
    sleep 0.15
    i=$((i+1))
  done
  wait "$pid"; local rc=$?
  local elapsed=$(( $(date +%s) - start ))
  if (( rc == 0 )); then
    printf "\b${G}✓${X} ${D}(${elapsed}s)${X}\n"
    rm -f "$logf"
    return 0
  else
    printf "\b${R}✗${X} ${D}(exit ${rc})${X}\n"
    echo "  ── last log lines ──"
    tail -15 "$logf" | sed 's/^/    /'
    rm -f "$logf"
    return $rc
  fi
}

# ─── intro ─────────────────────────────────────────────────────────
echo
echo -e "  ${BD}${M_INTRO_TITLE}${X}"
echo -e "    ${D}1.${X} ${M_S1}"
echo -e "    ${D}2.${X} ${M_S2}"
echo -e "    ${D}3.${X} ${M_S3}"
echo -e "    ${D}4.${X} ${M_S4}"
echo -e "    ${D}5.${X} ${M_S5}"
echo -e "    ${D}6.${X} ${M_S6}"

# ─── 1) pre-flight ─────────────────────────────────────────────────
step "[1/8] ${M_STEP1}"

[[ $EUID -eq 0 ]] || die "Run as root: sudo bash install.sh"
ok "root"

[[ -f /etc/os-release ]] || die "No /etc/os-release"
. /etc/os-release
[[ "${ID}" == "ubuntu" ]] || die "Only Ubuntu supported (detected: $ID)"
ok "Ubuntu ${VERSION_ID} (${VERSION_CODENAME})"

MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
SWAP_MB=$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)
if (( MEM_MB < 1800 )); then warn "RAM: ${MEM_MB}MB"; else ok "RAM: ${MEM_MB}MB"; fi

if (( MEM_MB < 2048 && SWAP_MB < 1024 )); then
  warn "$M_SWAP_LOW"
  ans=$(ask "Add 2GB swap? [y/N]: ")
  if [[ "${ans,,}" =~ ^y ]]; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q "^/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
    ok "2GB swap eklendi"
  fi
fi

DISK_FREE=$(df -m / | awk 'NR==2 {print $4}')
if (( DISK_FREE < 5120 )); then warn "Disk: ${DISK_FREE}MB free"; else ok "Disk: ${DISK_FREE}MB free"; fi

# saat senkron mu?
if command -v timedatectl >/dev/null 2>&1; then
  SYNC=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo "no")
  if [[ "$SYNC" == "yes" ]]; then
    ok "Time synchronized"
  else
    warn "$M_TIME_DRIFT"
    timedatectl set-ntp true 2>/dev/null || true
    sleep 2
    ok "NTP açıldı"
  fi
fi

# ─── 2) deps + docker ──────────────────────────────────────────────
step "[2/8] ${M_STEP2}"

export DEBIAN_FRONTEND=noninteractive
run_step "apt update" apt-get update -qq
run_step "Paketler (curl, git, ufw, openssl, dnsutils)" \
  apt-get install -y -qq ca-certificates curl gnupg lsb-release git ufw openssl dnsutils

if ! command -v docker >/dev/null 2>&1; then
  run_step "Docker repo anahtarı" bash -c '
    install -m 0755 -d /etc/apt/keyrings &&
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg &&
    chmod a+r /etc/apt/keyrings/docker.gpg &&
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu '"$VERSION_CODENAME"' stable" \
      > /etc/apt/sources.list.d/docker.list'
  run_step "apt update (docker repo dahil)" apt-get update -qq
  run_step "Docker indirme + kurulum (1-3 dk)" \
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker >/dev/null
  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',') hazır"
else
  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',') zaten kurulu"
fi

docker compose version >/dev/null 2>&1 || die "docker compose plugin missing"
ok "Docker Compose"

# ─── 3) repo ───────────────────────────────────────────────────────
step "[3/8] ${M_STEP3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"

if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/docker-compose.standalone.yml" && -f "$SCRIPT_DIR/Dockerfile.backend" ]]; then
  INSTALL_DIR="$SCRIPT_DIR"
  ok "Local repo: $INSTALL_DIR"
elif [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Updating existing: $INSTALL_DIR"
  CUR_URL=$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || echo "")
  if [[ -n "${GITHUB_TOKEN:-}" && "$CUR_URL" =~ ^https://github\.com/ ]]; then
    AUTH_URL="${CUR_URL/https:\/\/github.com\//https://x-access-token:${GITHUB_TOKEN}@github.com/}"
    git -C "$INSTALL_DIR" remote set-url origin "$AUTH_URL"
    git -C "$INSTALL_DIR" pull --rebase --autostash
    git -C "$INSTALL_DIR" remote set-url origin "$CUR_URL"
    unset GITHUB_TOKEN AUTH_URL
  else
    git -C "$INSTALL_DIR" pull --rebase --autostash
  fi
  ok "Repo updated"
else
  [[ -n "$REPO_URL" ]] || REPO_URL=$(ask "$M_ASK_REPO")
  [[ -n "$REPO_URL" ]] || die "REPO_URL required"
  info "Cloning: $REPO_URL → $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  # Private repo icin GITHUB_TOKEN'i URL'e enjekte et (sadece bu komut icin)
  if [[ -n "${GITHUB_TOKEN:-}" && "$REPO_URL" =~ ^https://github\.com/ ]]; then
    AUTH_URL="${REPO_URL/https:\/\/github.com\//https://x-access-token:${GITHUB_TOKEN}@github.com/}"
    git clone "$AUTH_URL" "$INSTALL_DIR"
    # Remote'ta token kalmasın — token-suz versiyonla değiştir
    git -C "$INSTALL_DIR" remote set-url origin "$REPO_URL"
    unset GITHUB_TOKEN AUTH_URL
  else
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  ok "Cloned"
fi
cd "$INSTALL_DIR"

# ─── 4) config ─────────────────────────────────────────────────────
step "[4/8] ${M_STEP4}"

if [[ "$NO_TLS" != "1" ]]; then
  [[ -n "$DOMAIN" ]] || DOMAIN=$(ask "$M_ASK_DOMAIN")
  [[ -n "$EMAIL" ]]  || EMAIL=$(ask "$M_ASK_EMAIL")
fi

# secrets üret (önceki .env'i yedekle)
if [[ -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak.$(date +%s)"
  warn ".env yedeklendi → .env.bak.*"
  set -a; . "$INSTALL_DIR/.env"; set +a
  API_KEY="${API_KEY:-$(openssl rand -hex 32)}"
  NEXTAUTH_SECRET="${NEXTAUTH_SECRET:-$(openssl rand -hex 24)}"
else
  API_KEY=$(openssl rand -hex 32)
  NEXTAUTH_SECRET=$(openssl rand -hex 24)
fi

PROTO="https"; [[ "$NO_TLS" == "1" ]] && PROTO="http"
EFFECTIVE_HOST="${DOMAIN:-localhost}"

cat > "$INSTALL_DIR/.env" <<ENV
# CMR — install.sh tarafından oluşturuldu
CMR_DOMAIN=${EFFECTIVE_HOST}
CMR_EMAIL=${EMAIL:-admin@example.com}
PUBLIC_URL=${PROTO}://${EFFECTIVE_HOST}

API_KEY=${API_KEY}
CORS_DOMAIN=${PROTO}://${EFFECTIVE_HOST}
REDIS_URL=redis://redis:6379/0
JOBS_BACKEND=redis
PDF_MAX_AGE_HOURS=2
PARALLEL_WORKERS=3
PARALLEL_MIN_ROWS=100
MAX_ROWS_PER_REQUEST=3000

NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
NEXTAUTH_URL=${PROTO}://${EFFECTIVE_HOST}
NEXT_PUBLIC_API_URL=${PROTO}://${EFFECTIVE_HOST}
NEXT_PUBLIC_API_KEY=${API_KEY}
ENV
chmod 600 "$INSTALL_DIR/.env"
ok ".env yazıldı"

# ─── 5) DNS & TLS checks ───────────────────────────────────────────
step "[5/8] ${M_STEP5}"

if [[ "$NO_TLS" == "1" ]]; then
  info "NO_TLS=1 → DNS check atlanıyor"
elif [[ "$SKIP_DNS_CHECK" == "1" ]]; then
  warn "SKIP_DNS_CHECK=1 → atlanıyor"
else
  # sunucunun public IP'si
  SERVER_IP=$(curl -s --max-time 5 https://api.ipify.org || curl -s --max-time 5 https://ifconfig.me || echo "")
  [[ -n "$SERVER_IP" ]] || warn "Sunucu IP'si tespit edilemedi"
  info "Sunucu IP: ${SERVER_IP:-?}"

  # port 80/443 boş mu?
  for port in 80 443; do
    if ss -tlnp 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
      OWNER=$(ss -tlnp 2>/dev/null | grep ":${port} " | head -1 | sed 's/.*users:(("//; s/".*//')
      warn "$M_PORT_BUSY: $port (sahibi: ${OWNER:-bilinmiyor})"
    fi
  done

  check_dns() {
    local d="$1"
    dig +short A "$d" @1.1.1.1 2>/dev/null | tail -n1
  }

  is_cf_ip() {
    local ip="$1" oct1 oct2
    oct1=${ip%%.*}; rest=${ip#*.}; oct2=${rest%%.*}
    case "$oct1.$oct2" in
      104.1[6-9]|104.2[0-7]|172.6[4-9]|172.7[0-1]|173.245|103.21|103.22|103.31|141.101|108.162|190.93|188.114|197.234|198.41|162.158|131.0|104.16) return 0 ;;
    esac
    return 1
  }

  attempt=0
  while :; do
    DOMAIN_IP=$(check_dns "$DOMAIN")
    info "${DOMAIN} → ${DOMAIN_IP:-resolve edilemedi}"

    if [[ "$DOMAIN_IP" == "$SERVER_IP" && -n "$DOMAIN_IP" ]]; then
      ok "$M_DNS_OK"
      break
    fi

    err "$M_DNS_MISMATCH"
    if [[ -n "$DOMAIN_IP" ]] && is_cf_ip "$DOMAIN_IP"; then
      warn "$DOMAIN_IP Cloudflare IP'si gibi görünüyor — proxy (turuncu bulut) açık olabilir"
      warn "Caddy'nin Let's Encrypt almasi icin ya CF proxy'yi kapat (DNS only/gri bulut) ya da NO_TLS=1 ile çalıştır"
    fi

    echo "    $M_DNS_OPT1"
    echo "    $M_DNS_OPT2"
    echo "    $M_DNS_OPT3"
    echo "    $M_DNS_OPT4"
    ans=$(ask "[1-4]: ")
    case "$ans" in
      1)
        attempt=$((attempt+1))
        info "Bekleniyor (5 dk)... attempt $attempt"
        for i in $(seq 1 30); do printf "."; sleep 10; done; echo
        ;;
      2) NO_TLS=1
         PROTO="http"
         sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=http://${EFFECTIVE_HOST}|; s|^CORS_DOMAIN=.*|CORS_DOMAIN=http://${EFFECTIVE_HOST}|; s|^NEXTAUTH_URL=.*|NEXTAUTH_URL=http://${EFFECTIVE_HOST}|; s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${EFFECTIVE_HOST}|" "$INSTALL_DIR/.env"
         warn "NO_TLS moduna geçildi"; break ;;
      3) warn "Devam ediliyor, TLS başarısız olabilir"; break ;;
      *) die "İptal edildi" ;;
    esac
  done
fi

# Caddyfile üret
if [[ "$NO_TLS" == "1" ]]; then
  cat > "$INSTALL_DIR/Caddyfile" <<EOF
:80 {
    encode gzip
    reverse_proxy frontend:3000
}
EOF
  ok "Caddyfile (HTTP-only)"
else
  cat > "$INSTALL_DIR/Caddyfile" <<EOF
{
    email {\$CMR_EMAIL}
}

{\$CMR_DOMAIN} {
    encode gzip
    reverse_proxy frontend:3000
}
EOF
  ok "Caddyfile (auto-TLS)"
fi

# ─── 6) firewall ───────────────────────────────────────────────────
step "[6/8] ${M_STEP6}"

# SSH portunu sshd_config'ten al
SSH_PORT=$(awk '/^Port / {print $2; exit}' /etc/ssh/sshd_config 2>/dev/null || echo 22)
SSH_PORT=${SSH_PORT:-22}

# kilitlenme failsafe: bağlı olduğumuz IP'yi whitelist'e
if [[ -n "${SSH_CLIENT:-}" ]]; then
  SRC_IP="${SSH_CLIENT%% *}"
  ufw allow from "$SRC_IP" >/dev/null 2>&1 || true
  ok "Failsafe: ${SRC_IP} whitelisted"
fi

if ufw status | grep -q "Status: inactive"; then
  ufw --force default deny incoming >/dev/null
  ufw --force default allow outgoing >/dev/null
fi
ufw allow ${SSH_PORT}/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ok "UFW: ${SSH_PORT}, 80, 443"

# ─── 7) build + up ─────────────────────────────────────────────────
step "[7/8] ${M_STEP7}"

run_step "Image build (ilk seferde 2-5 dk)" \
  docker compose -f docker-compose.standalone.yml --env-file .env build
run_step "Container'lar başlatılıyor" \
  docker compose -f docker-compose.standalone.yml --env-file .env up -d

# ─── 8) health ─────────────────────────────────────────────────────
step "[8/8] ${M_STEP8}"

info "Servislerin hazır olması bekleniyor..."
for i in $(seq 1 90); do
  HEALTHY=$(docker compose -f docker-compose.standalone.yml ps --format json 2>/dev/null | grep -c '"Health":"healthy"' || true)
  if (( HEALTHY >= 2 )); then ok "Healthy: $HEALTHY container"; break; fi
  sleep 2
done

docker compose -f docker-compose.standalone.yml ps --format "table {{.Name}}\t{{.Status}}"

# ─── final summary ─────────────────────────────────────────────────
echo
echo -e "${G}${BD}  ✓ ${M_DONE}${X}"
echo
if [[ "$NO_TLS" == "1" ]]; then
  PUB="http://${EFFECTIVE_HOST}"
else
  PUB="https://${DOMAIN}"
fi
echo -e "  ${BD}URL:${X}    ${PUB}"
echo -e "  ${BD}Dir:${X}    $INSTALL_DIR"
echo -e "  ${BD}Logs:${X}   cd $INSTALL_DIR && docker compose -f docker-compose.standalone.yml logs -f"
echo -e "  ${BD}Stop:${X}   cd $INSTALL_DIR && docker compose -f docker-compose.standalone.yml down"
echo
echo -e "  ${Y}${BD}${M_SECRETS_TITLE}${X}"
echo -e "    ${D}API_KEY=${X}${API_KEY}"
echo -e "    ${D}NEXTAUTH_SECRET=${X}${NEXTAUTH_SECRET}"
echo
echo -e "  ${D}(Bunlar ${INSTALL_DIR}/.env içinde de kayıtlı)${X}"
echo
