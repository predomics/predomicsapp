"""Single-use tickets for opening a WebSocket.

Browsers cannot send an Authorization header on a WebSocket handshake, so the
credential has to travel in the URL, where proxies and access logs record it.
Instead of the long-lived access token, the client first asks for a ticket over
the normal authenticated API: a random value that works once, for one user,
for :data:`TICKET_TTL` seconds.

Tickets live in this process's memory: the app runs as a single process
(see the job runner), and a restart only costs the client a new ticket.
"""

from __future__ import annotations

import secrets
import threading
import time

TICKET_TTL = 30  # seconds
_MAX_TICKETS = 10_000

_lock = threading.Lock()
_tickets: dict[str, tuple[str, float]] = {}  # ticket -> (user_id, expires_at monotonic)


def _purge(now: float) -> None:
    for t in [t for t, (_, exp) in _tickets.items() if exp <= now]:
        del _tickets[t]


def issue(user_id: str) -> str:
    """Create a ticket for ``user_id``."""
    now = time.monotonic()
    ticket = secrets.token_urlsafe(32)
    with _lock:
        _purge(now)
        if len(_tickets) >= _MAX_TICKETS:  # runaway client: drop the oldest
            for t in sorted(_tickets, key=lambda k: _tickets[k][1])[: _MAX_TICKETS // 10]:
                del _tickets[t]
        _tickets[ticket] = (user_id, now + TICKET_TTL)
    return ticket


def redeem(ticket: str) -> str | None:
    """Return the user id for a valid ticket and invalidate it; None otherwise."""
    if not ticket:
        return None
    now = time.monotonic()
    with _lock:
        entry = _tickets.pop(ticket, None)
        _purge(now)
    if entry is None or entry[1] <= now:
        return None
    return entry[0]


def clear() -> None:
    """Forget every ticket (tests)."""
    with _lock:
        _tickets.clear()
