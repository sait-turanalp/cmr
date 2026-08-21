from flask import Flask, request, jsonify, send_file, after_this_request
import fitz
import textwrap
import io
import json
import uuid as _uuid
import re
import multiprocessing as mp
from datetime import datetime
from dotenv import load_dotenv
import os
from flask_cors import CORS
from cleanup_pdfs import start_background_cleanup
from jobs_store import get_store
import threading
import gc
import atexit
import time


def _malloc_trim():
    """glibc arena'sindaki serbest bellegi OS'a geri ver.

    PyMuPDF'in C tarafi free() cagirsa bile glibc bellegi arena'da tutuyor;
    buyuk bir isten sonra RSS 3.9 GB'da takili kaliyordu (olculdu). malloc_trim
    olmadan bellek ancak worker yenilenince (max-requests 500) donuyor.
    """
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass  # musl/alpine veya glibc disi ortamda sessizce atla


def _shutdown_watchdog():
    """gthread worker kapanirken threading._shutdown() deadlock'a girebilir.
    Bu watchdog, kapanma 5 saniyeden uzun surerse os._exit() ile zorla cikar."""
    time.sleep(5)
    os._exit(0)


def _start_shutdown_watchdog():
    t = threading.Thread(target=_shutdown_watchdog, daemon=True)
    t.start()


atexit.register(_start_shutdown_watchdog)

load_dotenv()

# Font ve input.pdf buffer'larini modul yuklenirken bir kere oku.
# preload=True ile gunicorn fork oncesi yuklenir; multiprocessing fork COW
# sayesinde child process'ler de ek RAM tuketmeden paylasir.
_normal_font_buffer = open("./fonts/normal.ttf", "rb").read()
_bold_font_buffer = open("./fonts/bold.ttf", "rb").read()
_INPUT_PDF_BYTES = open("./input.pdf", "rb").read()


def _precompute_blanked_template():
    """input.pdf'i bir kez ac, tum placeholder metinleri bul+beyazla, fontlari embed et.
    Sonraki her edit_pdf cagrisi search+redact adimlarini atlar: ~138ms/sayfa kazanim."""
    # _build_replacements burada henuz tanimli degil, placeholder metinleri direkt listele.
    targets = [
        "RUSYA", "MARDIN / TURKIYE",
        "ERTAŞ GRUP TARIM SANAYİ VE TİCARET LİMİTED",
        "İSKENDERUN", "SULEYMANIYAH / IRAK", "MEHMET MEHMET",
        "34KA4273", "73AAD890", "19.12.2024", "122", "KAP",
        "Ekmeklik Buğday", "26660", "100199", "$0,262862",
        "$7.007,91", "810,08", "GIB2024000000057",
        "QAIWAN FOR FOODSTUFFS MANUFACTURING", "13",
    ]
    pdf = fitz.open(stream=_INPUT_PDF_BYTES, filetype="pdf")
    page = pdf[0]
    coords = {}
    for text in targets:
        rects = page.search_for(text)
        if rects:
            r = rects[0]
            coords[text] = (r.x0, r.y0 + 10.5 if r.y0 >= 0 else r.y0 - 8.1, r)
            page.add_redact_annot(fitz.Rect(r.x0, r.y0 + 2, r.x1, r.y1 - 2), fill=(1, 1, 1))
    page.apply_redactions()
    page.insert_font(fontname="normal", fontbuffer=_normal_font_buffer)
    page.insert_font(fontname="bold", fontbuffer=_bold_font_buffer)
    blanked = pdf.write()
    pdf.close()
    return blanked, coords


_BLANKED_PDF_BYTES, _TEMPLATE_COORDS = _precompute_blanked_template()

CORS_DOMAIN = os.getenv('CORS_DOMAIN', 'http://localhost:3000')
API_KEY = os.getenv('API_KEY', 'your-secret-api-key')
OUTPUT_DIR = "outputs"
MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB
GC_EVERY_N_PAGES = 10

