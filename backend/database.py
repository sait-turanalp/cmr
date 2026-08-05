import sqlite3
import os
import threading

DB_NAME = "local_data.db"

# Concurrent write support icin WAL modu + busy_timeout.
# WAL: reader'lar writer'i blocklamaz, writer'lar arasi sira gelir.
# busy_timeout: 5 saniye lock bekle, sonra hata at.
_init_lock = threading.Lock()
_initialized = False


def _apply_pragmas(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")  # WAL ile birlikte guvenli
    conn.execute("PRAGMA foreign_keys=ON;")


def get_db_connection():
    # Her thread kendi bagiantisini kullanir (sqlite3 thread-safety mode)
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def init_db():
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = get_db_connection()
        try:
            c = conn.cursor()
            # NOT: 'files' tablosu kaldirildi — her PDF uretiminde tum satirlarin
            # JSON'unu yaziyordu ama hicbir yer okumuyordu. PDF zaten indirilince
            # siliniyor; veriyi tutmanin degeri yok.
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            ''')
            conn.commit()
            _initialized = True
        finally:
            conn.close()


# Ensure DB is created on import
if not os.path.exists(DB_NAME):
    init_db()
else:
    # Mevcut DB'ye WAL pragmalarini uygula (ilk calistirma WAL degilse gecir)
    init_db()
