#!/usr/bin/env python3
"""
Outputs/ klasorunden belirli yasin uzerindeki PDF'leri siler.
Backend app.py icinde arka plan thread olarak saatlik calisir.
"""

import os
import time
import threading
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"

# Yuksek-trafik prod icin makul defaultlar: 2 saat sonra sil, 15 dakikada bir tara.
# Her istek ~10-20MB PDF uretir; saatte 1000 istekte 15GB olusur, 2 saat retention
# disk baskisi olmadan kullanicilara download icin yeterli zaman verir.
DEFAULT_MAX_AGE_HOURS = int(os.getenv("PDF_MAX_AGE_HOURS", "2"))
DEFAULT_INTERVAL_SEC = int(os.getenv("PDF_CLEANUP_INTERVAL_SEC", "900"))


def cleanup_pdfs(max_age_hours: int = DEFAULT_MAX_AGE_HOURS) -> int:
    """max_age_hours'tan eski PDF'leri siler. Silinen dosya sayisini doner."""
    if not OUTPUTS_DIR.exists():
        return 0

    cutoff = time.time() - (max_age_hours * 3600)
    deleted = 0
    total = 0
    try:
        for f in OUTPUTS_DIR.glob("*.pdf"):
            total += 1
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception as e:
                print(f"[cleanup] delete error {f}: {e}")
    except Exception as e:
        print(f"[cleanup] scan error: {e}")

    print(f"[cleanup] scanned={total} deleted={deleted} max_age_h={max_age_hours}")
    return deleted


def _cleanup_loop(interval_sec: int, max_age_hours: int):
    # Ilk calistirmayi container basladiktan hemen sonra degil,
    # 60sn sonra yap ki startup'ta I/O yarismasi olmasin.
    time.sleep(60)
    while True:
        try:
            cleanup_pdfs(max_age_hours)
        except Exception as e:
            print(f"[cleanup] loop error: {e}")
        time.sleep(interval_sec)


def start_background_cleanup(
    interval_sec: int = DEFAULT_INTERVAL_SEC,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
):
    """Arka plan daemon thread baslatir. Birden fazla worker'da da guvenli
    cunku her worker kendi thread'ini calistirir; dosya sistemi paylasilir
    ama os.unlink idempotent."""
    t = threading.Thread(
        target=_cleanup_loop,
        args=(interval_sec, max_age_hours),
        daemon=True,
        name="pdf-cleanup",
    )
    t.start()
    print(f"[cleanup] background thread started (interval={interval_sec}s, max_age={max_age_hours}h)")


if __name__ == "__main__":
    print("Running one-shot PDF cleanup...")
    cleanup_pdfs()
