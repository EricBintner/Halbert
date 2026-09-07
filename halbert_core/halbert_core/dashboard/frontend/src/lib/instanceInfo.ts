// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The shape of GET /api/instance/info — this machine's identity.
 *
 * Lives in lib (not in the component that reads it) because the shell and
 * the rail both need it: Layout gates the rail's items on `features`, and
 * EntityNodeBlock names the serving node. It used to be exported from
 * PresencePill.tsx; the pill's split (§5R.3 N1) moved it out so the shell
 * does not import a top-bar component for a type.
 */

/** The session a guest persona is fronting for — /api/instance/info. */
export interface FrontingSession {
  session_id: string
  name: string
  offered_by: string
  offered_by_name: string
  started_at: string
  seconds_until_expiry: number
  active: boolean
  end_reason: string | null
  /** Where the guest's own memory lives, when it was pulled from a home. */
  home?: { base_url: string; persona_id: string; label: string } | null
}

export interface InstanceInfo {
  /** Non-null while a borrowed face is on. */
  fronting?: FrontingSession | null
  persona_id: string
  scene_context: string
  role: 'host' | 'home'
  variant: string
  display_name: string
  port: number
  features: {
    home: boolean
    gpu: boolean
    development: boolean
    wyoming_port: number
  }
  data_dir: string
  config_dir: string
  body_name: string
  singular: boolean
}