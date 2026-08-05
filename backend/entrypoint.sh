#!/bin/sh

cleanup() {
    echo "[entrypoint] Shutdown signal received, stopping gunicorn..."
    kill -TERM $PID 2>/dev/null
    wait $PID 2>/dev/null
    exit 0
}
trap cleanup TERM INT QUIT

# Gunicorn: 4 worker (process) x 4 thread = 16 concurrent request.
# Multi-process CPython GIL'i kirar -> gercek multi-core kullanilir.
# Progress Redis'te paylasildigi icin worker'lar arasi state sorunu yok.
# preload: font+input.pdf fork oncesi yuklenir; Redis client lazy, fork-safe.
WORKERS=${GUNICORN_WORKERS:-2}
THREADS=${GUNICORN_THREADS:-8}
TIMEOUT=${GUNICORN_TIMEOUT:-600}

echo "[entrypoint] starting gunicorn: workers=${WORKERS} threads=${THREADS} timeout=${TIMEOUT}"

gunicorn \
    --bind 0.0.0.0:5001 \
    --workers ${WORKERS} \
    --threads ${THREADS} \
    --worker-class gthread \
    --timeout ${TIMEOUT} \
    --graceful-timeout 30 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --worker-tmp-dir /dev/shm \
    --preload \
    app:app &

PID=$!

sleep 5

FAIL_COUNT=0
MAX_FAILS=5

echo "[entrypoint] Health monitoring started (PID: $PID)"

while true; do
    sleep 30

    if ! kill -0 $PID 2>/dev/null; then
        echo "[entrypoint] Gunicorn process died, exiting container"
        exit 1
    fi

    if python3 -c "
import urllib.request
try:
    urllib.request.urlopen('http://localhost:5001/health', timeout=10)
except Exception:
    exit(1)
" 2>/dev/null; then
        FAIL_COUNT=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[entrypoint] Health check failed ($FAIL_COUNT/$MAX_FAILS)"

        if [ "$FAIL_COUNT" -ge "$MAX_FAILS" ]; then
            echo "[entrypoint] Health check failed $MAX_FAILS times, killing container"
            kill -9 $PID 2>/dev/null
            wait $PID 2>/dev/null
            exit 1
        fi
    fi
done
