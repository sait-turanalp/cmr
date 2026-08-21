#!/bin/sh
# Haftalik saglik ozeti — sessiz bozulmayi erken yakalamak icin.
APP_DIR="${CMR_DIR:-/opt/cmr}"
HERE=$(dirname "$0")

DISK=$(df -h / | awk 'NR==2{print $5" dolu ("$4" bos)"}')
MEM=$(free -m | awk 'NR==2{printf "%dMB/%dMB", $3, $2}')
LINES=""
for c in cmr-caddy cmr-frontend cmr-backend cmr-redis; do
    st=$(docker inspect -f '{{.State.Status}} restart={{.RestartCount}}' "$c" 2>/dev/null || echo "YOK")
    up=$(docker inspect -f '{{.State.StartedAt}}' "$c" 2>/dev/null | cut -dT -f1)
    LINES="$LINES
$c: $st (calisiyor: $up)"
done
PDFS=$(ls "$APP_DIR"/backend/outputs/*.pdf 2>/dev/null | wc -l | tr -d ' ')

sh "$HERE/notify.sh" "CMR haftalik ozet" "Disk: $DISK
RAM: $MEM
Bekleyen PDF: $PDFS$LINES" "low"
