# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Frigate NVR integration — camera event streaming and on-demand queries.

Connects to a Frigate instance via REST (snapshots, clips, event queries)
and MQTT (real-time detection events → cognition). Mirrors the Home
Assistant integration pattern: config → client → tools → event mapper.
"""
