# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision capture subsystem: screen and webcam frames for the agent.

Local-only. Frames are captured on demand (user button or agent tool call),
encoded to JPEG, and sent to the configured vision model. Nothing is stored
to disk unless the user explicitly saves a conversation with images.
"""
