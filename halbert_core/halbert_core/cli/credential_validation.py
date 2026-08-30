# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Credential validation — standalone human-run tool to check if a
credential is still active.

**This module is NOT part of the Tier 2 describe_secret path.**
``describe_secret`` in ``secure_response.py`` never calls this module.
The Tier 2 architectural guarantee is that a secret value never leaves
the tool when the LLM asks about it. This module sends the secret to
the issuing service's API, which breaks that guarantee. It exists as a
standalone tool a human can run deliberately to check their own
credentials — the secret never enters an LLM context.

This is the TruffleHog pattern: verification against issuing APIs is a
scanner activity performed by a human, not a describe activity
performed by an agent.

Usage
-----
Call ``validate_credential(value, service, enabled=True)`` directly.
The function returns ``{"status": "disabled"}`` without making any
network call when ``enabled`` is False (the default).

Security notes
--------------
- Each service's validator uses a minimal API call that reveals no
  sensitive data beyond what the credential itself grants.
- Validation results are cached for 1 hour to avoid repeated calls.
- Network errors return ``{"status": "error", "detail": "..."}`` rather
  than treating a network failure as "invalid".
- The credential is sent over HTTPS to the service's documented API
  endpoint. No third-party intermediaries are involved.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache: (credential_hash, service) -> (result, timestamp)
_validation_cache: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]] = {}
_CACHE_TTL = 3600  # 1 hour


def _hash_token(token: str) -> str:
    """Hash a token for cache keying without storing the token itself."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _is_validation_enabled(
    service: str,
    *,
    enabled: bool = False,
    services: Optional[List[str]] = None,
) -> bool:
    """Check if validation is enabled for this service."""
    if not enabled:
        return False
    if services is None:
        return True  # enabled for all
    return service.lower() in [s.lower() for s in services]


# ---------------------------------------------------------------------------
# Service validators
# ---------------------------------------------------------------------------

def _validate_github(token: str) -> Dict[str, Any]:
    """Validate a GitHub token by calling /user."""
    import urllib.request
    import json as _json

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "Halbert-MCP/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = _json.loads(resp.read())
                return {
                    "status": "valid",
                    "service": "GitHub",
                    "user": data.get("login", ""),
                    "scopes": resp.headers.get("X-OAuth-Scopes", ""),
                }
            return {"status": "invalid", "service": "GitHub"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"status": "invalid", "service": "GitHub"}
        return {"status": "error", "service": "GitHub", "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "service": "GitHub", "detail": str(e)}


def _validate_openai(token: str) -> Dict[str, Any]:
    """Validate an OpenAI API key by calling /v1/models."""
    import urllib.request
    import json as _json

    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = _json.loads(resp.read())
                model_count = len(data.get("data", []))
                return {
                    "status": "valid",
                    "service": "OpenAI",
                    "models_available": model_count,
                }
            return {"status": "invalid", "service": "OpenAI"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"status": "invalid", "service": "OpenAI"}
        return {"status": "error", "service": "OpenAI", "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "service": "OpenAI", "detail": str(e)}


def _validate_stripe(token: str) -> Dict[str, Any]:
    """Validate a Stripe key by calling /v1/balance."""
    import urllib.request

    req = urllib.request.Request("https://api.stripe.com/v1/balance")
    # Stripe uses HTTP Basic auth with the API key as the username
    import base64
    credentials = base64.b64encode(f"{token}:".encode()).decode()
    req.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return {"status": "valid", "service": "Stripe"}
            return {"status": "invalid", "service": "Stripe"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"status": "invalid", "service": "Stripe"}
        return {"status": "error", "service": "Stripe", "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "service": "Stripe", "detail": str(e)}


def _validate_slack(token: str) -> Dict[str, Any]:
    """Validate a Slack token by calling auth.test."""
    import urllib.request
    import json as _json

    data = b"token=" + token.encode()
    req = urllib.request.Request(
        "https://slack.com/api/auth.test",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                result = _json.loads(resp.read())
                if result.get("ok"):
                    return {
                        "status": "valid",
                        "service": "Slack",
                        "team": result.get("team", ""),
                        "user": result.get("user", ""),
                    }
                return {"status": "invalid", "service": "Slack"}
            return {"status": "invalid", "service": "Slack"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"status": "invalid", "service": "Slack"}
        return {"status": "error", "service": "Slack", "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "service": "Slack", "detail": str(e)}


# Service name -> validator function
_VALIDATORS = {
    "github": _validate_github,
    "openai": _validate_openai,
    "stripe": _validate_stripe,
    "slack": _validate_slack,
}


def validate_credential(
    value: str,
    service: str,
    *,
    enabled: bool = False,
    services: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate a credential against the legitimate service's API.

    Parameters
    ----------
    value
        The credential value to validate.
    service
        The service name (must match a key in _VALIDATORS).
    enabled
        Whether credential validation is globally enabled.
    services
        List of service names to validate. If None and enabled=True,
        all services are validated.

    Returns
    -------
    dict with ``status`` (valid, invalid, disabled, error), ``service``,
    and service-specific details.

    The credential is sent to the service's own API over HTTPS. It is
    NOT sent to any LLM vendor. This is the same call a human would make
    to test a key.
    """
    if not _is_validation_enabled(service, enabled=enabled, services=services):
        return {"status": "disabled", "service": service}

    if not value or not isinstance(value, str):
        return {"status": "error", "service": service, "detail": "empty or non-string value"}

    service_lower = service.lower()
    if service_lower not in _VALIDATORS:
        return {"status": "error", "service": service, "detail": f"no validator for {service}"}

    # Check cache
    cache_key = (_hash_token(value), service_lower)
    cached = _validation_cache.get(cache_key)
    if cached:
        result, timestamp = cached
        if time.time() - timestamp < _CACHE_TTL:
            return result

    # Call the validator
    validator = _VALIDATORS[service_lower]
    try:
        result = validator(value)
    except Exception as e:
        result = {"status": "error", "service": service, "detail": str(e)}

    # Cache the result
    _validation_cache[cache_key] = (result, time.time())

    return result


def available_services() -> List[str]:
    """List services that have validators configured."""
    return sorted(_VALIDATORS.keys())
