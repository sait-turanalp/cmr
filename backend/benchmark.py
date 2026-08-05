"""
CMR PDF üretim benchmark: v1 (sequential) vs v2 (parallel + tmpfs IPC)

Kullanım:
  cd cmr/backend
  source venv/bin/activate
  python benchmark.py /path/to/file.xlsx [workers]

Varsayılan workers = CPU sayısı.
"""
import sys
import os
import time
import io
import multiprocessing
import importlib.util
import tempfile

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JOBS_BACKEND", "memory")  # Redis gerekmeden çalışır
os.environ.setdefault("PDF_MAX_AGE_HOURS", "2")

XLSX_PATH = sys.argv[1] if len(sys.argv) > 1 else None
if not XLSX_PATH:
    print("Kullanım: python benchmark.py /path/to/file.xlsx [workers]")
    sys.exit(1)

N_WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else multiprocessing.cpu_count()


# ── Veri yükle ──────────────────────────────────────────────────────────────
import openpyxl
wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
headers = [str(c).strip() if c is not None else "" for c in rows[0]]
data_rows = rows[1:]
currency = "USD"

transformed_data = []
for row in data_rows:
    item = {headers[i]: (str(row[i]).strip() if row[i] is not None else "") for i in range(len(headers))}
    transformed_data.append(item)

wb.close()
N = len(transformed_data)
print(f"Satır sayısı: {N}  |  Workers: {N_WORKERS}  |  CPU: {multiprocessing.cpu_count()}")
print()


# ── app modülünü import et (flask init olmadan) ──────────────────────────────
# Doğrudan fonksiyonları import ediyoruz
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import fitz
import app as app_v1
import app_v2 as app_v2_mod


def run_sequential(mod, data, label):
    """PARALLEL_WORKERS=1 yolu: her satır sırayla işlenir."""
    t0 = time.perf_counter()
    merged = fitz.open()
    for idx, entry in enumerate(data, start=1):
        replacements = mod._build_replacements(entry, currency)
        bio = mod.edit_pdf(replacements, page_index=idx)
        src = fitz.open(stream=bio.getvalue(), filetype="pdf")
        merged.insert_pdf(src)
        src.close()
        bio.close()
    out = io.BytesIO()
    merged.save(out, deflate=True, deflate_images=True, deflate_fonts=True, garbage=4, clean=True, use_objstms=1)
    merged.close()
    elapsed = time.perf_counter() - t0
    size_mb = out.tell() / 1024 / 1024
    print(f"  {label:30s}  {elapsed:6.2f}s  {N/elapsed:5.1f} sayfa/s  {size_mb:.1f} MB")
    return elapsed


def run_parallel_v1(data, workers, label):
    """v1 parallel: IPC üzerinden bytes döner."""
    import app as mod
    t0 = time.perf_counter()
    ctx = multiprocessing.get_context("fork")
    args = [(entry, currency, idx) for idx, entry in enumerate(data, start=1)]
    chunksize = max(1, min(16, N // (workers * 8)))
    merged = fitz.open()
    with ctx.Pool(processes=workers) as pool:
        for pdf_bytes in pool.imap(mod._render_row, args, chunksize=chunksize):
            src = fitz.open(stream=pdf_bytes, filetype="pdf")
            merged.insert_pdf(src)
            src.close()
            del pdf_bytes
    out = io.BytesIO()
    merged.save(out, deflate=True, deflate_images=True, deflate_fonts=True, garbage=4, clean=True, use_objstms=1)
    merged.close()
    elapsed = time.perf_counter() - t0
    size_mb = out.tell() / 1024 / 1024
    print(f"  {label:30s}  {elapsed:6.2f}s  {N/elapsed:5.1f} sayfa/s  {size_mb:.1f} MB")
    return elapsed


def run_parallel_v2(data, workers, label):
    """v2 parallel: tmpfs path döner, IPC minimal."""
    import app_v2 as mod
    t0 = time.perf_counter()
    ctx = multiprocessing.get_context("fork")
    args = [(entry, currency, idx) for idx, entry in enumerate(data, start=1)]
    merged = fitz.open()
    with ctx.Pool(processes=workers) as pool:
        for tmp_path in pool.imap(mod._render_row_v2, args, chunksize=4):
            try:
                src = fitz.open(tmp_path)
                merged.insert_pdf(src)
                src.close()
            finally:
                os.unlink(tmp_path)
    out = io.BytesIO()
    merged.save(out, deflate=True, deflate_images=True, deflate_fonts=True, garbage=4, clean=True, use_objstms=1)
    merged.close()
    elapsed = time.perf_counter() - t0
    size_mb = out.tell() / 1024 / 1024
    print(f"  {label:30s}  {elapsed:6.2f}s  {N/elapsed:5.1f} sayfa/s  {size_mb:.1f} MB")
    return elapsed


# ── Benchmark ────────────────────────────────────────────────────────────────
print("=" * 65)
print(f"{'Mod':<30}  {'Süre':>6}  {'Hız':>10}  {'Boyut':>7}")
print("=" * 65)

t_seq  = run_sequential(app_v1,  transformed_data, f"v1  sequential (1 worker)")
t_p1   = run_parallel_v1(transformed_data, N_WORKERS, f"v1  parallel  ({N_WORKERS} workers, IPC bytes)")
t_p2   = run_parallel_v2(transformed_data, N_WORKERS, f"v2  parallel  ({N_WORKERS} workers, tmpfs)")

print("=" * 65)
print()
print("Özet:")
print(f"  v1 sequential → baseline")
print(f"  v1 parallel   → {t_seq/t_p1:+.1f}x  ({'hızlı' if t_p1 < t_seq else 'YAVAŞ — IPC overhead'})")
print(f"  v2 parallel   → {t_seq/t_p2:+.1f}x  ({'hızlı' if t_p2 < t_seq else 'YAVAŞ'})")
print(f"  v2 vs v1 parallel kazanım: {(t_p1-t_p2)/t_p1*100:.0f}%")
