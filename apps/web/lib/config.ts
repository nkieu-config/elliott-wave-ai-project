import { parseAsFloat, parseAsInteger, parseAsString, parseAsStringLiteral } from "nuqs";
import type { PipelineConfig } from "./api";
import type { ScaleMode } from "./types";

export const TIMEFRAMES = ["day", "week", "month"] as const;
// satisfies keeps the const in lockstep with the canonical ScaleMode type.
export const SCALE_MODES = ["linear", "log"] as const satisfies readonly ScaleMode[];
export const PERIODS = ["2y", "5y", "10y", "max"] as const;
export const COMMITMENT_CURVES = ["off", "sqrt", "linear"] as const;

export type Timeframe = (typeof TIMEFRAMES)[number];
export type { ScaleMode };

// meta.config echoes the run's scale_mode as a plain `string` (see lib/types.ts);
// fall back to the default rather than hand a bad literal to the chart.
export function asScaleMode(value: string): ScaleMode {
  return (SCALE_MODES as readonly string[]).includes(value)
    ? (value as ScaleMode)
    : CONFIG_DEFAULTS.scale_mode;
}
export type Period = (typeof PERIODS)[number];
export type CommitmentCurve = (typeof COMMITMENT_CURVES)[number];

export const CONFIG_DEFAULTS: Required<PipelineConfig> = {
  symbol: "DDOG",
  period: "max",
  timeframe: "week",
  scale_mode: "linear",
  atr_period: 14,
  atr_multiplier: 3.0,
  atr_floor: 0.1,
  min_bars_between: 4,
  k_sigma: 0.5,
  log_tol_fib: 0.05,
  pull_depth_lo: 0.382,
  pull_depth_hi: 0.618,
  pull_depth_tol: 0.15,
  pivot_window: 2,
  commitment_curve: "linear",
};

export const configParsers = {
  symbol: parseAsString.withDefault(CONFIG_DEFAULTS.symbol),
  period: parseAsStringLiteral(PERIODS).withDefault(CONFIG_DEFAULTS.period),
  timeframe: parseAsStringLiteral(TIMEFRAMES).withDefault(CONFIG_DEFAULTS.timeframe),
  scale_mode: parseAsStringLiteral(SCALE_MODES).withDefault(CONFIG_DEFAULTS.scale_mode),
  atr_period: parseAsInteger.withDefault(CONFIG_DEFAULTS.atr_period),
  atr_multiplier: parseAsFloat.withDefault(CONFIG_DEFAULTS.atr_multiplier),
  atr_floor: parseAsFloat.withDefault(CONFIG_DEFAULTS.atr_floor),
  min_bars_between: parseAsInteger.withDefault(CONFIG_DEFAULTS.min_bars_between),
  k_sigma: parseAsFloat.withDefault(CONFIG_DEFAULTS.k_sigma),
  log_tol_fib: parseAsFloat.withDefault(CONFIG_DEFAULTS.log_tol_fib),
  pull_depth_lo: parseAsFloat.withDefault(CONFIG_DEFAULTS.pull_depth_lo),
  pull_depth_hi: parseAsFloat.withDefault(CONFIG_DEFAULTS.pull_depth_hi),
  pull_depth_tol: parseAsFloat.withDefault(CONFIG_DEFAULTS.pull_depth_tol),
  pivot_window: parseAsInteger.withDefault(CONFIG_DEFAULTS.pivot_window),
  commitment_curve: parseAsStringLiteral(COMMITMENT_CURVES).withDefault(
    CONFIG_DEFAULTS.commitment_curve,
  ),
};
