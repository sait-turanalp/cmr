#!/bin/sh
# Sunucu disk hijyeni — yeni bir host'a tasinirken bir kez calistirilir.
# Hicbir cron/timer kurmaz: her sey Docker'in kendi mekanizmalari.
#
#   curl -fsSL <raw-url>/deploy/setup-host.sh | sh
# veya repo icinden:  sh deploy/setup-host.sh
set -e

HERE=$(dirname "$0")

# 1) Docker daemon: build cache GC (2GB tavan) + log rotation (10m x3).
#    Build cache'in 25GB'a cikmasini Docker kendi engeller — cron gerekmez.
mkdir -p /etc/docker
if [ -f /etc/docker/daemon.json ]; then
  cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
  echo "mevcut daemon.json -> daemon.json.bak"
fi
cp "$HERE/docker-daemon.json" /etc/docker/daemon.json

# 2) logrotate: daemon.json log-opts SADECE yeni container'lara uygulanir.
#    Bu kural mevcut olanlari da kapsar (recreate beklemeden).
cat > /etc/logrotate.d/docker-containers <<'EOF'
/var/lib/docker/containers/*/*-json.log {
  rotate 3
  size 10M
  copytruncate
  missingok
  notifempty
  compress
  delaycompress
}
EOF

# 3) Daemon'u yeni ayarlarla baslat. Container'lar restart policy ile geri gelir.
systemctl restart docker
until docker info >/dev/null 2>&1; do sleep 2; done

# 4) Tek seferlik: birikmis cache/image temizligi.
docker builder prune -af >/dev/null 2>&1 || true
docker image prune -af >/dev/null 2>&1 || true

echo "tamam. disk:"
df -h / | tail -1
docker system df
