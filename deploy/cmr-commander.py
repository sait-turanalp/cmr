#!/usr/bin/env python3
"""Telefondaki bildirim butonundan gelen komutlari dinler ve calistirir.

NEDEN BU TASARIM (port acan bir dinleyici degil):
  - Sunucuda hicbir port acilmaz, firewall/TLS/sertifika derdi yok.
  - Caddy'ye ya da herhangi bir container'a bagimli DEGILDIR. Docker'in
    disinda, systemd servisi olarak calisir; site tamamen olu olsa bile
    buton calismaya devam eder. Baglanti giden yonde (long-poll).
  - Komut konusu, uyari konusundan AYRI bir gizli konudur: uyari konusu
    sizsa bile komut calistirilamaz.

Butonlar 'Cache: no' ile yayinlar — komut ntfy'de saklanmaz, dolayisiyla
servis yeniden basladiginda eski bir komut tekrar oynatilamaz. Ayrica
asagida zaman damgasi filtresi de var (iki kat guvenlik).
"""
import fcntl
import json
import os
import subprocess
import time
import urllib.request

ENV_FILE = os.environ.get("CMR_ENV", "/opt/cmr/.env")
APP_DIR = os.environ.get("CMR_DIR", "/opt/cmr")
NOTIFY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.sh")
COOLDOWN = 60          # ayni komut icin en az bu kadar saniye beklenir
LOCK_FILE = "/var/lock/cmr-ops.lock"   # watchdog ile paylasilir (bkz. asagi)
SERVICES = ("cmr-caddy", "cmr-frontend", "cmr-backend", "cmr-redis")
READ_TIMEOUT = 120     # ntfy ~45sn'de bir keepalive yollar; sessizlik = kopuk


def env(key):
    try:
        with open(ENV_FILE) as fh:
            for line in fh:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def notify(title, body, prio="default", tag=""):
    try:
        subprocess.run(["sh", NOTIFY, title, body, prio, tag, "", ""],
                       timeout=20, check=False)
    except Exception:
        pass


def log(msg):
    print(msg, flush=True)


def dead_services():
    out = []
    for c in SERVICES:
        p = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", c],
                           capture_output=True, text=True)
        if p.stdout.strip() != "running":
            out.append(c)
    return out


def do_restart():
    notify("Yeniden baslatiliyor", "Butona bastin. Uygulama yeniden basliyor,\n"
                                   "yaklasik 1 dakika surer.", "default", "arrows_counterclockwise")
    # Kilit: watchdog ayni anda ikinci bir "compose up" baslatmasin.
    lock = open(LOCK_FILE, "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        r = subprocess.run(["docker", "compose", "up", "-d",
                            "--force-recreate", "--remove-orphans"],
                           cwd=APP_DIR, capture_output=True, timeout=300)
        # Saglik kapilari yuzunden ayaga kalkma 30-60 sn surebilir; bekle.
        for _ in range(30):
            dead = dead_services()
            if not dead:
                break
            time.sleep(2)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    if r.returncode == 0 and not dead:
        notify("Yeniden baslatildi", "Dort servis de ayakta, site calisiyor.",
               "default", "white_check_mark")
    else:
        notify("Yeniden baslatma basarisiz",
               "Komut calisti ama servisler ayaga kalkmadi.\n"
               "Sunucuya baglanip bakman gerek.", "urgent", "rotating_light")


def do_reboot():
    # Bildirimi ONCE yolla — reboot'tan sonra sansimiz yok.
    notify("Sunucu resetleniyor", "Butona bastin. Sunucu yeniden basliyor,\n"
                                  "site 1-2 dakika icinde geri gelir.", "default", "arrows_counterclockwise")
    time.sleep(2)
    subprocess.run(["systemctl", "reboot"], check=False)


COMMANDS = {"restart": do_restart, "reboot": do_reboot}


def main():
    topic = env("NTFY_CMD_TOPIC")
    if not topic:
        log("NTFY_CMD_TOPIC tanimli degil — cikiliyor")
        return
    # since parametresi YOK: varsayilan davranis "sadece yeni mesajlar".
    # ("since=now" gecersiz, HTTP 400 doner — denendi.)
    url = "https://ntfy.sh/%s/json" % topic
    started = time.time()
    last_action = 0.0
    log("komut dinleyicisi basladi")

    while True:
        try:
            with urllib.request.urlopen(url, timeout=READ_TIMEOUT) as resp:
                for raw in resp:
                    try:
                        msg = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        continue
                    if msg.get("event") != "message":
                        continue
                    if msg.get("time", 0) < started:
                        continue          # servis baslamadan onceki komut: yoksay
                    cmd = (msg.get("message") or "").strip().lower()
                    fn = COMMANDS.get(cmd)
                    if not fn:
                        log("bilinmeyen komut yoksayildi: %r" % cmd[:40])
                        continue
                    now = time.time()
                    if now - last_action < COOLDOWN:
                        # Sessizce yutma: butona basan biri sonuc bekler.
                        log("soguma suresi — komut yoksayildi: %s" % cmd)
                        notify("Zaten yeniden basliyor",
                               "Az once bir yeniden baslatma basladi.\n"
                               "Bitmesini bekle, gerekirse tekrar bas.",
                               "low", "hourglass")
                        continue
                    last_action = now
                    log("komut calistiriliyor: %s" % cmd)
                    try:
                        fn()
                    except Exception as exc:
                        log("komut hatasi: %s" % exc)
        except Exception as exc:
            log("baglanti koptu (%s) — 5 sn sonra tekrar" % exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