# Paralel PDF uretme kontrolleri (10x hizlanma icin)
PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "4"))
PARALLEL_MIN_ROWS = int(os.getenv("PARALLEL_MIN_ROWS", "100"))
# Cok yuksek row sayilari icin sert limit. 5k+ istekler tek conteynirde
# OOM yapar cunku her satir ~1MB. Uzerini client'a onay mesajiyla yonlendir.
MAX_ROWS_PER_REQUEST = int(os.getenv("MAX_ROWS_PER_REQUEST", "2000"))
# Ayni anda kabul edilen en fazla is. Asilirsa 503 — kuyruga alip herkesi
# bekletmek yerine acikca reddediyoruz (RAM ve fork sayisi ust siniri).
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "8"))
# Kac satirda bir cekirdek payi yeniden hesaplanir. Kucuk = daha adil ama
# daha cok pool yeniden kurulumu (~50ms fork). 40 iyi denge.
REBALANCE_EVERY_ROWS = int(os.getenv("REBALANCE_EVERY_ROWS", "40"))


def _worker_share(active_jobs: int) -> int:
    """Cekirdek butcesini aktif isler arasinda paylastir (weighted fair share).

    Amac: 2. kullanici geldiginde ikisinin de fork havuzu acip 4 cekirdegi
    asiri abone etmesini onlemek. Herkes hemen basliyor, sadece payi kuculuyor
    — kimse kuyrukta beklemiyor.

        1 is  -> 3 worker    2 is -> 2'ser    3+ is -> 1'er
    """
    if active_jobs <= 1:
        return PARALLEL_WORKERS
    return max(1, round(PARALLEL_WORKERS / active_jobs))

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

start_background_cleanup()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_BODY_BYTES
CORS(app, resources={r"/*": {"origins": "*"}})

key_map = {
    'Menşei:': 'ORIGIN_VAR',
    'Gönderen Adres / Exporter Adress': 'EXPORTER_ADDRESS_VAR',
    'Alıcı Adresi / Consignee Adress': 'PLACE_OF_DELIVERY_VAR',
    'DATE:': 'DATE_VAR',
    'CMR NO:': 'CMR_NO_VAR',
    'ALICI / CONSIGNEE': 'CONSIGNEE_VAR',
    'Yükleme Yeri / Place Of Loading': 'PLACE_DATE_OF_LOADING_VAR',
    'Gönderildiği Yer: ': 'PLACE_OF_DELIVERY_VAR',
    'ARAÇ PLAKA NO:': 'CAR_PLATE_VAR',
    'Truck Plate NO': 'TRUCK_PLATE_VAR',
    'Malın Cinsi:': 'DESCRIPTION_VAR',
    'Brüt KG': 'GROSS_WEIGHT_VAR',
    'DEĞER / VALUE': 'VALUE_VAR',
    'Birim Fiyat': 'UNIT_PRICE_VAR',
    'Toplam Miktar': 'TOTAL_QUANTITY_VAR',
    'Fatura No': 'INVOICE_NO_VAR',
    'ŞOFÖR ADI:': 'DRIVER_VAR',
    'Adet:': 'QUANTITY_VAR',
    'Ambalaj:': 'PACKING_VAR',
    'Marka ve No:': 'MARK_NO_VAR',
    'GÖNDEREN / EXPORTER': 'EXPORTER_VAR',
}


