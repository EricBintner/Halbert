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
export { createSpeechBurstSource } from './demo'
export type { SpeechBurstOptions } from './demo'
export {
  ResonatorBank,
  SWELL_SPRING,
  STRING_LADDER,
  STRING_TUNING,
  RING_MAX,
  FIXED_TIMESTEP,
  stringSpring,
  tuneStrings,
} from './springs'
export type { SpringParams, StringTuning } from './springs'
export {
  STATE_EXCITATION,
  ONSET_FLOOR,
  IDLE_PLUCK,
  STRUM,
  OnsetPlucker,
  PluckQueue,
  IdlePlucker,
  strum,
} from './excitation'
export type { StateExcitation, ScheduledPluck } from './excitation'
export {
  MARK,
  laneCount,
  tineCount,
  TINE_AMPLITUDES,
  TINE_MODES,
  MAX_DISPLACEMENT_MULTIPLIER,
  laneRadius,
  laneTop,
  tinePathD,
  staticTinePaths,
} from './geometry'
export type { TinePathOptions, TravelingBulge, VoiceDensity } from './geometry'
