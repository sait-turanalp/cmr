#!/bin/sh
# ntfy.sh uzerinden bildirim gonderir. Kayit/token gerektirmez.
#
# Konu adi /opt/cmr/.env icindeki NTFY_TOPIC'ten okunur. Konu adi gizli bir
# parola gibidir — bilen herkes mesajlari okuyabilir, o yuzden rastgele uretildi.
#
# Kullanim: notify.sh "baslik" "mesaj" [oncelik]
# Bildirim ASLA cagiran isi bloklamaz: kisa timeout + hata yutulur.

ENV_FILE="${CMR_ENV:-/opt/cmr/.env}"
[ -f "$ENV_FILE" ] && NTFY_TOPIC=$(grep -E '^NTFY_TOPIC=' "$ENV_FILE" | cut -d= -f2-)
[ -z "$NTFY_TOPIC" ] && exit 0     # yapilandirilmamissa sessizce cik

TITLE="${1:-CMR}"
BODY="${2:-}"
PRIO="${3:-default}"

curl -fsS --max-time 8 \
     -H "Title: $TITLE" \
     -H "Priority: $PRIO" \
     -H "Tags: package" \
     -d "$BODY" \
     "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
exit 0
