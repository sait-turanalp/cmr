#!/bin/sh
# Olu/eksik container'i kaldirir.
#
# NEDEN: Docker'in restart:always politikasi, container API uzerinden
# durdurulmussa (docker stop / docker kill / basarisiz docker restart)
# KASTEN devreye girmez — RestartCount 0'da kalir. 19 Agustos'ta site tam bu
# yuzden 17 saat olu kaldi (autoheal'in basarisiz restart'i). Battle test'te
# de dogrulandi. Bu script o tek bosluğu kapatir.
#
# Her sey ayaktaysa HICBIR SEY yapmaz — bedeli sadece birkac docker inspect.
set -e

APP_DIR="${CMR_DIR:-/opt/cmr}"
HERE=$(dirname "$0")
EXPECTED="cmr-caddy cmr-frontend cmr-backend cmr-redis"

DEAD=""
for c in $EXPECTED; do
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
    [ "$state" = "running" ] || DEAD="$DEAD $c($state)"
done

[ -z "$DEAD" ] && exit 0    # saglikli: sessiz cik

logger -t cmr-watchdog "olu servis bulundu:$DEAD — toparlaniyor"
cd "$APP_DIR" && docker compose up -d --remove-orphans >/dev/null 2>&1 || true

sleep 12
STILL=""
for c in $EXPECTED; do
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
    [ "$state" = "running" ] || STILL="$STILL $c($state)"
done

if [ -z "$STILL" ]; then
    logger -t cmr-watchdog "toparlandi:$DEAD"
    sh "$HERE/notify.sh" "CMR toparlandi" "Olu servis:$DEAD
Otomatik kaldirildi, sistem calisiyor." "default"
else
    logger -t cmr-watchdog "TOPARLANAMADI:$STILL"
    sh "$HERE/notify.sh" "CMR MUDAHALE GEREKIYOR" "Kaldirilamayan servis:$STILL
Sunucuya baglanip kontrol et." "urgent"
fi
