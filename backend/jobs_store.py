"""
Job progress storage. Iki backend destekler:
- redis: Multi-worker sunucularda (default). Her worker ayni Redis'e yazar.
- memory: Tek-worker veya Redis down durumunda fallback (thread-safe dict).

Env:
    JOBS_BACKEND = "redis" | "memory"  (default: redis)
    REDIS_URL    = "redis://host:6379/0"

API (her iki backend icin ayni):
    new_job(total) -> job_id
    update(job_id, current)
    finish(job_id)
    get(job_id) -> dict | None
    representative() -> (job_id, dict) | None  # V1 uyumluluk
    any_active() -> bool
"""

import os
import time
import uuid
import threading
from typing import Optional, Tuple, Dict, Any

JOB_TTL_SECONDS = 300  # finished job'lari 5 dk sakla
# Aktif bir job'in en uzun yasamasi beklenen sure. Gunicorn timeout=600s
# ile hizalanir. Bu suredeki cadan eski aktif entry orphan sayilir, temizlenir.
ACTIVE_ORPHAN_SECONDS = 900


class MemoryStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def _cleanup_locked(self, now: float):
        stale = [
            jid for jid, j in self._jobs.items()
            if j.get("finished") and j.get("finished_at") and (now - j["finished_at"]) > JOB_TTL_SECONDS
        ]
        for jid in stale:
            self._jobs.pop(jid, None)

    def new_job(self, total: int) -> str:
        jid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._jobs[jid] = {
                "current": 0,
                "total": total,
                "started_at": now,
                "finished_at": None,
                "finished": False,
            }
            self._cleanup_locked(now)
        return jid

    def update(self, job_id: str, current: int):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["current"] = current

    def finish(self, job_id: str):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["finished"] = True
                self._jobs[job_id]["finished_at"] = time.time()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

    def representative(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        with self._lock:
            active = [(jid, j) for jid, j in self._jobs.items() if not j.get("finished")]
            if active:
                active.sort(key=lambda kv: kv[1]["started_at"], reverse=True)
                return active[0][0], dict(active[0][1])
            finished = [(jid, j) for jid, j in self._jobs.items() if j.get("finished_at")]
            if finished:
                finished.sort(key=lambda kv: kv[1]["finished_at"], reverse=True)
                return finished[0][0], dict(finished[0][1])
        return None

    def any_active(self) -> bool:
        with self._lock:
            return any(not j.get("finished") for j in self._jobs.values())


class RedisStore:
    """
    Anahtar semasi:
        cmr:job:{id}           -> hash: current, total, started_at, finished_at, finished
        cmr:jobs:active        -> ZSET: jid -> started_at   (aktif joblar)
        cmr:jobs:finished      -> ZSET: jid -> finished_at  (bitmis joblar)
    """

    def __init__(self, url: str):
        import redis  # lazy import
        # decode_responses=True: string donustur, bizim icin kolay
        # connection_pool: fork-safe, her worker kendi bagiantisini acar
        self._redis = redis.from_url(url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
        self._prefix = "cmr"

    def _job_key(self, jid: str) -> str:
        return f"{self._prefix}:job:{jid}"

    def _cleanup(self, now: float):
        """Stale finished job'lari + orphan aktif entry'leri sil.

        Orphan: aktif ZSET'te duran ama hash'i expire olmus veya fazla eski
        (crash/SIGKILL sonrasi finish cagrilamadi). Bunlari birakirsak
        any_active() True doner, /api/isfree 429 gonderir, frontend dondurur.
        """
        try:
            # Finished: tamamlanmis ve TTL'i dolmus
            cutoff_finished = now - JOB_TTL_SECONDS
            stale_fin = self._redis.zrangebyscore(f"{self._prefix}:jobs:finished", 0, cutoff_finished)
            if stale_fin:
                pipe = self._redis.pipeline()
                for jid in stale_fin:
                    pipe.delete(self._job_key(jid))
                    pipe.zrem(f"{self._prefix}:jobs:finished", jid)
                pipe.execute()

            # Active orphan: cok eski VEYA hash'i kayip
            cutoff_active = now - ACTIVE_ORPHAN_SECONDS
            very_old = self._redis.zrangebyscore(f"{self._prefix}:jobs:active", 0, cutoff_active)
            if very_old:
                pipe = self._redis.pipeline()
                for jid in very_old:
                    pipe.zrem(f"{self._prefix}:jobs:active", jid)
                pipe.execute()
        except Exception as e:
            print(f"[jobs_store] cleanup error: {e}")

    def new_job(self, total: int) -> str:
        jid = uuid.uuid4().hex[:12]
        now = time.time()
        pipe = self._redis.pipeline()
        pipe.hset(self._job_key(jid), mapping={
            "current": 0,
            "total": total,
            "started_at": now,
            "finished": 0,
        })
        # Hash TTL'i aktif job + finished retention toplami kadar olmali,
        # aksi takdirde uzun isler sirasinda hash expire olur ve orphan gorunur.
        pipe.expire(self._job_key(jid), ACTIVE_ORPHAN_SECONDS + JOB_TTL_SECONDS)
        pipe.zadd(f"{self._prefix}:jobs:active", {jid: now})
        pipe.execute()
        self._cleanup(now)
        return jid

    def update(self, job_id: str, current: int):
        try:
            self._redis.hset(self._job_key(job_id), "current", current)
        except Exception as e:
            print(f"[jobs_store] update error: {e}")

    def finish(self, job_id: str):
        now = time.time()
        try:
            pipe = self._redis.pipeline()
            pipe.hset(self._job_key(job_id), mapping={"finished": 1, "finished_at": now})
            pipe.zrem(f"{self._prefix}:jobs:active", job_id)
            pipe.zadd(f"{self._prefix}:jobs:finished", {job_id: now})
            pipe.execute()
        except Exception as e:
            print(f"[jobs_store] finish error: {e}")

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            h = self._redis.hgetall(self._job_key(job_id))
            if not h:
                return None
            return {
                "current": int(h.get("current", 0)),
                "total": int(h.get("total", 0)),
                "started_at": float(h.get("started_at", 0)),
                "finished_at": float(h["finished_at"]) if h.get("finished_at") else None,
                "finished": bool(int(h.get("finished", 0))),
            }
        except Exception as e:
            print(f"[jobs_store] get error: {e}")
            return None

    def representative(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        try:
            # En son baslayan aktif. Orphan (hash yok) olanlari atla + temizle.
            active = self._redis.zrevrange(f"{self._prefix}:jobs:active", 0, 9)
            for jid in active:
                j = self.get(jid)
                if j:
                    return jid, j
                # orphan
                self._redis.zrem(f"{self._prefix}:jobs:active", jid)
            finished = self._redis.zrevrange(f"{self._prefix}:jobs:finished", 0, 0)
            if finished:
                jid = finished[0]
                j = self.get(jid)
                if j:
                    return jid, j
        except Exception as e:
            print(f"[jobs_store] representative error: {e}")
        return None

    def any_active(self) -> bool:
        """ZSET'teki aktif job'larin HASH'i da var mi kontrol eder.
        Orphan entry (hash expire olmus) sayilmaz + anlik temizlenir."""
        try:
            active_ids = self._redis.zrange(f"{self._prefix}:jobs:active", 0, -1)
            if not active_ids:
                return False
            pipe = self._redis.pipeline()
            for jid in active_ids:
                pipe.exists(self._job_key(jid))
            exists_flags = pipe.execute()
            orphans = [jid for jid, ex in zip(active_ids, exists_flags) if not ex]
            if orphans:
                cleanup_pipe = self._redis.pipeline()
                for jid in orphans:
                    cleanup_pipe.zrem(f"{self._prefix}:jobs:active", jid)
                cleanup_pipe.execute()
            return any(exists_flags)
        except Exception as e:
            print(f"[jobs_store] any_active error: {e}")
            return False


_store = None


def get_store():
    """Lazy singleton. Fork sonrasi her worker'da ilk cagrida olusur."""
    global _store
    if _store is not None:
        return _store

    backend = os.getenv("JOBS_BACKEND", "redis").lower()
    if backend == "redis":
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            rs = RedisStore(url)
            rs._redis.ping()
            _store = rs
            print(f"[jobs_store] using Redis backend ({url})")
            return _store
        except Exception as e:
            print(f"[jobs_store] Redis unavailable ({e}), falling back to memory")
    _store = MemoryStore()
    print("[jobs_store] using memory backend")
    return _store
