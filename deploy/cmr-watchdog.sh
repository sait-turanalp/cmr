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

# Teknik container adlarini insan diline cevir — bildirimde "cmr-backend"
# degil "PDF servisi" gorunsun.
human_name() {
    case "$1" in
        cmr-backend)  echo "PDF servisi" ;;
        cmr-frontend) echo "Web arayuzu" ;;
        cmr-caddy)    echo "Site erisimi" ;;
        cmr-redis)    echo "Is takibi" ;;
        *)            echo "$1" ;;
    esac
}

# Insan diliyle sure: "45 saniye", "3 dakika", "1 saat 5 dakika"
human_duration() {
    s=$1
    [ "$s" -lt 0 ] 2>/dev/null && s=0
    if [ "$s" -lt 90 ]; then
        echo "$s saniye"
    elif [ "$s" -lt 5400 ]; then
        echo "$(( s / 60 )) dakika"
    else
        h=$(( s / 3600 )); m=$(( (s % 3600) / 60 ))
        [ "$m" -eq 0 ] && echo "$h saat" || echo "$h saat $m dakika"
    fi
}

DEAD=""
DEAD_HUMAN=""
DOWN_SINCE=0
for c in $EXPECTED; do
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
    if [ "$state" != "running" ]; then
        DEAD="$DEAD $c($state)"
        DEAD_HUMAN="$DEAD_HUMAN$(human_name "$c"), "
        # Ne zaman durdu? En erken duran servisi baz al.
        fin=$(docker inspect -f '{{.State.FinishedAt}}' "$c" 2>/dev/null)
        fin_ts=$(date -d "$fin" +%s 2>/dev/null || echo 0)
        if [ "$fin_ts" -gt 0 ]; then
            [ "$DOWN_SINCE" -eq 0 ] && DOWN_SINCE=$fin_ts
            [ "$fin_ts" -lt "$DOWN_SINCE" ] && DOWN_SINCE=$fin_ts
        fi
    fi
done
DEAD_HUMAN=$(echo "$DEAD_HUMAN" | sed 's/, $//')

[ -z "$DEAD" ] && exit 0    # saglikli: sessiz cik

logger -t cmr-watchdog "olu servis bulundu:$DEAD — toparlaniyor"
cd "$APP_DIR" && docker compose up -d --remove-orphans >/dev/null 2>&1 || true

sleep 12
STILL=""
STILL_HUMAN=""
for c in $EXPECTED; do
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
    if [ "$state" != "running" ]; then
        STILL="$STILL $c($state)"
        STILL_HUMAN="$STILL_HUMAN$(human_name "$c"), "
    fi
done
STILL_HUMAN=$(echo "$STILL_HUMAN" | sed 's/, $//')

if [ -z "$STILL" ]; then
    logger -t cmr-watchdog "toparlandi:$DEAD"
    if [ "$DOWN_SINCE" -gt 0 ]; then
        OUTAGE=$(human_duration $(( $(date +%s) - DOWN_SINCE )))
    else
        OUTAGE="kisa bir sure"
    fi
    logger -t cmr-watchdog "kesinti suresi: $OUTAGE"
    sh "$HERE/notify.sh" "Sistem kendini onardi" \
       "$DEAD_HUMAN $OUTAGE durdu, geri geldi.
Bir sey yapmana gerek yok.

https://yedek.opik.online" \
       "default" "white_check_mark" "ok-$DEAD_HUMAN"
else
    logger -t cmr-watchdog "TOPARLANAMADI:$STILL"
    if [ "$DOWN_SINCE" -gt 0 ]; then
        OUTAGE=$(human_duration $(( $(date +%s) - DOWN_SINCE )))
    else
        OUTAGE="bilinmiyor"
    fi
    sh "$HERE/notify.sh" "Site calismiyor" \
       "$STILL_HUMAN $OUTAGE once durdu, kalkmiyor.
Otomatik toparlama denendi, basarisiz. Sunucuya bakman gerek.

https://yedek.opik.online" \
       "urgent" "rotating_light" "fail-$STILL_HUMAN"
fi
