# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Credential format database — identify credential types from their shape.

This is the safe version of "looking to the internet": a curated database
of known credential formats, bundled with Halbert and updated with each
release. No secret leaves the tool — only the prefix or pattern shape is
matched against the database.

``identify_credential(value)`` returns a dict with:
- ``type``: the credential type (e.g. "github_pat", "aws_access_key")
- ``service``: the service name (e.g. "GitHub", "AWS")
- ``description``: human-readable description
- ``confidence``: "high" (prefix match) or "medium" (format match)

The database is structured as a list of CredentialFormat entries, each
with a name, service, prefix pattern, and optional validation info.

Sources: TruffleHog detectors, GitGuardian rules, detect-secrets patterns,
and vendor documentation. The database is curated, not auto-fetched —
auto-fetching is a separate feature (dynamic prefix database) that
updates this list periodically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CredentialFormat:
    """One known credential format."""

    name: str
    service: str
    description: str
    # Regex pattern to match the credential. Must use ^...$ or \b boundaries.
    pattern: re.Pattern
    # Whether this format has a known validation endpoint (for credential
    # validation feature — not used by identify_credential itself).
    validation_endpoint: str = ""
    # Whether this credential type is commonly found in public breaches.
    breach_risk: str = "medium"  # low, medium, high


# ---------------------------------------------------------------------------
# The credential format database
# ---------------------------------------------------------------------------

