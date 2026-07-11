// Score-component metadata. Engine rolls components up by min within each group,
// takes min(structural, visual) as Quality, then Total = Quality × Commitment.

import type { Scenario } from "./types";

export type ComponentGroup = "structural" | "visual";
export type Tier = "low" | "mid" | "high";

export interface ComponentMeta {
  label: string;
  group: ComponentGroup;
  measures: string;
  weakHint: string;
  /** Technical formula shown in the Step-4 row tooltip (carries the parser key). */
  formula: string;
}

export const COMPONENT_META: Record<string, ComponentMeta> = {
  speed_cluster: {
    label: "Speed",
    group: "structural",
    measures: "Push waves move at a steady, even pace.",
    weakHint: "The push waves are advancing at uneven speeds.",
    formula:
      "speed_cluster — how tightly the push legs' bars-per-pivot rates cluster. Higher = more uniform pacing.",
  },
  fib_push_pairs: {
    label: "Fibonacci",
    group: "structural",
    measures: "Wave-to-wave size ratios land near Fibonacci levels.",
    weakHint: "Wave-to-wave size ratios stray from Fibonacci levels.",
    formula:
      "fib_push_pairs — how close each push-pair ratio is to a Fibonacci level (in log space). Higher = closer to Fib.",
  },
  pull_depth_discipline: {
    label: "Pullback",
    group: "structural",
    measures: "Pullbacks retrace to a healthy, in-range depth.",
    weakHint: "Pullbacks are retracing too shallow or too deep.",
    formula:
      "pull_depth_discipline — how often pullbacks land inside the ideal retracement window. Higher = more disciplined pullbacks.",
  },
  pivot_sharpness: {
    label: "Pivots",
    group: "visual",
    measures: "Turning points stand out clearly from nearby bars.",
    weakHint: "Some turning points are hard to tell apart from nearby bars.",
    formula:
      "pivot_sharpness — how distinct each internal pivot is vs. nearby bars. Higher = the turning points are visually obvious.",
  },
  leg_smoothness: {
    label: "Smoothness",
    group: "visual",
    measures: "Each wave moves cleanly, without messy inner reversals.",
    weakHint: "One or more waves wobble instead of moving cleanly.",
    formula:
      "leg_smoothness — how monotone each leg moves (small inner reversals lower this). Higher = cleaner legs.",
  },
};

// Stable display order: Structure = Speed→Fib→Pullback, Visual = Pivots→Smoothness.
export const SLOT_ORDER: string[] = [
  "speed_cluster",
  "fib_push_pairs",
  "pull_depth_discipline",
  "pivot_sharpness",
  "leg_smoothness",
];

export const GROUP_META: Record<ComponentGroup, { title: string; question: string }> = {
  structural: { title: "Structure", question: "Is the wave geometry sound?" },
  visual: { title: "Visual", question: "Does it look clean on the chart?" },
};

// Slot bands wider than parent — MIN aggregation compresses parents.
const SLOT_BANDS: [number, number] = [0.4, 0.7];
const PARENT_BANDS: [number, number] = [0.25, 0.5];

export function scoreTier(value: number, opts: { parent: boolean }): Tier {
  const [mid, high] = opts.parent ? PARENT_BANDS : SLOT_BANDS;
  if (value < mid) return "low";
  if (value < high) return "mid";
  return "high";
}

// Maps band cutoffs to 35%/70% fill so bar length agrees with tier colour —
// raw scores compress low, so a "good" total would otherwise look near-empty.
export function calibratedPct(value: number, opts: { parent: boolean }): number {
  const v = Math.min(Math.max(value, 0), 1);
  const [mid, high] = opts.parent ? PARENT_BANDS : SLOT_BANDS;
  let frac: number;
  if (v < mid) {
    frac = (v / mid) * 0.35;
  } else if (v < high) {
    frac = 0.35 + ((v - mid) / (high - mid)) * 0.35;
  } else {
    frac = 0.7 + ((v - high) / (1 - high)) * 0.3;
  }
  return Math.round(frac * 100);
}

export const TIER_FG: Record<Tier, string> = {
  low: "var(--color-down)",
  mid: "var(--color-warn)",
  high: "var(--color-up)",
};

export interface SlotValue {
  key: string;
  meta: ComponentMeta;
  value: number;
}

export interface BottleneckResolution {
  kind: "progress" | "slot" | "none";
  progress: number | null;
  slot: SlotValue | null;
  slots: SlotValue[];
  total: number;
  quality: number | null;
}

/** Total = Quality × Progress; the lower factor drags the score. Quality is the
 * MIN of its slots, so when Quality drags, the weakest slot IS the bottleneck. */
export function resolveBottleneck(scenario: Scenario): BottleneckResolution {
  const c = scenario.score_components;
  const total = c.total ?? scenario.score;
  const quality = c.quality ?? null;
  const progress = c.commitment ?? null;
  const slots: SlotValue[] = SLOT_ORDER.filter((k) => k in c).map((k) => ({
    key: k,
    meta: COMPONENT_META[k],
    value: c[k],
  }));
  let kind: "progress" | "slot" | "none" = "none";
  let slot: SlotValue | null = null;
  if (slots.length > 0) {
    const weakest = slots.reduce((b, s) => (s.value < b.value ? s : b), slots[0]);
    if (progress !== null && quality !== null && progress < quality) {
      kind = "progress";
    } else {
      kind = "slot";
      slot = weakest;
    }
  }
  return { kind, progress, slot, slots, total, quality };
}
