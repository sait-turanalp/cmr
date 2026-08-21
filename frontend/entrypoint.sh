#!/bin/sh
# Kendi kendini iyilestiren baslatici.
#
# NEDEN: autoheal (harici izleyici) bir kez "restart failed" verdi, container'i
# durdurup baslatamadi ve site 17 saat olu kaldi (19-08-2026 15:47). Docker'in
# restart:always politikasi devreye girmedi cunku API'den durdurulan container
# manuel mudahale sayilir. Cozum: harici izleyiciye guvenme — container saglik
# kaybederse KENDINI oldursun, restart:always onu kaldirsin.

cleanup() {
    echo "[entrypoint] kapanma sinyali, next.js durduruluyor..."
    kill -TERM $PID 2>/dev/null
    wait $PID 2>/dev/null
    exit 0
}
trap cleanup TERM INT QUIT

node server.js &
PID=$!
sleep 8

FAIL_COUNT=0
MAX_FAILS=5   # 5 x 30sn = 2.5 dk kesintisiz sagliksizlik

echo "[entrypoint] saglik izleme basladi (PID: $PID)"

while true; do
    sleep 30

    if ! kill -0 $PID 2>/dev/null; then
        echo "[entrypoint] next.js sureci oldu, container cikiyor"
        exit 1
    fi

    # DIKKAT: http.get'in 'timeout' secenegi istegi IPTAL ETMEZ, sadece socket
    # zamanlayicisini kurar. Donmus (SIGSTOP) bir surecte istek asili kalir ve
    # bu dongu hic ilerlemez — battle test'te tam bu yasandi. Bu yuzden hem
    # req.destroy() hem de kesin bir setTimeout+exit koyuldu.
    if node -e "
const http=require('http');
const t=setTimeout(()=>process.exit(1),8000);
const req=http.get({host:'127.0.0.1',port:3000,path:'/'},r=>{clearTimeout(t);r.resume();process.exit(r.statusCode<500?0:1);});
req.setTimeout(7000,()=>{req.destroy();process.exit(1);});
req.on('error',()=>{clearTimeout(t);process.exit(1);});
" 2>/dev/null; then
        FAIL_COUNT=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[entrypoint] saglik kontrolu basarisiz ($FAIL_COUNT/$MAX_FAILS)"
        if [ "$FAIL_COUNT" -ge "$MAX_FAILS" ]; then
            echo "[entrypoint] $MAX_FAILS kez basarisiz, container oldurulyor (Docker yeniden baslatacak)"
            kill -9 $PID 2>/dev/null
            wait $PID 2>/dev/null
            exit 1
        fi
    fi
done
