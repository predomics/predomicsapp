"""Back-off after repeated failed logins.

Failures are counted per account (the email typed, whether or not it exists,
so the answer never reveals which addresses have accounts) and per client IP.
After a few free attempts each further failure doubles the wait, up to a cap.
A successful login clears the account counter.

State is in memory: the app is a single process, and losing the counters on a
restart only gives an attacker a handful of extra guesses.
"""

from __future__ import annotations

import math
import threading
import time

from ..core.config import settings

_BASE_DELAY = 30.0        # seconds, for the first throttled attempt
_IP_FREE_FACTOR = 4       # an IP (office, NAT) gets more room than a single account
_FORGET_AFTER = 24 * 3600  # counters idle this long are dropped
_MAX_ENTRIES = 50_000

_lock = threading.Lock()
# key -> [failures, blocked_until (wall clock), last_failure (wall clock)]
_state: dict[str, list[float]] = {}


def enabled() -> bool:
    return bool(settings.login_throttle_enabled and settings.rate_limit_enabled)


def _keys(email: str, ip: str | None) -> list[tuple[str, int]]:
    free = max(1, settings.login_throttle_free_attempts)
    keys = [(f"acct:{email}", free)]
    if ip:
        keys.append((f"ip:{ip}", free * _IP_FREE_FACTOR))
    return keys


def retry_after(email: str, ip: str | None) -> int:
    """Seconds the caller must still wait before another attempt (0 = go ahead)."""
    if not enabled():
        return 0
    now = time.time()
    wait = 0.0
    with _lock:
        for key, _free in _keys(email, ip):
            entry = _state.get(key)
            if entry and entry[1] > now:
                wait = max(wait, entry[1] - now)
    return math.ceil(wait)


def record_failure(email: str, ip: str | None) -> None:
    if not enabled():
        return
    now = time.time()
    cap = max(1, settings.login_throttle_max_minutes) * 60.0
    with _lock:
        if len(_state) > _MAX_ENTRIES:
            for k in [k for k, v in _state.items() if now - v[2] > 3600]:
                del _state[k]
        for key, free in _keys(email, ip):
            entry = _state.get(key)
            if entry is None or now - entry[2] > _FORGET_AFTER:
                entry = _state[key] = [0.0, 0.0, now]
            entry[0] += 1
            entry[2] = now
            over = int(entry[0]) - free
            if over >= 0:
                entry[1] = now + min(cap, _BASE_DELAY * (2 ** min(over, 20)))


def record_success(email: str, ip: str | None) -> None:
    """A correct password clears the account's counter (the IP's is left to age out)."""
    with _lock:
        _state.pop(f"acct:{email}", None)


def clear() -> None:
    """Forget everything (tests, admin unlock)."""
    with _lock:
        _state.clear()


def unlock_account(email: str) -> None:
    with _lock:
        _state.pop(f"acct:{(email or '').strip().lower()}", None)
