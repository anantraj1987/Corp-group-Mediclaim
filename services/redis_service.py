import json
import hashlib
from typing import Optional, Dict, Any
import redis
from config.settings import settings
from utils.logger import logger


class RedisCacheService:
    """Manages fast response retrieval for recurring queries."""

    def __init__(self):
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,
                socket_timeout=2
            )
            self.client.ping()
            self.is_connected = True
            logger.info("[REDIS] Connected to Redis Cache successfully.")
        except Exception as e:
            self.is_connected = False
            logger.warning(f"[REDIS] Redis server unavailable ({str(e)}). Proceeding without cache.")

    def _generate_key(self, query: str, user_id: str) -> str:
        """Generates a deterministic cache key for a given user query."""
        normalized = f"{user_id}:{query.strip().lower()}"
        return f"cache:incident:{hashlib.md5(normalized.encode()).hexdigest()}"

    def get_cached_solution(self, query: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached solution if available."""
        if not self.is_connected:
            return None

        try:
            key = self._generate_key(query, user_id)
            cached_data = self.client.get(key)
            if cached_data:
                logger.info(f"[REDIS] Cache HIT for key: {key}")
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"[REDIS] Error reading from cache: {str(e)}")

        logger.info("[REDIS] Cache MISS.")
        return None

    def set_cached_solution(self, query: str, user_id: str, payload: Dict[str, Any]):
        """Caches successful incident solutions in Redis."""
        if not self.is_connected:
            return

        try:
            key = self._generate_key(query, user_id)
            self.client.setex(
                key,
                settings.REDIS_CACHE_TTL,
                json.dumps(payload)
            )
            logger.info(f"[REDIS] Cached solution under key: {key} (TTL: {settings.REDIS_CACHE_TTL}s)")
        except Exception as e:
            logger.error(f"[REDIS] Error writing to cache: {str(e)}")


redis_service = RedisCacheService()

