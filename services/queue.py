"""
RQ taakwachtrij voor asynchrone e-mailverwerking.
"""
import logging
import os
import redis
from rq import Queue

logger = logging.getLogger(__name__)

# Lokaal: localhost:6379 | Docker: redis://valkey:6379
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    redis_conn = redis.from_url(REDIS_URL, socket_connect_timeout=5)
    redis_conn.ping()
    email_queue = Queue("emails", connection=redis_conn)
    logger.info(f"✓ Redis verbinding tot stand gebracht ({REDIS_URL})")
except redis.exceptions.ConnectionError as e:
    logger.critical(f"❌ Kan geen verbinding maken met Redis op {REDIS_URL}: {e}")
    raise RuntimeError(
        f"Redis niet bereikbaar op {REDIS_URL}. "
        "Lokaal: `sudo systemctl start valkey` | Docker: `docker compose up`"
    ) from e
