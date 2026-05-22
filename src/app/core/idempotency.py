from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _redis_key(site_slug: str, client_key: str) -> str:
    h = hashlib.sha256(f"{site_slug}:{client_key}".encode()).hexdigest()[:48]
    return f"orch:idemp:v1:{site_slug}:{h}"


def enqueue_with_idempotency(
    *,
    site_slug: str,
    client_key: str | None,
    enqueue: Callable[[], str],
) -> str:
    """
    ``enqueue`` должен вернуть строку с id задачи Celery.
    Если ``client_key`` пустой — один вызов ``enqueue`` без участия Redis.
    """
    ck = (client_key or "").strip()
    if not ck:
        return enqueue()

    try:
        import redis
        from app.core.config import get_settings

        settings = get_settings()
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        ttl = int(settings.idempotency_ttl_seconds)
    except Exception as e:
        logger.warning("idempotency disabled (redis): %s", e)
        return enqueue()

    rkey = _redis_key(site_slug, ck)
    existing = r.get(rkey)
    if existing and existing != "pending":
        return existing

    if existing == "pending":
        for _ in range(100):
            time.sleep(0.05)
            v = r.get(rkey)
            if v and v != "pending":
                return v
        logger.warning("idempotency wait timeout for %s", rkey)
        return enqueue()

    if not r.set(rkey, "pending", nx=True, ex=ttl):
        v = r.get(rkey)
        if v and v != "pending":
            return v
        return enqueue()

    try:
        task_id = enqueue()
        r.set(rkey, task_id, ex=ttl)
        return task_id
    except Exception:
        try:
            r.delete(rkey)
        except Exception:
            logger.exception("idempotency cleanup failed")
        raise
