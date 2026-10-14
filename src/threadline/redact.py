"""Shared secret-redaction helpers (M1).

Logs, error messages, and API responses must never contain credentials.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|api[_-]?key|secret|token|bearer|authorization)\s*"
    r"([=:]\s*| +)([^\s,;\"']+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9\-._~+/=]+)")
# URL userinfo passwords have no key word: scheme://user:password@host/...
_URL_PASSWORD_PATTERN = re.compile(r"(?i)(://[^/\s:@?#]+:)([^@\s/?#]+)(@)")


def _mask_match(m: re.Match) -> str:
    sep = m.group(2)
    joiner = "=" if ("=" in sep or ":" in sep) else " "
    return f"{m.group(1)}{joiner}[REDACTED]"


def redact_secrets(text: str) -> str:
    """Replace likely secret values with `[REDACTED]` (best-effort)."""
    if not text:
        return text
    redacted = _SECRET_KEY_PATTERN.sub(_mask_match, text)
    redacted = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)} [REDACTED]", redacted)
    redacted = _URL_PASSWORD_PATTERN.sub(lambda m: f"{m.group(1)}[REDACTED]{m.group(3)}", redacted)
    return redacted


def redact_url(url: str) -> str:
    """Strip password/userinfo from a URL for safe display in errors/logs."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if parts.password or "@" in parts.netloc:
            # Rebuild netloc without credentials.
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
        return url
    except Exception:
        return "[UNPARSEABLE_URL]"