def save_to_local_storage(file_bytes, filename):
    try:
        file_path = os.path.join(OUTPUT_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        return True
    except Exception as e:
        print(f"File Save Error: {e}")
        return False


def format_date(date_string):
    try:
        date_obj = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%fZ")
        return date_obj.strftime("%d/%m/%Y")
    except ValueError:
        return date_string


def edit_pdf(replacements: dict, page_index: int = 0):
    """_BLANKED_PDF_BYTES (startup'ta olusturulan pre-blanked template) uzerinden
    calisir. search_for + apply_redactions adimlarini atlar (~138ms/sayfa kazanim)."""
    pdf_document = fitz.open(stream=_BLANKED_PDF_BYTES, filetype="pdf")
    try:
        page = pdf_document[0]
        # Fontlar blanked template'e embed edildi ama alias (normal/bold) runtime'da
        # yeniden kaydedilmeli; font verisi zaten dosyada oldugu icin bu sadece alias.
        page.insert_font(fontname="normal", fontbuffer=_normal_font_buffer)
        page.insert_font(fontname="bold", fontbuffer=_bold_font_buffer)

        for text_to_replace, replacement_info in replacements.items():
            coord = _TEMPLATE_COORDS.get(text_to_replace)
            if coord is None:
                continue
            x0, y_off, _ = coord
            text = replacement_info["text"]
            fontname = replacement_info.get("fontname", "normal")
            fontsize = replacement_info.get("fontsize", 12)
            wrap = replacement_info.get("wrap", False)
            wrap_width = replacement_info.get("wrap_width", 25)
            if wrap:
                wrapped_text = textwrap.fill(text, width=wrap_width, break_long_words=False)
                for i, line in enumerate(wrapped_text.split('\n')):
                    y_line = y_off + (i * (fontsize + 2))
                    page.insert_text((x0, y_line), line, fontname=fontname, fontsize=fontsize, color=(0, 0, 0))
            else:
                page.insert_text((x0, y_off), text, fontname=fontname, fontsize=fontsize, color=(0, 0, 0))

        pdf_bytes = pdf_document.write()
        return io.BytesIO(pdf_bytes)
    finally:
        pdf_document.close()
        if page_index and (page_index % GC_EVERY_N_PAGES == 0):
            try:
                fitz.TOOLS.store_shrink(100)
            except Exception:
                pass
            gc.collect()


def _build_replacements(entry: dict, currency: str) -> dict:
    """Bir CMR satirini input.pdf'teki hedef metinlere esler."""
    return {
        "RUSYA": {"text": entry.get("ORIGIN_VAR", "N/A"), "fontname": "bold", "fontsize": 12, "wrap": True, "wrap_width": 25},
        "MARDIN / TURKIYE": {"text": entry.get("EXPORTER_ADDRESS_VAR", "N/A"), "fontname": "normal", "fontsize": 12, "wrap": True, "wrap_width": 25},
        "ERTAŞ GRUP TARIM SANAYİ VE TİCARET LİMİTED": {"text": entry.get("EXPORTER_VAR", "N/A"), "fontname": "normal", "fontsize": 11, "wrap": True, "wrap_width": 42},
        "İSKENDERUN": {"text": entry.get("PLACE_DATE_OF_LOADING_VAR", "N/A"), "fontname": "normal", "fontsize": 11},
        "SULEYMANIYAH / IRAK": {"text": entry.get("PLACE_OF_DELIVERY_VAR", "N/A"), "fontname": "normal", "fontsize": 12},
        "MEHMET MEHMET": {"text": entry.get("DRIVER_VAR", "N/A"), "fontname": "normal", "fontsize": 12, "wrap": True, "wrap_width": 25},
        "34KA4273": {"text": entry.get("CAR_PLATE_VAR", "N/A"), "fontname": "normal", "fontsize": 12},
        "73AAD890": {"text": entry.get("TRUCK_PLATE_VAR", "N/A"), "fontname": "normal", "fontsize": 12},
        "19.12.2024": {"text": format_date(entry.get("DATE_VAR", "N/A")), "fontname": "normal", "fontsize": 12},
        "122": {"text": entry.get("CMR_NO_VAR", "N/A"), "fontname": "normal", "fontsize": 12},
        "KAP": {"text": entry.get("PACKING_VAR", "N/A"), "fontname": "bold", "fontsize": 12, "wrap": True, "wrap_width": 6},
        "Ekmeklik Buğday": {"text": entry.get("DESCRIPTION_VAR", "N/A"), "fontname": "bold", "fontsize": 12, "wrap": True, "wrap_width": 25},
        "26660": {"text": entry.get("GROSS_WEIGHT_VAR", "N/A"), "fontname": "bold", "fontsize": 12},
        "100199": {"text": entry.get("MARK_NO_VAR", "N/A"), "fontname": "bold", "fontsize": 12},
        "$0,262862": {"text": entry.get("UNIT_PRICE_VAR", "N/A"), "fontname": "bold", "fontsize": 11},
        "$7.007,91": {"text": f"{entry.get('VALUE_VAR', 'N/A')} {currency}", "fontname": "normal", "fontsize": 12},
        "810,08": {"text": entry.get("TOTAL_QUANTITY_VAR", "N/A"), "fontname": "bold", "fontsize": 11},
        "GIB2024000000057": {"text": entry.get("INVOICE_NO_VAR", "N/A"), "fontname": "bold", "fontsize": 10},
        "QAIWAN FOR FOODSTUFFS MANUFACTURING": {"text": entry.get("CONSIGNEE_VAR", "N/A"), "fontname": "normal", "fontsize": 11, "wrap": True, "wrap_width": 35},
        "13": {"text": entry.get("QUANTITY_VAR", "N/A"), "fontname": "bold", "fontsize": 12, "wrap": True, "wrap_width": 25},
    }


def _render_row(arg):
    """multiprocessing.Pool icinde child process'te calisir. Module-level
    olmali ki pickle edilebilsin. fork COW ile _INPUT_PDF_BYTES + font buffer'lari
    parent'tan miras alir."""
    entry, currency, idx = arg
    replacements = _build_replacements(entry, currency)
    bio = edit_pdf(replacements, page_index=idx)
    return bio.getvalue()


def merge_pdfs(pdf_list):
    merged_pdf = fitz.open()
    try:
        for pdf in pdf_list:
            pdf.seek(0)
            src = fitz.open(stream=pdf.read(), filetype="pdf")
            try:
                merged_pdf.insert_pdf(src)
            finally:
                src.close()

        merged_pdf_bytes = io.BytesIO()
        # Sikistirma + duplicate font/object temizligi.
        # 182 sayfalik CMR icin ~188MB -> ~15-25MB'e dusurur.
        #   deflate=True         : tum stream'leri zlib ile sikistir
        #   deflate_images=True  : image stream'lerini sikistir
        #   deflate_fonts=True   : font stream'lerini sikistir
        #   garbage=4            : unreferenced object'leri temizle (duplicate fontlar)
        #   use_objstms=1        : object stream'ler (daha kompakt xref)
        merged_pdf.save(
            merged_pdf_bytes,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            garbage=4,
            clean=True,
            use_objstms=1,
        )
        merged_pdf_bytes.seek(0)
        return merged_pdf_bytes
    finally:
        merged_pdf.close()
        for pdf in pdf_list:
            try:
                pdf.close()
            except Exception:
                pass


@app.route('/health', methods=['GET'])
def health_check():
    try:
        store = get_store()
        if hasattr(store, '_redis'):
            store._redis.ping()
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503
    return jsonify({"status": "ok"}), 200


# Download endpoint: public (auth yok). Rastgele token + zaman ile uretilmis
# dosya adi tahmin direncine sahiptir. Path traversal icin strict regex.
_SAFE_FILENAME_RE = re.compile(r'^out_[\w\-.]+_[a-f0-9]{8}\.pdf$')


@app.route('/api/active', methods=['GET'])
def api_active():
    """Anlik yuk. Frontend rozeti bunu okur.

    Auth istemez: sadece sayac doner, veri sizdirmaz ve rozetin her
    yuklemede calismasi gerekiyor.
    """
    try:
        n = get_store().active_count()
    except Exception:
        n = 0
    return jsonify({
        "active_jobs": n,
        "worker_share": _worker_share(max(1, n)),
        "max_workers": PARALLEL_WORKERS,
        "capacity": MAX_CONCURRENT_JOBS,
    })


@app.route('/api/download/<path:filename>', methods=['GET'])
def download_pdf(filename):
    # Path traversal / injection korumasi
    if not _SAFE_FILENAME_RE.match(filename):
        return jsonify({"error": "invalid filename"}), 400
    file_path = os.path.join(OUTPUT_DIR, filename)
    # os.path.abspath ile OUTPUT_DIR disi yolu tamamen blokla
    real = os.path.realpath(file_path)
    base = os.path.realpath(OUTPUT_DIR)
    if not real.startswith(base + os.sep):
        return jsonify({"error": "forbidden"}), 403
    if not os.path.exists(real):
        return jsonify({"error": "not found"}), 404
    response = send_file(real, as_attachment=True, download_name=filename, mimetype="application/pdf")
    # Tek kullanimlik: indirme bitince diskten sil. Kullanici uretip indiriyor,
    # sunucuda tutmanin degeri yok. POSIX'te acik fd varken os.remove guvenli —
    # inode stream bitene kadar yasar, sonra gercekten silinir.
    # (cleanup_pdfs thread'i yine de duruyor: indirilmeden birakilanlar icin.)
    @after_this_request
    def _drop(resp):
        try:
            os.remove(real)
        except OSError:
            pass
        return resp

    response.headers["Cache-Control"] = "no-store"
    return response


@app.route('/process-pdf', methods=['POST', 'OPTIONS'])
def api_process_pdf():
    if request.method == 'OPTIONS':
        return '', 200

    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    job_id = None
    store = get_store()
    T = {"start": time.time()}
    try:
        data = request.get_json()
        body_data = data.get('data', [])
        currency = data.get('currency', '$')
        mode = data.get('mode', 'normal')  # 'turbo' | 'normal'
        req_min_rows = PARALLEL_MIN_ROWS if mode == 'turbo' else 9999

        if not isinstance(body_data, list):
            return jsonify({'error': 'Expected an array of items.'}), 400

        # Bos liste: PyMuPDF 'cannot save with zero pages' ile 500 sizdiriyordu.
        if len(body_data) == 0:
            return jsonify({'error': 'Dosyada islenecek satir bulunamadi.'}), 400

        # Kabul kontrolu — job yaratmadan ONCE. Tavani asarsak acikca reddet.
        if store.active_count() >= MAX_CONCURRENT_JOBS:
            return jsonify({
                'error': 'Sistem su an yogun. Lutfen birkac saniye sonra tekrar deneyin.',
                'busy': True,
                'active_jobs': MAX_CONCURRENT_JOBS,
            }), 503

        if len(body_data) > MAX_ROWS_PER_REQUEST:
            return jsonify({
                'error': f'Cok fazla satir: {len(body_data)}. Tek istekte en fazla {MAX_ROWS_PER_REQUEST} satir islenebilir. Dosyayi bolerek gonderin.',
                'max_rows': MAX_ROWS_PER_REQUEST,
                'received': len(body_data),
            }), 413

        # Progress total'i save+deflate fazi icin ek slot icerir.
        # render ~%90'a kadar gider; kalan %10 save+download icin rezerve.
        n_rows = len(body_data)
        save_reserve = max(int(n_rows * 0.1), 5)
        progress_total = n_rows + save_reserve
        job_id = store.new_job(total=progress_total)

        # Payi job KAYDEDILDIKTEN sonra hesapla: kendimiz de sayilalim ki
        # es zamanli iki istek birbirini gormeden tam pay almasin.
        active_jobs = max(1, store.active_count())
        req_workers = _worker_share(active_jobs) if mode == 'turbo' else 1

        transformed_data = []
        for item in body_data:
            transformed_item = {}
            for key, value in item.items():
                new_key = key_map.get(key)
                if new_key:
                    if isinstance(value, dict) and 'result' in value:
                        transformed_item[new_key] = f"{value['result']:.2f}"
                    else:
                        transformed_item[new_key] = str(value)
            transformed_data.append(transformed_item)

        n = len(transformed_data)
        use_parallel = req_workers > 1 and n >= req_min_rows
        T["transform"] = time.time()

        # Streaming merge: sayfa bytes'larini toplu bir liste tutmak yerine,
        # geldikce dogrudan merged_pdf'e ekle ve bytes'i cope at. 5000+ satirda
        # tek worker'da ~5GB RAM birikmesini (OOM -> SIGKILL) onler.
        merged_pdf = fitz.open()
        progress_step = max(1, n // 100)

        def _consume(idx, pdf_bytes):
            src = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                merged_pdf.insert_pdf(src)
            finally:
                src.close()
            if idx == n or idx % progress_step == 0:
                store.update(job_id, idx)

        if use_parallel:
            ctx = mp.get_context("fork")
            all_args = [(entry, currency, idx) for idx, entry in enumerate(transformed_data, start=1)]
            done = 0
            cur_share = req_workers
            pool = None
            try:
                while done < n:
                    # Payi HER DILIMDE yeniden degerlendir: baska bir is bittiginde
                    # bosalan cekirdekler hemen kalanlara dagilir. Sabit paylasimda
                    # son gelen is 1 worker'da kilitli kaliyordu (olculdu: 4 kisilik
                    # testte en yavas/en hizli farki 1.94x).
                    share = _worker_share(max(1, store.active_count())) if mode == 'turbo' else 1
                    if pool is None or share != cur_share:
                        if pool is not None:
                            pool.terminate()
                            pool.join()
                        cur_share = share
                        pool = ctx.Pool(processes=cur_share)
                    slice_args = all_args[done:done + REBALANCE_EVERY_ROWS]
                    # chunksize dengesi: cok kucuk -> IPC overhead; cok buyuk ->
                    # parent buffer sismesi (OOM riski). max 16 iyi balans.
                    chunksize = max(1, min(16, len(slice_args) // (cur_share * 8)))
                    for pdf_bytes in pool.imap(_render_row, slice_args, chunksize=chunksize):
                        done += 1
                        _consume(done, pdf_bytes)
                        del pdf_bytes
            finally:
                if pool is not None:
                    pool.terminate()
                    pool.join()
        else:
            for idx, entry in enumerate(transformed_data, start=1):
                replacements = _build_replacements(entry, currency)
                edited_pdf = edit_pdf(replacements, page_index=idx)
                try:
                    _consume(idx, edited_pdf.getvalue())
                finally:
                    edited_pdf.close()
                if mode == 'normal':
                    time.sleep(0.55)  # ~1.5 sayfa/sn — turbo ile belirgin fark
        T["render"] = time.time()
        # Render bittikten sonra progress %90 civarinda kalir; save/deflate
        # surecinde frontend yanitsiz gibi gorunmesin diye burada 100%'e ceksek
        # de kullanici save biterken "100 ama bekliyor" gorurdu — bu yuzden
        # progress tam 100%'e ancak save bittikten sonra cekilir.

        # Tahmin-dirençli filename: zaman + 8 byte random token.
        current_time = datetime.now().isoformat().replace(':', '-')
        token = _uuid.uuid4().hex[:8]
        file_name = f"out_{current_time}_{token}.pdf"

        # Diske DOGRUDAN save — BytesIO kopya birikmesi yok.
        # 5k+ sayfalik islerde BytesIO getvalue() tekrar RAM'e ~500MB aliyordu.
        # Direkt dosyaya yazarak bu ikinci kopya elimine ediliyor.
        out_path = os.path.join(OUTPUT_DIR, file_name)
        # OLCULDU (182 sayfa, taze dokumanla her varyant):
        #   g=4 clean=1 -> 6.51s / 24.26 MB   (eski)
        #   g=4 clean=0 -> 3.30s / 23.73 MB   (bu — hem hizli hem kucuk)
        #   g=3 clean=1 -> 18.21s / 127 MB    (garbage dusurmek FELAKET)
        # garbage=4 sart: 182 sayfanin duplicate font/logo objelerini tekillestirir.
        # clean=True gereksiz: content stream rewrite, boyut kazanci yok.
        merged_pdf.save(
            out_path,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            garbage=4,
            use_objstms=1,
        )
        merged_pdf.close()
        T["save"] = time.time()
        # PDF boyutu (header icin stat)
        size_bytes = os.path.getsize(out_path)
        T["metadata"] = time.time()
        # Save bitti — simdi progress 100%'e cek
        store.update(job_id, progress_total)

        # Bytes donmek yerine URL doner: kullanici "indir" butonuna basinca
        # browser native download manager uzerinden cekilir. API yaniti milisaniye,
        # kullanici progress'i anlik 100%'e gider, buton donuk kalmaz.
        size_mb = size_bytes / 1024 / 1024
        total = time.time() - T["start"]
        # Pipeline breakdown — hangi asama ne kadar surdu (prod debug)
        _t = T
        timings = {
            "parse_transform": round(_t["transform"] - _t["start"], 2),
            "render": round(_t["render"] - _t["transform"], 2),
            "save_deflate": round(_t["save"] - _t["render"], 2),
            "db_metadata": round(_t["metadata"] - _t["save"], 2),
            "total": round(total, 2),
        }
        print(f"[TIMING] {timings} mode={mode} pages={n} workers_start={req_workers} active_start={active_jobs}", flush=True)
        return jsonify({
            "timings": timings,
            "workers_used": req_workers,
            "rebalanced": True,
            "active_jobs_at_start": active_jobs,
            "filename": file_name,
            "download_url": f"/api/download/{file_name}",
            "size_mb": round(size_mb, 2),
            "processing_time_sec": round(total, 2),
            "pages": n,
            "job_id": job_id,
        }), 200
    except Exception as e:
        print(f"PDF Processing Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if job_id is not None:
            try:
                store.finish(job_id)
            except Exception:
                pass
        try:
            fitz.TOOLS.store_shrink(100)
        except Exception:
            pass
        gc.collect()
        _malloc_trim()


@app.route('/api/progress', methods=['GET', 'OPTIONS'])
def get_progress():
    if request.method == 'OPTIONS':
        return '', 200
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    store = get_store()
    job_id = request.args.get("job_id")
    if job_id:
        j = store.get(job_id)
        if not j:
            return jsonify({"current": 0, "total": 0, "unknown": True})
        return jsonify({"current": j["current"], "total": j["total"], "finished": j.get("finished", False)})

    # Idle: aktif job yoksa finished'in 100%'ini gosterme (yeni kullanici
    # bastirmadan once boylelikle "hemen 100" gormesin). Sadece canli job'u rapor et.
    rep = store.representative()
    if not rep:
        return jsonify({"current": 0, "total": 0})
    jid, j = rep
    if j.get("finished"):
        return jsonify({"current": 0, "total": 0})
    return jsonify({"current": j["current"], "total": j["total"]})


@app.route('/api/isfree', methods=['GET', 'OPTIONS'])
def get_isfree():
    if request.method == 'OPTIONS':
        return '', 200
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    # Info-only: multi-worker + async download ile 429 blok mantigi kalktı.
    # Frontend'e 200 doneriz, isteyen client rakam icin kullanir.
    store = get_store()
    return jsonify({"is_processing": store.any_active()}), 200


if __name__ == '__main__':
    app.run(port=5001)
