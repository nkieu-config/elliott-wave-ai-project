"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { composeWatermark, type LegendRole } from "@/lib/chart/helpers";
import { useLocale } from "@/lib/locale";
import { TOAST_DURATION } from "@/lib/ui";
import type { ChartLayerKey } from "@/lib/chart-store";
import { prettyFamily } from "@/lib/scenario-format";
import type { Bar, Layer1Result, Pivot, Scenario, ScaleMode } from "@/lib/types";
import { ChartLegend, ChartToolbar, TimeChips } from "@/components/chart/chart-chrome";
import { CrosshairTooltip } from "@/components/chart/crosshair-tooltip";
import { useWaveChart } from "@/components/chart/use-wave-chart";

interface Props {
  symbol: string;
  scaleMode: ScaleMode;
  bars: Bar[];
  activePivots: Pivot[];
  rawPivots: Pivot[];
  selectedScenario: Scenario | null;
  compareScenario?: Scenario | null;
  onClearCompare?: () => void;
  onSwapCompare?: () => void;
  layers: Record<ChartLayerKey, boolean>;
  layer1: Layer1Result | null;
  /** Drill scope — indices into successive `drawableLegs`. Empty = root. */
  drillPath: number[];
  onDrill: (path: number[]) => void;
}

export function WaveChart({
  symbol,
  scaleMode,
  bars,
  activePivots,
  rawPivots,
  selectedScenario,
  compareScenario = null,
  onClearCompare,
  onSwapCompare,
  layers,
  layer1,
  drillPath,
  onDrill,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const locale = useLocale();

  // isolatedRole sticky (tap), hoveredRole transient (mouse) — active = either,
  // so touch users without hover can still highlight.
  const [hoveredRole, setHoveredRole] = useState<LegendRole | null>(null);
  const [isolatedRole, setIsolatedRole] = useState<LegendRole | null>(null);
  const activeRole = isolatedRole ?? hoveredRole;

  // Reset isolation on scenario change — a stale "isolated:s3" on a scenario
  // lacking an S3 leg would dim everything.
  useEffect(() => {
    setIsolatedRole(null);
    setHoveredRole(null);
  }, [selectedScenario?.id]);

  const {
    hasDrillable,
    bottleneckRect,
    latestX,
    crosshair,
    canSetRange,
    showRange,
    takeScreenshot,
  } = useWaveChart({
    containerRef,
    locale,
    scaleMode,
    bars,
    activePivots,
    rawPivots,
    selectedScenario,
    compareScenario,
    drillPath,
    onDrill,
    layers,
    layer1,
    activeRole,
  });

  const onExport = useCallback(() => {
    const chartCanvas = takeScreenshot();
    if (!chartCanvas) return;
    try {
      const dateStr = new Date().toISOString().slice(0, 10);
      const fileName = `ewl-${symbol}-${scaleMode}-${dateStr}.png`;
      const composed = composeWatermark(chartCanvas, {
        symbol,
        scaleMode,
        scenario: selectedScenario,
        compare: compareScenario && compareScenario.id !== selectedScenario?.id ? compareScenario : null,
        locale,
      });
      composed.toBlob((blob) => {
        if (!blob) {
          toast.error("Screenshot failed", {
            action: { label: "Retry", onClick: onExport },
          });
          return;
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("Chart exported", { duration: TOAST_DURATION });
      });
    } catch (e) {
      toast.error(`Export failed: ${(e as Error).message}`, {
        action: { label: "Retry", onClick: onExport },
      });
    }
  }, [takeScreenshot, symbol, scaleMode, selectedScenario, compareScenario, locale]);

  return (
    // Size-query container so the bottom rail collapses on the CHART's width,
    // not the viewport — a dragged-narrow desktop pane otherwise overlaps.
    <div className="w-full h-full flex flex-col @container/ewlchart">
      <div
        ref={containerRef}
        className="flex-1 min-h-0 relative"
        role="img"
        aria-label={
          selectedScenario
            ? `Candlestick chart of ${symbol} on ${scaleMode} scale, ${bars.length} bars. ` +
              `Currently inspecting ${prettyFamily(selectedScenario.family)} scenario, ` +
              `score ${selectedScenario.score.toFixed(3)}, ` +
              `${selectedScenario.is_complete ? "complete" : "still developing"}.` +
              (compareScenario && compareScenario.id !== selectedScenario.id
                ? ` Comparing against ${prettyFamily(compareScenario.family)}, score ${compareScenario.score.toFixed(3)}.`
                : "")
            : `Candlestick chart of ${symbol}, ${bars.length} bars. No scenario selected.`
        }
      >
        <div className="ewl-chart-title">
          <div className="ewl-chart-title-symbol" translate="no">
            {symbol}
            <span className="ewl-chart-title-scale">/ {scaleMode}</span>
          </div>
          {/* Hidden on sm+ — the input-state strip above the chart already shows this. */}
          <div className="ewl-chart-title-meta sm:hidden">
            {bars.length.toLocaleString(locale)} bars
          </div>
          {drillPath.length === 0 && hasDrillable && (
            <div className="ewl-chart-title-meta text-accent-bright">
              ◆ click a wave to drill in
            </div>
          )}
        </div>

        {/* pointer-events:none preserves crosshair underneath. */}
        {latestX != null && (
          <div
            aria-hidden="true"
            className="absolute top-0 bottom-0 pointer-events-none"
            style={{
              left: `${latestX}px`,
              width: "1px",
              borderLeft: "1px dashed rgba(148, 163, 184, 0.55)",
            }}
          >
            <span
              // top-10 clears the top-right toolbar row, which the pill's x can
              // coincide with when the last bar sits near the right edge.
              className="absolute top-10 ewl-num text-[10px] font-semibold uppercase tracking-[0.12em] px-1.5 py-0.5 rounded"
              style={{
                right: "4px",
                color: "#cbd5e1",
                background: "rgba(7, 10, 18, 0.85)",
                border: "1px solid rgba(148, 163, 184, 0.35)",
              }}
            >
              Latest
            </span>
          </div>
        )}

        {/* pointer-events:none keeps the chart interactive. */}
        {bottleneckRect && (
          <div
            aria-hidden="true"
            className="absolute top-0 bottom-0 pointer-events-none border-l border-r"
            style={{
              left: `${bottleneckRect.left}px`,
              width: `${bottleneckRect.width}px`,
              background: "rgba(244, 63, 94, 0.16)",
              borderColor: "rgba(244, 63, 94, 0.45)",
            }}
          >
            <span
              className="absolute top-2 left-2 ewl-num text-[10px] font-semibold uppercase tracking-[0.1em] px-1.5 py-0.5 rounded"
              style={{
                color: "#f43f5e",
                background: "rgba(7, 10, 18, 0.85)",
                border: "1px solid rgba(244, 63, 94, 0.45)",
              }}
            >
              ⛔ Bottleneck · Wave {bottleneckRect.legIdx + 1}
            </span>
          </div>
        )}

        <ChartToolbar
          compare={
            compareScenario && compareScenario.id !== selectedScenario?.id
              ? compareScenario
              : null
          }
          onClear={onClearCompare}
          onSwap={onSwapCompare}
          onExport={onExport}
        />

        <div className="ewl-chart-bottom">
          <ChartLegend
            isolatedRole={isolatedRole}
            hoveredRole={hoveredRole}
            onIsolate={(r) => setIsolatedRole((prev) => (prev === r ? null : r))}
            onHover={setHoveredRole}
          />
          <TimeChips onPick={showRange} disabled={!canSetRange} />
        </div>

        {crosshair && <CrosshairTooltip data={crosshair} />}
      </div>
    </div>
  );
}
