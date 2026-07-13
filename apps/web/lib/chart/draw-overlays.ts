import {
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import {
  ROLE_COLOR,
  SPINE_COLOR,
  collectLeafWaves,
  dedupeByTime,
  toUTC,
  type MarkerSpec,
} from "./helpers";
import type { ChartLayerKey } from "../chart-store";
import { drawableLegs, isDrillable, roleShort, scopeLegs } from "../scenario-format";
import type { Bar, Pivot, Scenario, Wave } from "../types";

export type OverlayLayers = Pick<
  Record<ChartLayerKey, boolean>,
  "raw_zigzag" | "trendline" | "in_progress"
>;

export interface SubLegSeries {
  rootRole: string;
  series: ISeriesApi<"Line">;
  baseColor: string;
}

export interface OverlayResult {
  overlays: ISeriesApi<"Line">[];
  subLegSeries: SubLegSeries[];
  markers: MarkerSpec[];
}

// Compare spine + markers share one hue so they read as one count.
const COMPARE_COLOR = "rgba(6, 182, 212, 0.7)";

// One source of truth for every fixed line-overlay style. Exported so tests can
// select a series by identity (opts === OVERLAY_STYLE.x), decoupling assertions
// from the palette. Sub-wave dim lines are role-derived, so they stay inline.
export const OVERLAY_STYLE = {
  backbone: {
    color: "rgba(148, 163, 184, 0.55)",
    lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
  },
  rawZigzag: {
    color: "rgba(245, 158, 11, 0.55)",
    lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  },
  spine: {
    color: SPINE_COLOR,
    lineWidth: 3, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  },
  trendline: {
    color: "#06b6d4",
    lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  },
  compareSpine: {
    color: COMPARE_COLOR,
    lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  },
  projection: {
    color: "rgba(56, 189, 248, 0.85)",
    lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  },
} satisfies Record<string, Parameters<IChartApi["addSeries"]>[1]>;

// Returns the created series + markers so the caller owns their removal.
export function drawOverlays(
  chart: IChartApi,
  {
    bars,
    activePivots,
    rawPivots,
    selectedScenario,
    compareScenario,
    drillPath,
    layers,
  }: {
    bars: Bar[];
    activePivots: Pivot[];
    rawPivots: Pivot[];
    selectedScenario: Scenario | null;
    compareScenario: Scenario | null;
    drillPath: number[];
    layers: OverlayLayers;
  },
): OverlayResult {
  const overlays: ISeriesApi<"Line">[] = [];
  const subLegSeries: SubLegSeries[] = [];
  const markers: MarkerSpec[] = [];

  const addLine = (opts: Parameters<IChartApi["addSeries"]>[1]): ISeriesApi<"Line"> => {
    const s = chart.addSeries(LineSeries, opts);
    overlays.push(s);
    return s;
  };

  // Backbone ZigZag (always-on dashed reference).
  if (activePivots.length >= 2) {
    const zigzag = addLine(OVERLAY_STYLE.backbone);
    zigzag.setData(activePivots.map((p) => ({ time: toUTC(p.time), value: p.price })));
  }

  if (layers.raw_zigzag && rawPivots.length >= 2) {
    const raw = addLine(OVERLAY_STYLE.rawZigzag);
    // dedupe REQUIRED: pre-spacing-filter raw pivots can cluster on one bar →
    // identical timestamps, which crash the chart. (activePivots can't.)
    raw.setData(
      dedupeByTime(rawPivots.map((p) => ({ time: toUTC(p.time), value: p.price }))),
    );
  }

  // Selected scenario: one amber spine through root legs (role identity carried
  // by endpoint markers, not per-segment hue) + dimmed sub-waves + markers.
  if (selectedScenario) {
    const rLegs = scopeLegs(selectedScenario, drillPath);

    // Dim sub-wave layer — drawn FIRST so the spine sits on top.
    for (const rootLeg of rLegs) {
      if (rootLeg.children.length === 0) continue;
      const innerLeaves = collectLeafWaves(rootLeg);
      // collectLeafWaves returns [rootLeg] when the leg is itself a leaf — skip.
      const nestedOnly = innerLeaves.filter((leaf) => leaf !== rootLeg);
      for (const leaf of nestedOnly) {
        const baseColor = ROLE_COLOR[leaf.role] ?? "#94a3b8";
        const subSeries = chart.addSeries(LineSeries, {
          color: `${baseColor}55`,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const points = [
          { time: toUTC(leaf.span_start.time), value: leaf.span_start.price },
          ...leaf.segments.map((s) => ({ time: toUTC(s.end.time), value: s.end.price })),
        ];
        const deduped = dedupeByTime(points);
        subSeries.setData(deduped);
        subLegSeries.push({
          rootRole: rootLeg.role,
          series: subSeries,
          baseColor,
        });
      }
    }

    if (rLegs.length > 0) {
      const spine = addLine(OVERLAY_STYLE.spine);
      const spinePoints = [
        { time: toUTC(rLegs[0].span_start.time), value: rLegs[0].span_start.price },
        ...rLegs.map((l) => ({
          time: toUTC(l.span_end.time),
          value: l.span_end.price,
        })),
      ];
      const deduped = dedupeByTime(spinePoints);
      spine.setData(deduped);
    }

    // Role markers at root endpoints.
    for (const rootLeg of rLegs) {
      const color = ROLE_COLOR[rootLeg.role] ?? "#94a3b8";
      const isHigh = rootLeg.span_end.kind === "high";
      markers.push({
        time: toUTC(rootLeg.span_end.time),
        position: isHigh ? "aboveBar" : "belowBar",
        color,
        shape: isHigh ? "arrowDown" : "arrowUp",
        // ◆ flags a drillable sub-pattern (no diamond marker shape exists).
        text: roleShort(rootLeg.role) + (isDrillable(rootLeg) ? " ◆" : ""),
      });
    }

    // S2–S4 trendline (5-wave only).
    if (layers.trendline && selectedScenario.family.startsWith("5W")) {
      const s2 = rLegs.find((l) => l.role === "s2");
      const s4 = rLegs.find((l) => l.role === "s4");
      if (s2 && s4) {
        const trendline = addLine(OVERLAY_STYLE.trendline);
        const lastBarTime = bars.length > 0 ? toUTC(bars[bars.length - 1].time) : null;
        const points = [
          { time: toUTC(s2.span_end.time), value: s2.span_end.price },
          { time: toUTC(s4.span_end.time), value: s4.span_end.price },
        ];
        if (lastBarTime && lastBarTime > toUTC(s4.span_end.time)) {
          const t1 = toUTC(s2.span_end.time);
          const t2 = toUTC(s4.span_end.time);
          const dt = t2 - t1;
          // dt=0 (W2/W4 same timestamp) would make extendedP NaN — skip the point.
          if (dt > 0) {
            const dp = s4.span_end.price - s2.span_end.price;
            const extendedP = s4.span_end.price + (dp / dt) * (lastBarTime - t2);
            points.push({ time: lastBarTime, value: extendedP });
          }
        }
        trendline.setData(points);
      }
    }
  }

  // Compare overlay — always its root count; drilling applies only to primary.
  if (compareScenario && compareScenario.id !== selectedScenario?.id) {
    const cmpRootLegs = drawableLegs(compareScenario.root);
    if (cmpRootLegs.length > 0) {
      const cmpSpine = addLine(OVERLAY_STYLE.compareSpine);
      const points = [
        { time: toUTC(cmpRootLegs[0].span_start.time), value: cmpRootLegs[0].span_start.price },
        ...cmpRootLegs.map((l) => ({
          time: toUTC(l.span_end.time),
          value: l.span_end.price,
        })),
      ];
      const deduped = dedupeByTime(points);
      cmpSpine.setData(deduped);
    }

    // Circles, not arrows, so they don't compete with the primary's markers.
    for (const rootLeg of cmpRootLegs) {
      markers.push({
        time: toUTC(rootLeg.span_end.time),
        position: rootLeg.span_end.kind === "high" ? "aboveBar" : "belowBar",
        color: COMPARE_COLOR,
        shape: "circle",
        text: "",
      });
    }
  }

  // In-progress projection: from the last completed root leg, walk open_subtree
  // DFS appending each leaf span_end so the partial sub-pattern shows instead of
  // a straight line. Falls back to a last-bar line when no open_subtree.
  if (
    layers.in_progress &&
    drillPath.length === 0 && // Streamlit hides the projection while drilled
    selectedScenario &&
    !selectedScenario.is_complete &&
    bars.length > 0
  ) {
    const rLegs = scopeLegs(selectedScenario, drillPath);
    const lastClosed = rLegs[rLegs.length - 1];
    if (lastClosed?.span_end) {
      const startPt = {
        time: toUTC(lastClosed.span_end.time),
        value: lastClosed.span_end.price,
      };

      // Leaf span_ends only, so the polyline traces the most granular sub-count.
      const subtreePts: Array<{ time: UTCTimestamp; value: number }> = [];
      const walk = (node: Wave): void => {
        if (node.children.length > 0) {
          for (const c of node.children) walk(c);
        } else if (node.span_end) {
          subtreePts.push({
            time: toUTC(node.span_end.time),
            value: node.span_end.price,
          });
        }
      };
      if (selectedScenario.open_subtree) walk(selectedScenario.open_subtree);

      let candidatePts: Array<{ time: UTCTimestamp; value: number }> = [];
      if (subtreePts.length > 0) {
        candidatePts = [startPt, ...subtreePts];
      } else {
        const lastBar = bars[bars.length - 1];
        if (toUTC(lastBar.time) > toUTC(lastClosed.span_end.time)) {
          candidatePts = [
            startPt,
            { time: toUTC(lastBar.time), value: lastBar.close },
          ];
        }
      }

      // First subtree point may equal startPt when the outermost leaf coincides
      // with the last completed leg's endpoint.
      const dedup = dedupeByTime(candidatePts);
      if (dedup.length >= 2) {
        const projection = addLine(OVERLAY_STYLE.projection);
        projection.setData(dedup);
      }
    }
  }

  return { overlays, subLegSeries, markers };
}
