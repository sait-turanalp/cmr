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

# --- Bellek esigi uyarisi -------------------------------------------------
# NEDEN: sisme/sizinti sessizce ilerler; container mem_limit'e dayanip OOM ile
# olene kadar hicbir sey belli olmaz. %90'da haber ver, olmeden once.
# Tekrar plani: hemen · +10dk · +20dk · sonra +10sa'de son hatirlatma · sus.
# Bellek normale donunce durum sifirlanir (yeni bir olayda bastan baslar).
# ponytail: tek durum dosyasi — ayni anda farkli servislerin dolmasi nadir.
MEM_STATE=/var/tmp/.cmr-mem-alert
MEM_THRESHOLD="${CMR_MEM_THRESHOLD:-90}"
OVER=""

MEM_TOTAL=$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)
MEM_AVAIL=$(awk '/^MemAvailable:/{print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)
if [ "$MEM_TOTAL" -gt 0 ]; then
    HOST_PCT=$(( (MEM_TOTAL - MEM_AVAIL) * 100 / MEM_TOTAL ))
    if [ "$HOST_PCT" -ge "$MEM_THRESHOLD" ]; then
        OVER="Sunucu bellegi %$HOST_PCT dolu."
    fi
fi

# Container yuzdesi kendi mem_limit'ine goredir — asil OOM riski budur.
CSTATS=$(docker stats --no-stream --format '{{.Name}}|{{.MemPerc}}' 2>/dev/null || true)
for line in $CSTATS; do
    cname=${line%%|*}
    cpct=${line##*|}; cpct=${cpct%\%}; cpct=${cpct%%.*}
    case " $EXPECTED " in *" $cname "*) ;; *) continue ;; esac
    case "$cpct" in ''|*[!0-9]*) continue ;; esac
    if [ "$cpct" -ge "$MEM_THRESHOLD" ]; then
        OVER="$OVER $(human_name "$cname") bellegin %$cpct'ini kullaniyor."
    fi
done

if [ -z "$OVER" ]; then
    rm -f "$MEM_STATE"
else
    COUNT=0; LAST=0
    if [ -f "$MEM_STATE" ]; then
        COUNT=$(cut -d' ' -f1 "$MEM_STATE" 2>/dev/null || echo 0)
        LAST=$(cut -d' ' -f2 "$MEM_STATE" 2>/dev/null || echo 0)
    fi
    NOW=$(date +%s); AGE=$(( NOW - LAST )); SEND=0
    if   [ "$COUNT" -eq 0 ];                              then SEND=1   # ilk uyari
    elif [ "$COUNT" -lt 3 ] && [ "$AGE" -ge 600 ];        then SEND=1   # +10dk, +20dk
    elif [ "$COUNT" -eq 3 ] && [ "$AGE" -ge 36000 ];      then SEND=1   # +10 saat, son
    fi
    if [ "$SEND" -eq 1 ]; then
        COUNT=$(( COUNT + 1 ))
        echo "$COUNT $NOW" > "$MEM_STATE"
        if [ "$COUNT" -ge 4 ]; then
            MEM_TAIL="Hala duzelmedi. Son hatirlatma — bundan sonra susacagim."
        else
            MEM_TAIL="Dusmezse servis kendini yeniden baslatabilir."
        fi
        logger -t cmr-watchdog "bellek uyarisi #$COUNT:$OVER"
        sh "$HERE/notify.sh" "Bellek doluyor" "$OVER
$MEM_TAIL" "high" "warning" ""
    fi
fi

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
Bir sey yapmana gerek yok." \
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
Otomatik toparlama denendi, basarisiz. Sunucuya bakman gerek." \
       "urgent" "rotating_light" "fail-$STILL_HUMAN"
fi
