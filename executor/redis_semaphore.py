"""
Redis-based distributed semaphore for limiting concurrent match executions.
"""

import asyncio
import logging
import time
from typing import Optional
import uuid

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisSemaphore:
    """
    Redis-based distributed semaphore to limit concurrent operations.
    
    Uses a Redis sorted set to track semaphore holders with timestamps.
    """

    def __init__(
        self,
        redis_url: str,
        key: str,
        max_concurrent: int,
        timeout_sec: int = 300,
    ) -> None:
        """
        Initialize Redis semaphore.

        Args:
            redis_url: Redis connection URL
            key: Redis key for the semaphore
            max_concurrent: Maximum number of concurrent holders
            timeout_sec: Timeout for stale entries (default: 5 minutes)
        """
        self.redis_url = redis_url
        self.key = key
        self.max_concurrent = max_concurrent
        self.timeout_sec = timeout_sec
        self.client: Optional[aioredis.Redis] = None
        self.holder_id: Optional[str] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        if self.client is None:
            self.client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(f"Connected to Redis for semaphore: {self.key}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self.client = None

    async def acquire(self, timeout_sec: Optional[int] = None) -> bool:
        """
        Acquire semaphore slot.

        Args:
            timeout_sec: Maximum time to wait for acquisition (None = wait forever)

        Returns:
            True if acquired, False if timeout

        Raises:
            RuntimeError: If Redis is not connected
        """
        if self.client is None:
            await self.connect()

        if self.holder_id is not None:
            raise RuntimeError("Semaphore already acquired by this instance")

        self.holder_id = str(uuid.uuid4())
        start_time = time.time()

        while True:
            # Clean up stale entries
            await self._cleanup_stale()

            # Try to acquire
            if await self._try_acquire():
                logger.info(
                    f"Semaphore acquired: {self.key} "
                    f"(holder: {self.holder_id}, "
                    f"max: {self.max_concurrent})"
                )
                return True

            # Check timeout
            if timeout_sec is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout_sec:
                    logger.warning(
                        f"Semaphore acquisition timeout: {self.key} "
                        f"(waited {elapsed:.1f}s)"
                    )
                    self.holder_id = None
                    return False

            # Wait before retry
            await asyncio.sleep(0.5)

    async def _try_acquire(self) -> bool:
        """
        Try to acquire semaphore (atomic operation).

        Returns:
            True if acquired, False otherwise
        """
        # Lua script for atomic acquire
        script = """
        local key = KEYS[1]
        local max_concurrent = tonumber(ARGV[1])
        local holder_id = ARGV[2]
        local current_time = tonumber(ARGV[3])
        
        -- Count current holders
        local count = redis.call('ZCARD', key)
        
        -- If below limit, add holder
        if count < max_concurrent then
            redis.call('ZADD', key, current_time, holder_id)
            return 1
        else
            return 0
        end
        """

        current_time = time.time()
        result = await self.client.eval(
            script,
            1,  # Number of keys
            self.key,
            self.max_concurrent,
            self.holder_id,
            current_time,
        )

        return result == 1

    async def release(self) -> bool:
        """
        Release semaphore slot.

        Returns:
            True if released, False if not held

        Raises:
            RuntimeError: If Redis is not connected
        """
        if self.client is None:
            raise RuntimeError("Redis not connected")

        if self.holder_id is None:
            logger.warning("Semaphore not held, cannot release")
            return False

        # Remove from sorted set
        removed = await self.client.zrem(self.key, self.holder_id)

        if removed:
            logger.info(
                f"Semaphore released: {self.key} (holder: {self.holder_id})"
            )
            self.holder_id = None
            return True
        else:
            logger.warning(
                f"Semaphore holder not found: {self.key} "
                f"(holder: {self.holder_id})"
            )
            self.holder_id = None
            return False

    async def _cleanup_stale(self) -> None:
        """Remove stale semaphore holders (exceeded timeout)."""
        cutoff_time = time.time() - self.timeout_sec

        # Remove entries older than cutoff
        removed = await self.client.zremrangebyscore(
            self.key,
            "-inf",
            cutoff_time,
        )

        if removed > 0:
            logger.info(
                f"Cleaned up {removed} stale semaphore holder(s): {self.key}"
            )

    async def get_current_count(self) -> int:
        """
        Get current number of semaphore holders.

        Returns:
            Number of active holders
        """
        if self.client is None:
            await self.connect()

        return await self.client.zcard(self.key)

    async def get_available_slots(self) -> int:
        """
        Get number of available semaphore slots.

        Returns:
            Number of available slots
        """
        current = await self.get_current_count()
        return max(0, self.max_concurrent - current)

    async def __aenter__(self):
        """Context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.release()


class SemaphoreManager:
    """
    Manager for multiple Redis semaphores.
    
    Useful for managing different resource pools (e.g., per-environment limits).
    """

    def __init__(self, redis_url: str, default_max_concurrent: int = 10) -> None:
        """
        Initialize semaphore manager.

        Args:
            redis_url: Redis connection URL
            default_max_concurrent: Default max concurrent operations
        """
        self.redis_url = redis_url
        self.default_max_concurrent = default_max_concurrent
        self.semaphores: dict[str, RedisSemaphore] = {}

    def get_semaphore(
        self,
        name: str,
        max_concurrent: Optional[int] = None,
    ) -> RedisSemaphore:
        """
        Get or create a semaphore.

        Args:
            name: Semaphore name (used as Redis key suffix)
            max_concurrent: Max concurrent holders (None = use default)

        Returns:
            RedisSemaphore instance
        """
        if name not in self.semaphores:
            max_concurrent = max_concurrent or self.default_max_concurrent
            key = f"executor:semaphore:{name}"
            
            self.semaphores[name] = RedisSemaphore(
                redis_url=self.redis_url,
                key=key,
                max_concurrent=max_concurrent,
            )

        return self.semaphores[name]

    async def disconnect_all(self) -> None:
        """Disconnect all semaphores."""
        for semaphore in self.semaphores.values():
            await semaphore.disconnect()
        self.semaphores.clear()
