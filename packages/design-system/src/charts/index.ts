// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The chart vocabulary.
 *
 * Each export serves one named job. Before adding a chart here, check that its
 * job is not already covered — the point of a small vocabulary is that a reader
 * learns each shape once, and that "this is a trend drawn as a ratio" stays a
 * reviewable claim rather than a matter of taste.
 */
export {
  SERIES_ORDER,
  seriesTone,
  thresholdTone,
  scale,
  fmt,
  toneClass,
} from './foundation'
export type { ChartJob, SeriesTone, StatusTone, ChartTone } from './foundation'

export { SlopeChart } from './SlopeChart'
export type { SlopeChartProps, SlopePoint } from './SlopeChart'

export { DotPlot } from './DotPlot'
export type { DotPlotProps, DotPlotItem } from './DotPlot'

export { StatusMatrix } from './StatusMatrix'
export type { StatusMatrixProps, MatrixItem, MatrixState } from './StatusMatrix'

export { RangeBar } from './RangeBar'
export type { RangeBarProps } from './RangeBar'

export { LifespanBars } from './LifespanBars'
export type { LifespanBarsProps, Lifespan } from './LifespanBars'

export { EstimateInterval, wilsonInterval } from './EstimateInterval'
export type { EstimateIntervalProps } from './EstimateInterval'

export { Sparkline } from './Sparkline'
export type { SparklineProps } from './Sparkline'

export { Waterfall } from './Waterfall'
export type { WaterfallProps, Stage } from './Waterfall'
