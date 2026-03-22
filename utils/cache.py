"""
utils/cache.py — スレッドセーフな TTL インメモリキャッシュ

エージェント設計の三層モデル（記録層）に対応：
  - 検索クエリ結果をキャッシュし、重複 API 呼び出しを削減
  - TTL で自動失効、maxsize でメモリ上限を管理

環境変数:
  CACHE_ENABLED   true/false (デフォルト: true)
  CACHE_MAX_SIZE  最大エントリ数 (デフォルト: 100)
  CACHE_TTL       有効期間秒数 (デフォルト: 3600)
"""
import time
import threading
from typing import Any, Optional

from utils.logger import log


class TTLCache:
    """スレッドセーフな TTL 付きインメモリキャッシュ。"""

    def __init__(self, maxsize: int = 100, ttl: int = 3600):
        self._store: dict = {}
        self._lock = threading.Lock()
        self.maxsize = maxsize
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            # 期限切れエントリを掃除
            if len(self._store) >= self.maxsize:
                now = time.time()
                expired = [k for k, (_, exp) in self._store.items() if now > exp]
                for k in expired:
                    del self._store[k]
                # それでも満杯なら最も早く期限切れになるエントリを削除
                if len(self._store) >= self.maxsize:
                    oldest_key = min(self._store, key=lambda k: self._store[k][1])
                    del self._store[oldest_key]
            expire_at = time.time() + (ttl if ttl is not None else self.ttl)
            self._store[key] = (value, expire_at)

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            alive = sum(1 for _, (_, exp) in self._store.items() if now <= exp)
            return {"total": len(self._store), "alive": alive, "maxsize": self.maxsize, "ttl": self.ttl}

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# ────────────────────────────────────────────────────────────────
#  グローバルシングルトン
# ────────────────────────────────────────────────────────────────

def _build_cache() -> TTLCache:
    from core.config import CACHE_ENABLED, CACHE_MAX_SIZE, CACHE_TTL
    if not CACHE_ENABLED:
        log.debug("[Cache] キャッシュ無効 (CACHE_ENABLED=false)")
        return _NullCache()
    log.debug(f"[Cache] 初期化 maxsize={CACHE_MAX_SIZE} ttl={CACHE_TTL}s")
    return TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL)


class _NullCache:
    """キャッシュ無効時のノーオペレーション実装。"""
    def get(self, key: str) -> None: return None
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None: pass
    def invalidate(self, key: str) -> bool: return False
    def clear(self) -> None: pass
    def stats(self) -> dict: return {"enabled": False}
    def __len__(self) -> int: return 0


query_cache: TTLCache = _build_cache()
