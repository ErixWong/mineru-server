"""
Concurrency Control Module

Provides rate limiting and concurrent task management for MCP Server.
"""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional
from collections import deque

from loguru import logger


@dataclass
class RateLimitConfig:
    """Rate limit configuration.
    
    Attributes:
        max_requests_per_minute: Maximum requests per minute.
        max_concurrent_tasks: Maximum concurrent parsing tasks.
        task_timeout_seconds: Maximum task duration in seconds.
    """
    max_requests_per_minute: int = 60
    max_concurrent_tasks: int = 5
    task_timeout_seconds: float = 600.0


class RateLimiter:
    """Rate limiter using sliding window algorithm.
    
    Limits the number of requests per time window.
    """
    
    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        """Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed in window.
            window_seconds: Time window in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._request_times: deque = deque()
        self._lock = asyncio.Lock()
    
    async def check(self) -> bool:
        """Check if a request is allowed.
        
        Returns:
            True if request is allowed, False if rate limited.
        """
        async with self._lock:
            now = time.time()
            
            # Remove old requests outside the window
            while self._request_times and self._request_times[0] < now - self.window_seconds:
                self._request_times.popleft()
            
            # Check if we're at the limit
            if len(self._request_times) >= self.max_requests:
                logger.warning(f"Rate limit reached: {self.max_requests} requests per {self.window_seconds}s")
                return False
            
            # Record this request
            self._request_times.append(now)
            return True
    
    async def wait_if_needed(self, max_wait: float = 30.0) -> bool:
        """Wait if rate limited, up to max_wait seconds.
        
        Args:
            max_wait: Maximum wait time in seconds.
            
        Returns:
            True if request is now allowed, False if still limited.
        """
        async with self._lock:
            now = time.time()
            
            # Remove old requests
            while self._request_times and self._request_times[0] < now - self.window_seconds:
                self._request_times.popleft()
            
            # If under limit, proceed
            if len(self._request_times) < self.max_requests:
                self._request_times.append(now)
                return True
            
            # Calculate wait time
            oldest_request = self._request_times[0]
            wait_time = oldest_request + self.window_seconds - now
            
            if wait_time > max_wait:
                logger.warning(f"Rate limit wait time ({wait_time}s) exceeds max wait ({max_wait}s)")
                return False
            
            # Wait and then proceed
            logger.info(f"Rate limited, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            
            # Clean up again after waiting
            now = time.time()
            while self._request_times and self._request_times[0] < now - self.window_seconds:
                self._request_times.popleft()
            
            self._request_times.append(now)
            return True
    
    def get_current_rate(self) -> int:
        """Get current request count in window.
        
        Returns:
            Number of requests in current window.
        """
        now = time.time()
        count = 0
        for t in self._request_times:
            if t >= now - self.window_seconds:
                count += 1
        return count


class ConcurrentTaskLimiter:
    """Limits concurrent tasks using a semaphore.
    
    Controls how many tasks can run simultaneously.
    """
    
    def __init__(self, max_concurrent: int = 5):
        """Initialize concurrent task limiter.
        
        Args:
            max_concurrent: Maximum concurrent tasks.
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: dict[str, float] = {}  # task_id -> start_time
        self._lock = asyncio.Lock()
    
    async def acquire(self, task_id: str, timeout: float = 30.0) -> bool:
        """Acquire a slot for a task.
        
        Args:
            task_id: Task identifier.
            timeout: Maximum wait time to acquire slot.
            
        Returns:
            True if slot acquired, False if timeout.
        """
        try:
            # Wait for semaphore with timeout
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            
            # Record task start
            async with self._lock:
                self._active_tasks[task_id] = time.time()
            
            logger.debug(f"Task {task_id} acquired slot ({len(self._active_tasks)}/{self.max_concurrent} active)")
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_id} failed to acquire slot after {timeout}s")
            return False
    
    async def release(self, task_id: str) -> None:
        """Release a task slot.
        
        Args:
            task_id: Task identifier.
        """
        async with self._lock:
            if task_id in self._active_tasks:
                start_time = self._active_tasks.pop(task_id)
                duration = time.time() - start_time
                logger.debug(f"Task {task_id} released slot after {duration:.1f}s")
        
        self._semaphore.release()
    
    def get_active_count(self) -> int:
        """Get number of active tasks.
        
        Returns:
            Number of currently active tasks.
        """
        return len(self._active_tasks)
    
    def get_active_tasks(self) -> list[str]:
        """Get list of active task IDs.
        
        Returns:
            List of active task IDs.
        """
        return list(self._active_tasks.keys())
    
    async def cleanup_stale_tasks(self, max_age: float = 600.0) -> int:
        """Clean up tasks that have been running too long.
        
        Args:
            max_age: Maximum task age in seconds.
            
        Returns:
            Number of tasks cleaned up.
        """
        now = time.time()
        cleaned = 0
        
        async with self._lock:
            stale_tasks = [
                task_id for task_id, start_time in self._active_tasks.items()
                if now - start_time > max_age
            ]
            
            for task_id in stale_tasks:
                self._active_tasks.pop(task_id)
                self._semaphore.release()
                cleaned += 1
                logger.warning(f"Cleaned up stale task {task_id} (age: {now - self._active_tasks.get(task_id, now):.1f}s)")
        
        return cleaned


