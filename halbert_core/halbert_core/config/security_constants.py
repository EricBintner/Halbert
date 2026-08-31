# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Security-enforcement constants shared across Halbert's surfaces.

The dashboard route and the MCP server both enforce the Tier 2 unlock
phrase; both import it from here so the two surfaces can never drift
apart. The phrase is friction, not a secret — it is rendered in the
dashboard's confirmation modal by design and lives in an open-source
repo. Its value is that a human must retype it for any change that
increases secret exposure. Never echo it in an error response: a 403
that repeats the challenge hands an agent driving the API the answer
to its own question.

``EGRESS_ACK_FIELD`` is the contract between ``config.queries`` and
``mcp.response``: ``get_config_value`` sets it to ``True`` on a payload
only after verifying tier + acknowledgment + TTL, and the MCP choke
point lets that dict's ``value`` field cross unredacted when it sees
the marker. No other code path may set it.
"""
from __future__ import annotations

# Confirmation phrase for any security change that increases secret
# exposure (unlock, hatch addition, expiry extension).
UNLOCK_PHRASE = "EXPOSE SECRETS"

# Marker field on a config-value payload whose raw value legitimately
# cleared the Tier 2 acknowledgment check. See module docstring — the
# only setter is config.queries.get_config_value.
EGRESS_ACK_FIELD = "_egress_ack"