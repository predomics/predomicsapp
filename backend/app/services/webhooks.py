"""Webhook delivery service with HMAC-SHA256 signing."""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlsplit

import httpx

from ..core.config import settings

_log = logging.getLogger(__name__)


class UnsafeWebhookURL(ValueError):
    """The URL is malformed or points at an address webhooks must not reach."""


def validate_webhook_url(url: str) -> str:
    """Return ``url`` if it is an http(s) URL resolving only to public addresses.

    Webhooks make the server send requests on a user's behalf, so they must not
    be able to reach loopback, private, link-local (cloud metadata) or otherwise
    internal addresses. Set PREDOMICS_WEBHOOK_ALLOW_PRIVATE=true for trusted
    intranet deployments.
    """
    try:
        parts = urlsplit(url or "")
    except ValueError:
        raise UnsafeWebhookURL("Enter a valid URL")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeWebhookURL("Webhook URL must start with http:// or https://")
    if parts.username or parts.password:
        raise UnsafeWebhookURL("Webhook URL must not contain credentials")
    if getattr(settings, "webhook_allow_private", False):
        return url
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, ValueError):
        raise UnsafeWebhookURL("Webhook host could not be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise UnsafeWebhookURL("Webhook URL must point to a public address")
    return url


def _sign_payload(payload_json: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()


def send_webhook_sync(url: str, payload: dict, secret: str, retries: int = 3) -> bool:
    """Send webhook with retries. Runs in sync context."""
    try:
        validate_webhook_url(url)  # re-checked at send time: DNS may have changed
    except UnsafeWebhookURL as e:
        _log.warning("Webhook to %s blocked: %s", url, e)
        return False
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    signature = _sign_payload(payload_json, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "User-Agent": "PredomicsApp-Webhook/1.0",
    }

    for attempt in range(retries):
        try:
            resp = httpx.post(url, content=payload_json, headers=headers, timeout=10, follow_redirects=False)
            if resp.status_code < 400:
                _log.info("Webhook delivered to %s (status %d)", url, resp.status_code)
                return True
            _log.warning("Webhook to %s returned %d", url, resp.status_code)
        except Exception as e:
            _log.warning("Webhook to %s failed (attempt %d): %s", url, attempt + 1, e)
        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    return False