class ConcurrencyManager:
    """Manages rate limiting and concurrent task control.
    
    Combines RateLimiter and ConcurrentTaskLimiter for comprehensive control.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize concurrency manager.
        
        Args:
            config: Rate limit configuration. Defaults to RateLimitConfig().
        """
        if config is None:
            config = RateLimitConfig()
        
        self.config = config
        self.rate_limiter = RateLimiter(
            max_requests=config.max_requests_per_minute,
            window_seconds=60.0,
        )
        self.task_limiter = ConcurrentTaskLimiter(
            max_concurrent=config.max_concurrent_tasks,
        )
    
    async def check_rate_limit(self) -> bool:
        """Check if request is allowed by rate limiter.
        
        Returns:
            True if allowed, False if rate limited.
        """
        return await self.rate_limiter.check()
    
    async def acquire_task_slot(self, task_id: str) -> bool:
        """Acquire a slot for a task.
        
        Args:
            task_id: Task identifier.
            
        Returns:
            True if slot acquired, False if no slots available.
        """
        return await self.task_limiter.acquire(task_id)
    
    async def release_task_slot(self, task_id: str) -> None:
        """Release a task slot.
        
        Args:
            task_id: Task identifier.
        """
        await self.task_limiter.release(task_id)
    
    def get_status(self) -> dict:
        """Get current concurrency status.
        
        Returns:
            Status dictionary with rate and task info.
        """
        return {
            "rate_limit": {
                "current_rate": self.rate_limiter.get_current_rate(),
                "max_per_minute": self.config.max_requests_per_minute,
            },
            "tasks": {
                "active_count": self.task_limiter.get_active_count(),
                "max_concurrent": self.config.max_concurrent_tasks,
                "active_tasks": self.task_limiter.get_active_tasks(),
            },
        }
    
    async def cleanup(self) -> dict:
        """Clean up stale tasks.
        
        Returns:
            Cleanup result dictionary.
        """
        cleaned = await self.task_limiter.cleanup_stale_tasks(
            max_age=self.config.task_timeout_seconds,
        )
        return {
            "cleaned_tasks": cleaned,
            "remaining_active": self.task_limiter.get_active_count(),
        }


# Global concurrency manager instance
_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """Get the global concurrency manager instance."""
    if _manager is None:
        config = RateLimitConfig(
            max_requests_per_minute=int(os.getenv("MCP_MAX_REQUESTS_PER_MINUTE", "60")),
            max_concurrent_tasks=int(os.getenv("MCP_MAX_CONCURRENT_TASKS", "5")),
            task_timeout_seconds=float(os.getenv("MCP_TASK_TIMEOUT_SECONDS", "600")),
        )
        _manager = ConcurrencyManager(config)
    return _manager


def reset_concurrency_manager() -> None:
    """Reset the global concurrency manager (for testing)."""
    global _manager
    _manager = None
