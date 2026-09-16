// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
export { AudioReactiveHalbertMark, THINKING_BULGES } from './AudioReactiveHalbertMark'
export type {
  AudioReactiveHalbertMarkProps,
  VoiceVisualState,
} from './AudioReactiveHalbertMark'
export { VoiceModeLoop, VOICE_MODE_LOOP } from './VoiceModeLoop'
export type { VoiceModeLoopProps } from './VoiceModeLoop'
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
  DEFAULT_FFT_SIZE,
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
export { Listener, LISTENING } from './listening'
export {
  MARK,
  DEFAULT_DENSITY,
  STROKE_WIDTH,
  laneCount,
  tineCount,
  TINE_AMPLITUDES,
  TINE_MODES,
  MAX_DISPLACEMENT_MULTIPLIER,
  laneRadius,
  laneTop,
  tineLength,
  tineLengths,
  tinePathD,
  bulgePolygonPoints,
  staticTinePaths,
} from './geometry'
export type {
  BulgeOptions,
  BulgeSpec,
  Retraction,
  TinePathOptions,
  VoiceDensity,
} from './geometry'
