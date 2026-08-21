#!/bin/sh
# ntfy.sh bildirimi. Kayit/token gerektirmez.
#
# Kullanim: notify.sh <baslik> <mesaj> [oncelik] [etiket] [susturma-anahtari]
#
# TASARIM KARARLARI:
# - Kilit ekraninda ilk birkac kelime disinda cok az sey okunur; BASLIK tek
#   basina durumu anlatir, govde kisa bir detaydir.
# - 'Click' basligi KULLANILMAZ: boylece bildirime dokununca ntfy uygulamasi
#   mesaj detayini acar (butonlar ve tam metin orada gorunur). Siteye gitmek
#   isteyen icin ayri bir buton var.
# - Markdown KULLANILMAZ: ntfy dokumanina gore markdown "web app only for now"
#   — iOS/Android uygulamasinda **kalin** isaretleri ham gorunur. Onun yerine
#   ciplak URL yaziyoruz; mobil uygulama onlari otomatik tiklanabilir yapar.
# - Susturma: ayni sorun icin 30 dk'da bir kez. Surekli coken bir sistem
#   yoksa telefonu dakikada bir bombalar.

ENV_FILE="${CMR_ENV:-/opt/cmr/.env}"
[ -f "$ENV_FILE" ] && NTFY_TOPIC=$(grep -E '^NTFY_TOPIC=' "$ENV_FILE" | cut -d= -f2-)
[ -z "$NTFY_TOPIC" ] && exit 0

SITE="${PUBLIC_URL:-https://yedek.opik.online}"
TITLE="${1:-CMR}"
BODY="${2:-}"
PRIO="${3:-default}"
TAGS="${4:-}"
MUTE_KEY="${5:-}"

if [ -n "$MUTE_KEY" ]; then
    STAMP="/tmp/.cmr-notify-$(echo "$MUTE_KEY" | tr -c 'a-zA-Z0-9' '_')"
    if [ -f "$STAMP" ]; then
        AGE=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
        [ "$AGE" -lt 1800 ] && exit 0
    fi
    touch "$STAMP"
fi

curl -fsS --max-time 8 \
     -H "Title: $TITLE" \
     -H "Priority: $PRIO" \
     ${TAGS:+-H "Tags: $TAGS"} \
     -H "Actions: view, Siteyi ac, $SITE, clear=true" \
     -d "$BODY" \
     "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
exit 0
