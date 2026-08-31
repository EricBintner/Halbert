// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
export { AudioReactiveHalbertMark } from './AudioReactiveHalbertMark'
export type {
  AudioReactiveHalbertMarkProps,
  VoiceVisualState,
} from './AudioReactiveHalbertMark'
export type {
  AudioEnergySource,
  ByteFrequencyNode,
  MediaStreamAnalyserOptions,
} from './spectrum'
export {
  SyntheticEnergySource,
  IdleBreathingSource,
  createAnalyserEnergySource,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
  tineEnergies,
  binRangesFor,
  TINE_BAND_HZ,
  TINE_BIN_RANGES_16K_64,
  SUB_BASS_ATTENUATION,
} from './spectrum'
export { ResonatorBank, SPRING_DEFAULTS, FIXED_TIMESTEP } from './springs'
export {
  MARK,
  TINE_COUNT,
  TINE_AMPLITUDES,
  TINE_MODES,
  TINE_DRIFT,
  laneRadius,
  laneTop,
  tinePathD,
  STATIC_TINE_PATHS,
} from './geometry'