_CREDENTIAL_FORMATS: List[CredentialFormat] = [
    CredentialFormat(
        name="github_pat_classic",
        service="GitHub",
        description="GitHub Personal Access Token (classic)",
        pattern=re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="github_pat_fine_grained",
        service="GitHub",
        description="GitHub Fine-grained Personal Access Token",
        pattern=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="github_oauth",
        service="GitHub",
        description="GitHub OAuth token",
        pattern=re.compile(r"\bgho_[A-Za-z0-9]{36,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="github_user_server",
        service="GitHub",
        description="GitHub user-to-server token",
        pattern=re.compile(r"\bghu_[A-Za-z0-9]{36,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="github_server-user",
        service="GitHub",
        description="GitHub server-to-server token",
        pattern=re.compile(r"\bghs_[A-Za-z0-9]{36,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="github_refresh",
        service="GitHub",
        description="GitHub refresh token",
        pattern=re.compile(r"\bghr_[A-Za-z0-9]{76,}\b"),
        validation_endpoint="https://api.github.com/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="openai_api_key",
        service="OpenAI",
        description="OpenAI API key",
        pattern=re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        validation_endpoint="https://api.openai.com/v1/models",
        breach_risk="high",
    ),
    CredentialFormat(
        name="anthropic_api_key",
        service="Anthropic",
        description="Anthropic API key",
        pattern=re.compile(r"\bsk-ant-[A-Za-z0-9-_]{20,}\b"),
        validation_endpoint="https://api.anthropic.com/v1/messages",
        breach_risk="high",
    ),
    CredentialFormat(
        name="aws_access_key_id",
        service="AWS",
        description="AWS Access Key ID",
        pattern=re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        validation_endpoint="https://sts.amazonaws.com/",
        breach_risk="high",
    ),
    CredentialFormat(
        name="aws_secret_access_key",
        service="AWS",
        description="AWS Secret Access Key (40 base64 chars, no prefix — medium confidence only)",
        # This pattern is deliberately broad and low-priority. It matches
        # any 40-char base64 string, which could be many things. It only
        # fires as a last resort, and only when the key name context
        # suggests AWS (the caller can check key == "aws_secret_access_key").
        # Listed AFTER all prefix-based formats so they take priority.
        pattern=re.compile(r"^[A-Za-z0-9/+=]{40}$"),
        breach_risk="high",
    ),
    CredentialFormat(
        name="slack_bot_token",
        service="Slack",
        description="Slack Bot token",
        pattern=re.compile(r"\bxoxb-[A-Za-z0-9-]{10,}\b"),
        validation_endpoint="https://slack.com/api/auth.test",
        breach_risk="high",
    ),
    CredentialFormat(
        name="slack_app_token",
        service="Slack",
        description="Slack App token",
        pattern=re.compile(r"\bxapp-[A-Za-z0-9-]{10,}\b"),
        breach_risk="high",
    ),
    CredentialFormat(
        name="slack_user_token",
        service="Slack",
        description="Slack User token",
        pattern=re.compile(r"\bxoxp-[A-Za-z0-9-]{10,}\b"),
        validation_endpoint="https://slack.com/api/auth.test",
        breach_risk="high",
    ),
    CredentialFormat(
        name="google_api_key",
        service="Google Cloud",
        description="Google API key",
        pattern=re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"),
        validation_endpoint="https://www.googleapis.com/oauth2/v1/tokeninfo",
        breach_risk="high",
    ),
    CredentialFormat(
        name="stripe_secret_key",
        service="Stripe",
        description="Stripe Secret API key",
        pattern=re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"),
        validation_endpoint="https://api.stripe.com/v1/balance",
        breach_risk="high",
    ),
    CredentialFormat(
        name="stripe_publishable_key",
        service="Stripe",
        description="Stripe Publishable key (not secret, but flagged for awareness)",
        pattern=re.compile(r"\bpk_live_[A-Za-z0-9]{24,}\b"),
        breach_risk="low",
    ),
    CredentialFormat(
        name="stripe_restricted_key",
        service="Stripe",
        description="Stripe Restricted key",
        pattern=re.compile(r"\brk_live_[A-Za-z0-9]{24,}\b"),
        validation_endpoint="https://api.stripe.com/v1/balance",
        breach_risk="high",
    ),
    CredentialFormat(
        name="gitlab_token",
        service="GitLab",
        description="GitLab Personal Access Token",
        pattern=re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
        validation_endpoint="https://gitlab.com/api/v4/user",
        breach_risk="high",
    ),
    CredentialFormat(
        name="gitlab_runner_token",
        service="GitLab",
        description="GitLab Runner registration token",
        pattern=re.compile(r"\bGR1348941[A-Za-z0-9_-]{20,}\b"),
        breach_risk="high",
    ),
    CredentialFormat(
        name="digitalocean_token",
        service="DigitalOcean",
        description="DigitalOcean API token",
        pattern=re.compile(r"\bdop_v1_[a-f0-9]{64}\b"),
        validation_endpoint="https://api.digitalocean.com/v2/account",
        breach_risk="high",
    ),
    CredentialFormat(
        name="cloudflare_api_token",
        service="Cloudflare",
        description="Cloudflare API token (40 chars, no prefix — medium confidence only)",
        # Cloudflare tokens are 40 chars of [A-Za-z0-9_-] with no prefix.
        # This is too broad to be useful for identification without key
        # context. Anchored to avoid matching substrings.
        pattern=re.compile(r"^[A-Za-z0-9_-]{40}$"),
        validation_endpoint="https://api.cloudflare.com/client/v4/user/tokens/verify",
        breach_risk="high",
    ),
    CredentialFormat(
        name="twilio_api_key",
        service="Twilio",
        description="Twilio API Key",
        pattern=re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
        breach_risk="high",
    ),
    CredentialFormat(
        name="sendgrid_api_key",
        service="SendGrid",
        description="SendGrid API key",
        pattern=re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b"),
        validation_endpoint="https://api.sendgrid.com/v3/scopes",
        breach_risk="high",
    ),
    CredentialFormat(
        name="linear_api_key",
        service="Linear",
        description="Linear API key",
        pattern=re.compile(r"\blin_api_[A-Za-z0-9]{40}\b"),
        validation_endpoint="https://api.linear.app/graphql",
        breach_risk="medium",
    ),
    CredentialFormat(
        name="notion_api_key",
        service="Notion",
        description="Notion integration token",
        pattern=re.compile(r"\bsecret_[A-Za-z0-9]{43}\b"),
        validation_endpoint="https://api.notion.com/v1/users/me",
        breach_risk="medium",
    ),
    CredentialFormat(
        name="pulumi_access_token",
        service="Pulumi",
        description="Pulumi access token",
        pattern=re.compile(r"\bpul-[a-f0-9]{40}\b"),
        validation_endpoint="https://api.pulumi.com/api/user",
        breach_risk="medium",
    ),
    CredentialFormat(
        name="terraform_token",
        service="Terraform Cloud",
        description="Terraform Cloud API token",
        pattern=re.compile(r"\b[a-zA-Z0-9]{14}\.[a-zA-Z0-9]{36}\b"),
        validation_endpoint="https://app.terraform.io/api/v2/account/details",
        breach_risk="medium",
    ),
    CredentialFormat(
        name="jwt_token",
        service="JWT",
        description="JSON Web Token (three base64 segments separated by dots)",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        breach_risk="medium",
    ),
    CredentialFormat(
        name="pem_private_key",
        service="PKI",
        description="PEM-encoded private key block",
        pattern=re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        breach_risk="high",
    ),
]


def identify_credential(value: str) -> Optional[Dict[str, Any]]:
    """Identify a credential's type from its format.

    Returns a dict with ``type``, ``service``, ``description``, ``confidence``,
    and ``breach_risk`` if the value matches a known credential format.
    Returns ``None`` if no format matches.

    No secret leaves this function — only the value's shape is matched
    against the format database. The value itself is never sent anywhere.

    Confidence levels:
    - ``high``: the value has a unique prefix (ghp_, sk-, AKIA, etc.) that
      unambiguously identifies the credential type.
    - ``medium``: the value matches a format pattern but without a unique
      prefix (e.g. 40 base64 chars could be an AWS secret key or a random
      string). These matches are advisory, not definitive.
    """
    if not value or not isinstance(value, str):
        return None

    text = str(value)

    # First pass: look for prefix-based matches (high confidence)
    for fmt in _CREDENTIAL_FORMATS:
        if fmt.pattern.search(text):
            # Prefix-based formats have unique identifiers in the value
            # itself (ghp_, sk-, AKIA, xox, AIza, etc.). Format-only
            # patterns (AWS secret key, Cloudflare) are medium confidence
            # because they match any string of the right length.
            prefix_based = any(
                fmt.name.startswith(prefix)
                for prefix in ("github_", "openai_", "anthropic_",
                               "slack_", "google_", "stripe_", "gitlab_",
                               "digitalocean_", "twilio_", "sendgrid_",
                               "linear_", "notion_", "pulumi_", "jwt_",
                               "pem_", "aws_access_key_id")
            )
            confidence = "high" if prefix_based else "medium"
            return {
                "type": fmt.name,
                "service": fmt.service,
                "description": fmt.description,
                "confidence": confidence,
                "breach_risk": fmt.breach_risk,
                "validation_available": bool(fmt.validation_endpoint),
            }

    return None


def list_known_formats() -> List[Dict[str, Any]]:
    """List all known credential formats (for documentation/debugging)."""
    return [
        {
            "name": fmt.name,
            "service": fmt.service,
            "description": fmt.description,
            "breach_risk": fmt.breach_risk,
            "validation_available": bool(fmt.validation_endpoint),
        }
        for fmt in _CREDENTIAL_FORMATS
    ]
