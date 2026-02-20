"""
rate_limiter.py
===============
Thread-safe, async-compatible rate limiting with four classic strategies:
  - Fixed Window
  - Sliding Window Log
  - Token Bucket
  - Leaky Bucket

Supports single-tier and multi-tier limiting, decorator usage, and context
managers for both sync and async code.

Usage
-----
    from rate_limiter import RateLimiter, TieredRateLimiter, StrategyType

    # Basic
    rl = RateLimiter(limit=100, window=60)
    result = rl.check("user:42")

    # Raise on exceeded
    rl.enforce("user:42")

    # Decorator
    @rl.throttle(key_fn=lambda user_id: f"user:{user_id}")
    def api_call(user_id): ...

    # Async
    result = await rl.async_check("user:42")
"""

import asyncio
import functools
import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RateLimitExceeded(Exception):
    """Raised by enforce() / async_enforce() when a limit is hit."""

    def __init__(self, key: str, retry_after: float, limit: int, strategy: str) -> None:
        self.key = key
        self.retry_after = retry_after
        self.limit = limit
        self.strategy = strategy
        super().__init__(
            f"[{strategy}] Rate limit exceeded for '{key}'. "
            f"Retry after {retry_after:.2f}s (limit={limit})"
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RateLimitResult:
    """Outcome of a single rate-limit check."""

    allowed: bool
    key: str
    remaining: int
    limit: int
    reset_at: float     # Unix timestamp when the quota resets
    retry_after: float  # Seconds to wait when denied (0 when allowed)
    strategy: str

    @property
    def headers(self) -> dict[str, str]:
        """Standard HTTP rate-limit response headers."""
        return {
            "X-RateLimit-Limit":     str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset":     str(int(self.reset_at)),
            "Retry-After":           "0" if self.allowed else str(int(self.retry_after)),
        }


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

class InMemoryStore:
    """
    Minimal thread-safe key/value store with optional TTL.

    Intentionally Redis-compatible in semantics so it can be swapped for a
    real Redis backend later without changing the strategy code.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._ttl:  dict[str, float] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, key: str) -> bool:
        expiry = self._ttl.get(key)
        return expiry is not None and time.monotonic() > expiry

    def _evict(self, key: str) -> None:
        self._data.pop(key, None)
        self._ttl.pop(key, None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return None
            return self._data.get(key)

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._data[key] = value
            if ttl is not None:
                self._ttl[key] = time.monotonic() + ttl

    def delete(self, key: str) -> None:
        with self._lock:
            self._evict(key)

    def incr(self, key: str, ttl: Optional[float] = None) -> int:
        """
        Atomically increment an integer counter.

        Sets the TTL only on the first increment so the window does not
        slide on subsequent calls.
        """
        with self._lock:
            if self._is_expired(key):
                self._evict(key)
            count = self._data.get(key, 0) + 1
            # Pass ttl only when creating the key for the first time
            self.set(key, count, ttl if count == 1 else None)
            return count

    @contextmanager
    def lock(self, _key: str):
        """Acquire the store's reentrant lock (key is ignored; kept for API symmetry)."""
        with self._lock:
            yield


# ---------------------------------------------------------------------------
# Base strategy
# ---------------------------------------------------------------------------

class Strategy(ABC):
    """Abstract base for all rate-limiting algorithms."""

    name: str = "base"

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    @abstractmethod
    def check(self, key: str, limit: int, window: float) -> RateLimitResult:
        ...

    async def async_check(self, key: str, limit: int, window: float) -> RateLimitResult:
        """Run the sync check in a thread-pool executor to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check, key, limit, window)


# ---------------------------------------------------------------------------
# Fixed Window
# ---------------------------------------------------------------------------

class FixedWindow(Strategy):
    """
    Divides time into fixed slots of `window` seconds and counts requests
    per slot. Simple and low-overhead but allows burst traffic at slot
    boundaries (up to 2× the limit in the worst case).
    """

    name = "fixed_window"

    def check(self, key: str, limit: int, window: float) -> RateLimitResult:
        now = time.time()
        slot = int(now / window)
        store_key = f"{key}:fw:{slot}"

        count = self.store.incr(store_key, ttl=window)
        reset_at = (slot + 1) * window
        allowed = count <= limit

        return RateLimitResult(
            allowed=allowed,
            key=key,
            remaining=max(0, limit - count),
            limit=limit,
            reset_at=reset_at,
            retry_after=0.0 if allowed else reset_at - now,
            strategy=self.name,
        )


# ---------------------------------------------------------------------------
# Sliding Window Log
# ---------------------------------------------------------------------------

class SlidingWindowLog(Strategy):
    """
    Keeps a timestamped log of every accepted request and counts only those
    within the rolling window. Precise but memory scales with request volume.
    """

    name = "sliding_window_log"

    def check(self, key: str, limit: int, window: float) -> RateLimitResult:
        now = time.time()
        store_key = f"{key}:swl"
        cutoff = now - window

        with self.store.lock(store_key):
            log: deque = self.store.get(store_key) or deque()

            # Remove timestamps outside the current window
            while log and log[0] <= cutoff:
                log.popleft()

            allowed = len(log) < limit
            if allowed:
                log.append(now)

            self.store.set(store_key, log, ttl=window)

            # Oldest entry tells us when a slot will free up
            retry_after = (log[0] + window - now) if not allowed else 0.0

        return RateLimitResult(
            allowed=allowed,
            key=key,
            remaining=max(0, limit - len(log)),
            limit=limit,
            reset_at=now + window,
            retry_after=retry_after,
            strategy=self.name,
        )


# ---------------------------------------------------------------------------
# Token Bucket
# ---------------------------------------------------------------------------

@dataclass
class _BucketState:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


class TokenBucket(Strategy):
    """
    Maintains a bucket that refills at a constant rate. Allows short bursts
    up to `limit` (the bucket capacity) while enforcing a sustained average.

    Parameters
    ----------
    limit  : Bucket capacity (max burst size).
    window : Seconds to fully refill an empty bucket.
    """

    name = "token_bucket"

    def check(self, key: str, limit: int, window: float) -> RateLimitResult:
        now = time.monotonic()
        store_key = f"{key}:tb"
        rate = limit / window  # tokens per second

        with self.store.lock(store_key):
            state: _BucketState = self.store.get(store_key) or _BucketState(tokens=float(limit))

            # Refill tokens proportional to elapsed time
            elapsed = now - state.last_refill
            state.tokens = min(float(limit), state.tokens + elapsed * rate)
            state.last_refill = now

            allowed = state.tokens >= 1.0
            if allowed:
                state.tokens -= 1.0

            self.store.set(store_key, state, ttl=window * 2)

        tokens_needed = 1.0 - state.tokens if not allowed else 0.0
        retry_after = tokens_needed / rate if not allowed else 0.0

        return RateLimitResult(
            allowed=allowed,
            key=key,
            remaining=int(state.tokens),
            limit=limit,
            reset_at=time.time() + (limit - state.tokens) / rate,
            retry_after=retry_after,
            strategy=self.name,
        )


# ---------------------------------------------------------------------------
# Leaky Bucket
# ---------------------------------------------------------------------------

@dataclass
class _LeakyState:
    queue_size: int = 0
    last_leak: float = field(default_factory=time.monotonic)


class LeakyBucket(Strategy):
    """
    Models a bucket with a hole: requests fill it and it drains at a constant
    rate. Smooths out bursts but drops requests when the bucket is full.

    Parameters
    ----------
    limit  : Bucket capacity (max queued requests).
    window : Seconds to drain a full bucket completely.
    """

    name = "leaky_bucket"

    def check(self, key: str, limit: int, window: float) -> RateLimitResult:
        now = time.monotonic()
        store_key = f"{key}:lb"
        rate = limit / window  # requests drained per second

        with self.store.lock(store_key):
            state: _LeakyState = self.store.get(store_key) or _LeakyState()

            # Drain requests proportional to elapsed time
            elapsed = now - state.last_leak
            leaked = int(elapsed * rate)
            state.queue_size = max(0, state.queue_size - leaked)
            if leaked:
                state.last_leak = now

            allowed = state.queue_size < limit
            if allowed:
                state.queue_size += 1

            self.store.set(store_key, state, ttl=window * 2)

        retry_after = (1.0 / rate) if not allowed else 0.0

        return RateLimitResult(
            allowed=allowed,
            key=key,
            remaining=max(0, limit - state.queue_size),
            limit=limit,
            reset_at=time.time() + state.queue_size / rate,
            retry_after=retry_after,
            strategy=self.name,
        )


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

class StrategyType(str, Enum):
    FIXED_WINDOW       = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    TOKEN_BUCKET       = "token_bucket"
    LEAKY_BUCKET       = "leaky_bucket"


_STRATEGY_MAP: dict[StrategyType, type[Strategy]] = {
    StrategyType.FIXED_WINDOW:       FixedWindow,
    StrategyType.SLIDING_WINDOW_LOG: SlidingWindowLog,
    StrategyType.TOKEN_BUCKET:       TokenBucket,
    StrategyType.LEAKY_BUCKET:       LeakyBucket,
}


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Unified rate limiter supporting multiple strategies and both sync/async
    usage patterns.

    Parameters
    ----------
    limit          : Maximum number of allowed requests per window.
    window         : Duration of the rate-limit window in seconds.
    strategy       : Algorithm to use (default: sliding window log).
    store          : Backing store; a fresh InMemoryStore is created if omitted.
    key_prefix     : Namespace prefix added to all store keys.
    raise_on_limit : If True, check() raises instead of returning a denied result.
    """

    def __init__(
        self,
        limit: int = 100,
        window: float = 60.0,
        strategy: StrategyType = StrategyType.SLIDING_WINDOW_LOG,
        store: Optional[InMemoryStore] = None,
        key_prefix: str = "rl",
        raise_on_limit: bool = False,
    ) -> None:
        self.limit = limit
        self.window = window
        self.raise_on_limit = raise_on_limit
        self.key_prefix = key_prefix
        self._store = store or InMemoryStore()
        self._strategy: Strategy = _STRATEGY_MAP[strategy](self._store)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_key(self, key: str) -> str:
        """Prefix and lightly hash the key to avoid delimiter collisions."""
        short_hash = hashlib.md5(key.encode()).hexdigest()[:8]
        return f"{self.key_prefix}:{short_hash}:{key}"

    # ------------------------------------------------------------------
    # Sync API
    # ------------------------------------------------------------------

    def check(self, key: str) -> RateLimitResult:
        """Check the rate limit without raising. Logs a warning when denied."""
        result = self._strategy.check(self._build_key(key), self.limit, self.window)
        if not result.allowed:
            logger.warning(
                "Rate limit hit | key=%s strategy=%s retry_after=%.2fs",
                key, result.strategy, result.retry_after,
            )
        return result

    def enforce(self, key: str) -> RateLimitResult:
        """Check the rate limit and raise RateLimitExceeded when denied."""
        result = self.check(key)
        if not result.allowed:
            raise RateLimitExceeded(key, result.retry_after, self.limit, result.strategy)
        return result

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def async_check(self, key: str) -> RateLimitResult:
        """Async variant of check()."""
        result = await self._strategy.async_check(self._build_key(key), self.limit, self.window)
        if not result.allowed:
            logger.warning(
                "Rate limit hit | key=%s strategy=%s retry_after=%.2fs",
                key, result.strategy, result.retry_after,
            )
        return result

    async def async_enforce(self, key: str) -> RateLimitResult:
        """Async variant of enforce()."""
        result = await self.async_check(key)
        if not result.allowed:
            raise RateLimitExceeded(key, result.retry_after, self.limit, result.strategy)
        return result

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset(self, key: str) -> None:
        """Clear all stored state for the given key across every strategy."""
        full_key = self._build_key(key)
        for suffix in (":swl", ":tb", ":lb"):
            self._store.delete(full_key + suffix)
        # Fixed-window keys are slot-specific; iterate recent slots
        for offset in range(3):
            slot = int(time.time() / self.window) - offset
            self._store.delete(f"{full_key}:fw:{slot}")

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def throttle(
        self,
        key_fn: Optional[Callable[..., str]] = None,
        fallback_key: str = "global",
    ) -> Callable:
        """
        Decorator factory that rate-limits the wrapped function.

        Parameters
        ----------
        key_fn      : Callable that receives the same arguments as the
                      decorated function and returns the rate-limit key.
                      If omitted, ``fallback_key`` is used for every call.
        fallback_key: Key used when ``key_fn`` is not provided.

        Examples
        --------
        @rl.throttle(key_fn=lambda req: req.user_id)
        def endpoint(req): ...

        @rl.throttle()
        async def background_job(): ...
        """
        def decorator(func: Callable) -> Callable:
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    key = key_fn(*args, **kwargs) if key_fn else fallback_key
                    await self.async_enforce(key)
                    return await func(*args, **kwargs)
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    key = key_fn(*args, **kwargs) if key_fn else fallback_key
                    self.enforce(key)
                    return func(*args, **kwargs)
                return sync_wrapper

        return decorator

    # ------------------------------------------------------------------
    # Context managers
    # ------------------------------------------------------------------

    @contextmanager
    def acquire(self, key: str):
        """Sync context manager that enforces the limit before entering."""
        self.enforce(key)
        yield

    @asynccontextmanager
    async def async_acquire(self, key: str):
        """Async context manager that enforces the limit before entering."""
        await self.async_enforce(key)
        yield

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"RateLimiter(strategy={self._strategy.name!r}, "
            f"limit={self.limit}, window={self.window}s)"
        )


