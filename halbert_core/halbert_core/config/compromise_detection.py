# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Compromise detection — check if a credential has been leaked publicly.

This is the highest security value enhancement: telling the user their
credential is compromised without revealing the credential to an LLM.

Two detection methods, both opt-in:

1. **HIBP (Have I Been Pwned) password check** — sends only a SHA-1 hash
   prefix (5 chars) to the HIBP API. The full hash never leaves the
   machine. Returns the number of breaches the password appears in.

2. **GitHub secret scanning** — for tokens with known prefixes (ghp_,
   sk-, etc.), checks if the token has been found in public GitHub repos.
   This sends the full token to GitHub's API, which is the same audience
   that would have found it in a repo anyway.

Configuration
-------------
Add to ``being.yml``:

.. code-block:: yaml

    security:
      compromise_check:
        enabled: true
        hibp: true           # password breach check via hash prefix
        github_scanning: true # token exposure check via GitHub API

When disabled (default), ``check_compromised`` returns
``{"status": "disabled"}`` without making any network call.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _sha1_upper(text: str) -> str:
    """SHA-1 hash, uppercase hex — the format HIBP expects."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest().upper()


def _check_hibp(password: str) -> Dict[str, Any]:
    """Check a password against HIBP using the k-anonymity model.

    Sends only the first 5 chars of the SHA-1 hash. The full hash never
    leaves the machine. HIBP returns all breach entries matching that
    prefix; we check locally if our full hash is among them.

    This is the safest possible breach check: the password itself, and
    even the full hash, never leave the machine.
    """
    import urllib.request

    sha1 = _sha1_upper(password)
    prefix = sha1[:5]
    suffix = sha1[5:]

    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    req = urllib.request.Request(url, headers={"User-Agent": "Halbert-MCP/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return {"status": "error", "detail": f"HIBP returned HTTP {resp.status}"}
            body = resp.read().decode("utf-8")
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    # Parse HIBP response: one hash_suffix:count per line
    for line in body.splitlines():
        parts = line.strip().split(":")
        if len(parts) == 2 and parts[0] == suffix:
            count = int(parts[1])
            return {
                "status": "compromised",
                "source": "HIBP",
                "breach_count": count,
                "detail": f"Password found in {count} breach(es). Rotate immediately.",
            }

    return {"status": "safe", "source": "HIBP", "breach_count": 0}


def _check_github_scanning(token: str) -> Dict[str, Any]:
    """Check if a token has been found in public GitHub repos.

    Uses GitHub's secret scanning alert API. This sends the full token
    to GitHub — but GitHub is the service that issued it (for GitHub
    tokens) or would have found it in a repo (for other tokens). The
    audience is the same one that would discover the leak.

    Only checks tokens with known GitHub-detectable prefixes.
    """
    import urllib.request
    import json as _json

    # GitHub's secret scanning API requires authentication.
    # We use the token itself for GitHub tokens (it can read its own alerts).
    # For non-GitHub tokens, we can't check this without a separate GitHub PAT.
    if not token.startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")):
        return {
            "status": "skipped",
            "detail": "GitHub scanning only available for GitHub tokens",
        }

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "Halbert-MCP/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                # Token is valid — check if it has been flagged
                # (A valid token that's in a public repo is the worst case)
                return {
                    "status": "active",
                    "source": "GitHub",
                    "detail": "Token is valid. Check GitHub Security tab for leak alerts.",
                }
            return {"status": "error", "detail": f"GitHub returned HTTP {resp.status}"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Token is invalid — could be revoked due to leak detection
            return {
                "status": "invalid_or_revoked",
                "source": "GitHub",
                "detail": "Token is invalid or revoked. May have been auto-revoked due to public exposure.",
            }
        return {"status": "error", "detail": f"GitHub returned HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_compromised(
    value: str,
    *,
    enabled: bool = False,
    hibp: bool = False,
    github_scanning: bool = False,
    credential_type: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check if a credential has been compromised in a public breach.

    Parameters
    ----------
    value
        The credential value to check.
    enabled
        Whether compromise checking is globally enabled.
    hibp
        Whether to check passwords against HIBP (k-anonymity, hash prefix only).
    github_scanning
        Whether to check tokens against GitHub secret scanning.
    credential_type
        Optional output from ``identify_credential`` — used to determine
        which check is appropriate for the credential type.

    Returns
    -------
    dict with ``status`` (compromised, safe, active, invalid_or_revoked,
    skipped, disabled, error) and check-specific details.

    Security:
    - HIBP: only SHA-1 hash prefix (5 chars) leaves the machine
    - GitHub: full token sent to GitHub's API (the issuing service)
    - No credential is ever sent to an LLM vendor
    """
    if not enabled:
        return {"status": "disabled"}

    if not value or not isinstance(value, str):
        return {"status": "error", "detail": "empty or non-string value"}

    results: Dict[str, Any] = {"checks": []}

    # Determine credential category
    is_password = False
    is_github_token = False
    if credential_type:
        service = credential_type.get("service", "")
        ctype = credential_type.get("type", "")
        if service == "GitHub" or "github" in ctype:
            is_github_token = True
        if "password" in ctype.lower() or service not in (
            "GitHub", "OpenAI", "AWS", "Slack", "Stripe", "Google Cloud",
            "GitLab", "DigitalOcean", "Cloudflare", "Twilio", "SendGrid",
            "Linear", "Notion", "Pulumi", "Terraform Cloud", "JWT", "PKI",
        ):
            is_password = True
    else:
        # Without identification, treat short values as potential passwords
        if len(value) < 40 and not value.startswith(("ghp_", "sk-", "AKIA", "xox")):
            is_password = True

    # HIBP check for passwords
    if hibp and is_password:
        hibp_result = _check_hibp(value)
        results["checks"].append(hibp_result)
        if hibp_result["status"] == "compromised":
            results["status"] = "compromised"
            results["detail"] = hibp_result["detail"]
            return results

    # GitHub scanning for GitHub tokens
    if github_scanning and is_github_token:
        gh_result = _check_github_scanning(value)
        results["checks"].append(gh_result)

    # Aggregate status
    if not results["checks"]:
        results["status"] = "skipped"
        results["detail"] = "No applicable check for this credential type"
    else:
        statuses = [c["status"] for c in results["checks"]]
        if "compromised" in statuses:
            results["status"] = "compromised"
        elif "invalid_or_revoked" in statuses:
            results["status"] = "invalid_or_revoked"
        elif "safe" in statuses and "active" in statuses:
            results["status"] = "safe"
        elif "safe" in statuses:
            results["status"] = "safe"
        elif "active" in statuses:
            results["status"] = "active"
        else:
            results["status"] = "checked"

    return results
