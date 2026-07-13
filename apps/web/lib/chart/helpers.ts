import type { SeriesMarker, Time, UTCTimestamp } from "lightweight-charts";
import { gregorianLocale } from "../resolve-locale";
import { drawableLegs, prettyFamilyUpper } from "../scenario-format";
import type { Bar, ClosedWave, Scenario, Wave } from "../types";

// Pipeline sends tz-less ISO datetimes; force UTC so the calendar date is
// identical for every viewer and matches the UTC axis. Honour an explicit
// offset/Z if present.
export const toUTC = (iso: string): UTCTimestamp => {
  const hasTz = /[zZ]$|[+-]\d\d:?\d\d$/.test(iso);
  const normalized = iso.includes("T") && !hasTz ? `${iso}Z` : iso;
  return Math.floor(Date.parse(normalized) / 1000) as UTCTimestamp;
};

// toUTC typed as plain number for arithmetic — drops the repeated `as number`.
export const toUTCNum = (iso: string): number => toUTC(iso);

// lightweight-charts rejects duplicate/non-increasing times; adjacent legs
// sharing a pivot emit a repeated endpoint.
export function dedupeByTime<T extends { time: UTCTimestamp }>(points: T[]): T[] {
  return points.filter((p, i) => i === 0 || p.time !== points[i - 1].time);
}

// Hardcoded (not --color-role-* CSS vars) because lightweight-charts paints to
// canvas and needs literal strings; keep in lockstep with globals.css.
export const ROLE_COLOR: Record<string, string> = {
  anchor: "#a855f7",
  s1: "#38bdf8",
  s2: "#fbbf24",
  s3: "#10b981",
  s4: "#f43f5e",
  s5: "#a855f7",
  link: "#facc15",
};
export const LEGEND_ROLES = ["s1", "s2", "s3", "s4", "s5"] as const;
export type LegendRole = (typeof LEGEND_ROLES)[number];

export const SPINE_COLOR = "#fbbf24";

export function collectLeafWaves(node: Wave, out: Wave[] = []): Wave[] {
  const isDrawable = node.role !== "anchor" && node.span_end && node.segments.length > 0;
  const drawableChildren = node.children.filter(
    (c) => c.role !== "anchor" && c.span_end && c.segments.length > 0,
  );
  if (isDrawable && drawableChildren.length === 0) out.push(node);
  for (const child of node.children) collectLeafWaves(child, out);
  return out;
}

export interface PerLegEntry {
  leg_idx: number;
  ratio: number;
}

// The engine derives leg_idx over CLOSED legs only (open legs are dropped before
// scoring — see engine/parser/scoring/components.py), so this must index
// drawableLegs, not root.children: an open leg ahead of the worst one would
// otherwise shift the band onto the wrong leg.
export function resolveBottleneckLeg(
  scenario: Scenario,
  perLeg: PerLegEntry[],
): { leg: ClosedWave; legIdx: number } | null {
  if (perLeg.length === 0) return null;
  const worst = perLeg.reduce((best, e) => (e.ratio > best.ratio ? e : best), perLeg[0]);
  const leg = drawableLegs(scenario.root)[worst.leg_idx];
  if (!leg) return null;
  return { leg, legIdx: worst.leg_idx };
}

export type MarkerSpec = SeriesMarker<Time>;

export interface CrosshairData {
  time: number;
  bar: Bar;
  role: string | null;
  x: number;
  y: number;
  /** Captured in the crosshair handler so the tooltip never reads layout during render. */
  w: number;
}

// Locale from the caller; en-US fallback for tests/non-request contexts.
export function fmtPrice(n: number, locale = "en-US"): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString(locale, { maximumFractionDigits: 0 });
  if (Math.abs(n) >= 1) return n.toLocaleString(locale, { maximumFractionDigits: 2 });
  return n.toLocaleString(locale, { maximumFractionDigits: 4 });
}

// Wrap the chart canvas with header + footer so the exported PNG is self-describing.
export function composeWatermark(
  chartCanvas: HTMLCanvasElement,
  ctx: {
    symbol: string;
    scaleMode: string;
    scenario: Scenario | null;
    compare: Scenario | null;
    locale: string;
  },
): HTMLCanvasElement {
  const headerH = 56;
  const footerH = 22;
  const w = chartCanvas.width;
  const h = chartCanvas.height;

  const out = document.createElement("canvas");
  out.width = w;
  out.height = h + headerH + footerH;
  const g = out.getContext("2d");
  if (!g) return chartCanvas;

  g.fillStyle = "#070a12";
  g.fillRect(0, 0, out.width, out.height);
  g.drawImage(chartCanvas, 0, headerH);

  // Hairlines above/below the chart.
  g.fillStyle = "rgba(148, 163, 184, 0.15)";
  g.fillRect(0, headerH - 1, out.width, 1);
  g.fillRect(0, h + headerH, out.width, 1);

  g.fillStyle = "#f1f5f9";
  g.font = '700 22px ui-monospace, "JetBrains Mono", "SF Mono", monospace';
  g.textBaseline = "middle";
  g.fillText(ctx.symbol, 18, headerH / 2);

  const symbolW = g.measureText(ctx.symbol).width;
  g.fillStyle = "#64748b";
  g.font = '500 12px ui-monospace, "JetBrains Mono", monospace';
  g.fillText(`/ ${ctx.scaleMode.toUpperCase()}`, 18 + symbolW + 10, headerH / 2);

  if (ctx.scenario) {
    const family = prettyFamilyUpper(ctx.scenario.family);
    const score = ctx.scenario.score.toFixed(3);
    const text = `${family} · ${score}`;
    g.fillStyle = "#34d399";
    g.font = '600 13px ui-monospace, "JetBrains Mono", monospace';
    const textW = g.measureText(text).width;
    g.textAlign = "right";
    g.fillText(text, w - 18, headerH / 2);
    g.textAlign = "left";

    if (ctx.compare) {
      const cmp = `vs ${prettyFamilyUpper(ctx.compare.family)} · ${ctx.compare.score.toFixed(3)}`;
      g.fillStyle = "#a855f7";
      g.font = '500 10px ui-monospace, "JetBrains Mono", monospace';
      g.textAlign = "right";
      g.fillText(cmp, w - 18 - textW - 12, headerH / 2);
      g.textAlign = "left";
    }
  }

  g.fillStyle = "#64748b";
  g.font = '500 10px ui-sans-serif, system-ui, sans-serif';
  g.textBaseline = "middle";
  g.fillText("Elliott Wave Lab", 18, h + headerH + footerH / 2);
  const dateStr = new Date().toLocaleDateString(gregorianLocale(ctx.locale), {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  g.textAlign = "right";
  g.fillText(dateStr, w - 18, h + headerH + footerH / 2);

  return out;
}