# ---------------------------------------------------------------------------
# TieredRateLimiter
# ---------------------------------------------------------------------------

class TieredRateLimiter:
    """
    Composes multiple RateLimiter instances; **all** tiers must pass.

    Useful for combining short-burst and long-term quotas, e.g.:

        rl = TieredRateLimiter(
            RateLimiter(limit=5,   window=1,    strategy=StrategyType.TOKEN_BUCKET),
            RateLimiter(limit=100, window=60,   strategy=StrategyType.SLIDING_WINDOW_LOG),
            RateLimiter(limit=500, window=3600, strategy=StrategyType.FIXED_WINDOW),
        )
    """

    def __init__(self, *limiters: RateLimiter) -> None:
        if not limiters:
            raise ValueError("At least one RateLimiter is required.")
        self.limiters = limiters

    def check(self, key: str) -> list[RateLimitResult]:
        """Check all tiers and return their results (no exception raised)."""
        return [rl.check(key) for rl in self.limiters]

    def enforce(self, key: str) -> list[RateLimitResult]:
        """Enforce all tiers; raises RateLimitExceeded on the first failure."""
        results = []
        for rl in self.limiters:
            results.append(rl.enforce(key))
        return results

    async def async_enforce(self, key: str) -> list[RateLimitResult]:
        """Async enforce; all tiers are checked concurrently."""
        return list(await asyncio.gather(*[rl.async_enforce(key) for rl in self.limiters]))


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

#: Ready-to-use limiter (100 req / 60 s, sliding window log).
limiter = RateLimiter(
    limit=100,
    window=60.0,
    strategy=StrategyType.SLIDING_WINDOW_LOG,
)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    SEP = "─" * 55

    # ── Token Bucket ──────────────────────────────────────
    print(SEP)
    print("  Token Bucket  —  limit=3, window=5s")
    print(SEP)
    rl = RateLimiter(limit=3, window=5, strategy=StrategyType.TOKEN_BUCKET)
    for i in range(5):
        res = rl.check("demo_user")
        status = "✅ ALLOWED" if res.allowed else "❌ DENIED"
        print(f"  Request {i + 1}: {status} | remaining={res.remaining} | retry_after={res.retry_after:.2f}s")

    # ── Tiered Limiter ────────────────────────────────────
    print()
    print(SEP)
    print("  Tiered Limiter  —  3/5s + 6/10s")
    print(SEP)
    tiered = TieredRateLimiter(
        RateLimiter(limit=3, window=5,  strategy=StrategyType.TOKEN_BUCKET),
        RateLimiter(limit=6, window=10, strategy=StrategyType.FIXED_WINDOW),
    )
    for i in range(7):
        try:
            tiered.enforce("api_user")
            print(f"  Request {i + 1}: ✅ ALLOWED")
        except RateLimitExceeded as exc:
            print(f"  Request {i + 1}: ❌ {exc}")

    # ── Decorator ─────────────────────────────────────────
    print()
    print(SEP)
    print("  Decorator usage  —  limit=2, window=10s")
    print(SEP)
    rl2 = RateLimiter(limit=2, window=10, strategy=StrategyType.SLIDING_WINDOW_LOG)

    @rl2.throttle(key_fn=lambda user_id: f"user:{user_id}")
    def fetch_data(user_id: str) -> str:
        return f"data for {user_id}"

    for i in range(4):
        try:
            print(f"  Call {i + 1}: {fetch_data('alice')}")
        except RateLimitExceeded as exc:
            print(f"  Call {i + 1}: ❌ {exc}")