"use client";

import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { drawOverlays } from "@/lib/chart/draw-overlays";
import type { OverlayLayers } from "@/lib/chart/draw-overlays";
import {
  resolveBottleneckLeg,
  toUTC,
  toUTCNum,
  type CrosshairData,
  type LegendRole,
  type PerLegEntry,
} from "@/lib/chart/helpers";
import type { ChartLayerKey } from "@/lib/chart-store";
import { isDrillable, scopeLegs } from "@/lib/scenario-format";
import type { Bar, Layer1Result, Pivot, Scenario, ScaleMode } from "@/lib/types";
import { gregorianLocale } from "@/lib/resolve-locale";

type SubLegSeries = { rootRole: string; series: ISeriesApi<"Line">; baseColor: string };

// lightweight-charts stops here. Nothing below leaves the module.
interface ChartRefs {
  chartRef: RefObject<IChartApi | null>;
  candlesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  overlaysRef: RefObject<ISeriesApi<"Line">[]>;
  subLegSeriesRef: RefObject<SubLegSeries[]>;
  markersRef: RefObject<ISeriesMarkersPluginApi<Time> | null>;
}

export interface BottleneckRect {
  left: number;
  width: number;
  legIdx: number;
}

export interface WaveChartParams {
  containerRef: RefObject<HTMLDivElement | null>;
  locale: string;
  scaleMode: ScaleMode;
  bars: Bar[];
  activePivots: Pivot[];
  rawPivots: Pivot[];
  selectedScenario: Scenario | null;
  compareScenario: Scenario | null;
  /** Drill scope — indices into successive `drawableLegs`. Empty = root. */
  drillPath: number[];
  onDrill: (path: number[]) => void;
  layers: Record<ChartLayerKey, boolean>;
  layer1: Layer1Result | null;
  /** Legend hover/isolate; dims the sub-wave layer. */
  activeRole: LegendRole | null;
}

export interface WaveChartApi {
  /** Some leg in the current scope has sub-waves to drill into. */
  hasDrillable: boolean;
  /** Pixel band over the bottleneck leg, for the component to draw. */
  bottleneckRect: BottleneckRect | null;
  /** Pixel x of the last bar, for the component to draw the "Latest" rule. */
  latestX: number | null;
  crosshair: CrosshairData | null;
  canSetRange: boolean;
  showRange: (months: number | "all") => void;
  takeScreenshot: () => HTMLCanvasElement | null;
}

const SANS_FALLBACK =
  '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif';

function useChartInstance(
  containerRef: RefObject<HTMLDivElement | null>,
  scaleMode: ScaleMode,
  bars: Bar[],
  locale: string,
): ChartRefs & { chartReady: boolean } {
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlaysRef = useRef<ISeriesApi<"Line">[]>([]);
  const subLegSeriesRef = useRef<SubLegSeries[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lastFitKeyRef = useRef<string>("");
  const [chartReady, setChartReady] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Canvas can't read `var(...)` — resolve the font token at mount, falling
    // back if the CSS var isn't computed yet.
    const resolvedFont =
      getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim() ||
      SANS_FALLBACK;

    const chart = createChart(el, {
      autoSize: true,
      // Detail via drilling not zooming; also lets the scroll-stack column page
      // cleanly instead of the wheel being swallowed as a zoom.
      handleScroll: false,
      handleScale: false,
      // Viewer's locale (matching tooltip/strip), Gregorian-pinned so a th-TH
      // browser doesn't label the axis in Buddhist-era years.
      localization: { locale: gregorianLocale(locale) },
      layout: {
        background: { color: "transparent" },
        textColor: "#cbd5e1",
        fontFamily: resolvedFont,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.06)" },
        horzLines: { color: "rgba(148, 163, 184, 0.06)" },
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.10)",
        textColor: "#94a3b8",
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.10)",
        rightOffset: 12,
        barSpacing: 8,
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "rgba(16, 185, 129, 0.4)",
          width: 1,
          style: 2,
          labelBackgroundColor: "#10b981",
        },
        horzLine: {
          color: "rgba(16, 185, 129, 0.4)",
          width: 1,
          style: 2,
          labelBackgroundColor: "#10b981",
        },
      },
    });
    chartRef.current = chart;
    candlesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderUpColor: "#10b981",
      borderDownColor: "#f43f5e",
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    });
    setChartReady(true);

    return () => {
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      overlaysRef.current = [];
      subLegSeriesRef.current = [];
      markersRef.current = null;
      setChartReady(false);
    };
    // containerRef stable + locale session-stable → effectively mount-only.
  }, [containerRef, locale]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.priceScale("right").applyOptions({ mode: scaleMode === "log" ? 1 : 0 });
  }, [scaleMode]);

  useEffect(() => {
    const candles = candlesRef.current;
    if (!candles) return;
    candles.setData(
      bars.map((b) => ({
        time: toUTC(b.time),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    // Refit only when the data window changes (ticker/period switch), keyed on
    // count + first/last time — a same-window re-render keeps the user's zoom.
    const fitKey = bars.length
      ? `${bars.length}:${bars[0].time}:${bars[bars.length - 1].time}`
      : "";
    if (fitKey && fitKey !== lastFitKeyRef.current) {
      lastFitKeyRef.current = fitKey;
      chartRef.current?.timeScale().fitContent();
    }
  }, [bars]);

  return { chartRef, candlesRef, overlaysRef, subLegSeriesRef, markersRef, chartReady };
}

interface LegSpan {
  role: string;
  start: number;
  end: number;
}

function useChartDrill({
  chartRef,
  chartReady,
  selectedScenario,
  drillPath,
  drillKey,
  onDrill,
}: {
  chartRef: RefObject<IChartApi | null>;
  chartReady: boolean;
  selectedScenario: Scenario | null;
  drillPath: number[];
  drillKey: string;
  onDrill: (path: number[]) => void;
}) {
  // Scope legs (not leaves) so the hover label reads the leg the cursor is in.
  const legSpans = useMemo<LegSpan[]>(() => {
    if (!selectedScenario) return [];
    return scopeLegs(selectedScenario, drillPath)
      .map((l) => ({
        role: l.role,
        start: toUTCNum(l.span_start.time),
        end: toUTCNum(l.span_end.time),
      }))
      .sort((a, b) => a.start - b.start);
  }, [selectedScenario, drillPath]);

  const hasDrillable = useMemo(
    () =>
      selectedScenario
        ? scopeLegs(selectedScenario, drillPath).some(isDrillable)
        : false,
    [selectedScenario, drillPath],
  );

  const findRoleAtTime = useCallback(
    (t: number): string | null => {
      for (const leg of legSpans) {
        if (t >= leg.start && t <= leg.end) return leg.role;
      }
      return null;
    },
    [legSpans],
  );

  // Click-to-drill: markers aren't clickable, so map the clicked time onto the
  // scope leg whose span contains it.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !chartReady || !selectedScenario) return;
    const handler = (param: MouseEventParams) => {
      if (typeof param.time !== "number") return;
      const t = param.time;
      const legs = scopeLegs(selectedScenario, drillPath);
      for (let i = 0; i < legs.length; i++) {
        const leg = legs[i];
        if (!isDrillable(leg)) continue;
        const start = toUTCNum(leg.span_start.time);
        const end = toUTCNum(leg.span_end.time);
        if (t >= start && t <= end) {
          onDrill([...drillPath, i]);
          return;
        }
      }
    };
    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [chartRef, chartReady, selectedScenario, drillPath, onDrill]);

  // Drill zoom: fit the time axis to the scope span on drill, refit the whole
  // count on reset. Track prev scope so we refit only when leaving a drill,
  // never stomping a manual zoom at root.
  const prevDrillKeyRef = useRef(drillKey);
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !chartReady || !selectedScenario) return;
    const prev = prevDrillKeyRef.current;
    prevDrillKeyRef.current = drillKey;
    const legs = scopeLegs(selectedScenario, drillPath);
    if (drillPath.length > 0 && legs.length > 0) {
      const start = toUTCNum(legs[0].span_start.time);
      const end = toUTCNum(legs[legs.length - 1].span_end.time);
      const pad = Math.max(1, Math.round((end - start) * 0.08));
      chart.timeScale().setVisibleRange({
        from: (start - pad) as UTCTimestamp,
        to: (end + pad) as UTCTimestamp,
      });
    } else if (prev !== "" && drillPath.length === 0) {
      chart.timeScale().fitContent();
    }
  }, [chartRef, chartReady, selectedScenario, drillPath, drillKey]);

  return { hasDrillable, findRoleAtTime };
}

// HTML band overlays (bottleneck, latest) return pixel positions for the
// component to render; everything else draws imperatively.
function useChartOverlays({
  chartRef,
  candlesRef,
  overlaysRef,
  subLegSeriesRef,
  markersRef,
  chartReady,
  bars,
  activePivots,
  rawPivots,
  selectedScenario,
  compareScenario,
  drillPath,
  layers,
  layer1,
  activeRole,
}: ChartRefs & {
  chartReady: boolean;
  bars: Bar[];
  activePivots: Pivot[];
  rawPivots: Pivot[];
  selectedScenario: Scenario | null;
  compareScenario: Scenario | null;
  drillPath: number[];
  layers: Record<ChartLayerKey, boolean>;
  layer1: Layer1Result | null;
  activeRole: LegendRole | null;
}) {
  // Price lines are owned by the candle series (not chart.removeSeries-able),
  // so they need their own tracked pool to clear.
  const priceLinesRef = useRef<IPriceLine[]>([]);
  // HTML overlay synced to the timeScale — no vertical-band primitive.
  // null = layer off or data missing.
  const [bottleneckRect, setBottleneckRect] = useState<BottleneckRect | null>(null);
  const [latestX, setLatestX] = useState<number | null>(null);

  const drawLayers = useMemo<OverlayLayers>(
    () => ({
      raw_zigzag: layers.raw_zigzag,
      trendline: layers.trendline,
      in_progress: layers.in_progress,
    }),
    [layers.raw_zigzag, layers.trendline, layers.in_progress],
  );

  const activeRoleRef = useRef(activeRole);
  activeRoleRef.current = activeRole;

  const applyDimming = useCallback(
    (role: LegendRole | null) => {
      const hasActive = role != null;
      for (const { rootRole, series, baseColor } of subLegSeriesRef.current) {
        const isActive = rootRole === role;
        series.applyOptions({
          // 55=33% default dim, full when isolated, 22=13% for faded peers.
          color: !hasActive ? `${baseColor}55` : isActive ? baseColor : `${baseColor}22`,
          lineWidth: isActive ? 2 : 1,
        });
      }
    },
    [subLegSeriesRef],
  );

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candlesRef.current;
    if (!chart || !candles) return;

    for (const s of overlaysRef.current) chart.removeSeries(s);
    for (const e of subLegSeriesRef.current) chart.removeSeries(e.series);
    markersRef.current?.setMarkers([]);

    const { overlays, subLegSeries, markers } = drawOverlays(chart, {
      bars,
      activePivots,
      rawPivots,
      selectedScenario,
      compareScenario,
      drillPath,
      layers: drawLayers,
    });
    overlaysRef.current = overlays;
    subLegSeriesRef.current = subLegSeries;

    if (markers.length > 0) {
      const sorted = [...markers].sort((a, b) => (a.time as number) - (b.time as number));
      if (!markersRef.current) {
        markersRef.current = createSeriesMarkers(candles, sorted);
      } else {
        markersRef.current.setMarkers(sorted);
      }
    }

    applyDimming(activeRoleRef.current);
  }, [
    chartRef,
    candlesRef,
    overlaysRef,
    subLegSeriesRef,
    markersRef,
    chartReady,
    bars,
    activePivots,
    rawPivots,
    selectedScenario,
    compareScenario,
    drawLayers,
    drillPath,
    applyDimming,
  ]);

  // Hover/isolation: dims the sub-wave layer only; the spine stays bold amber.
  // Isolating a root role brightens its subtree to full opacity and fades peers.
  // No-op for flat 5W scenarios (no nested sub-waves).
  useEffect(() => {
    applyDimming(activeRole);
  }, [activeRole, applyDimming]);

  // Price lines on the candle series survive pan/zoom and align with the axis label.
  useEffect(() => {
    const candles = candlesRef.current;
    if (!candles) return;

    // Clear previous lines so toggling a layer off leaves no orphans.
    for (const pl of priceLinesRef.current) candles.removePriceLine(pl);
    priceLinesRef.current = [];

    const targets = layer1?.targets ?? null;
    if (!targets) return;

    if (layers.fib_targets) {
      // Confirmation levels — top 3 only so the fib ladder doesn't crowd the axis.
      for (const t of targets.confirmation_targets.slice(0, 3)) {
        const pl = candles.createPriceLine({
          price: t.price,
          color: "#06b6d4",
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${t.name} (p.${t.theory_page})`,
        });
        priceLinesRef.current.push(pl);
      }
      // Fib flow projections — dimmer/dotted to read as softer than confirmations.
      for (const t of targets.fib_flow_targets.slice(0, 5)) {
        const pl = candles.createPriceLine({
          price: t.price,
          color: "rgba(6,182,212,0.5)",
          lineWidth: 1,
          lineStyle: 1,
          axisLabelVisible: true,
          title: t.name,
        });
        priceLinesRef.current.push(pl);
      }
    }

    if (layers.invalidation && targets.invalidation) {
      const inv = targets.invalidation;
      const pl = candles.createPriceLine({
        price: inv.price,
        color: "#f43f5e",
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: `⚠ Invalidation $${inv.price.toFixed(2)}`,
      });
      priceLinesRef.current.push(pl);
    }
  }, [candlesRef, layers.fib_targets, layers.invalidation, layer1]);

  // Bottleneck band over the worst leg, HTML <div> synced to the timeScale.
  useEffect(() => {
    if (!layers.bottleneck) {
      setBottleneckRect(null);
      return;
    }
    const bd = layer1?.bottleneck ?? null;
    if (!bd || bd.slot_name !== "leg_smoothness" || !selectedScenario) {
      setBottleneckRect(null);
      return;
    }
    const perLeg = bd.intermediates?.per_leg as PerLegEntry[] | undefined;
    if (!perLeg || perLeg.length === 0) {
      setBottleneckRect(null);
      return;
    }
    const worst = resolveBottleneckLeg(selectedScenario, perLeg);
    if (!worst) {
      setBottleneckRect(null);
      return;
    }
    const { leg, legIdx } = worst;
    const t0 = toUTC(leg.span_start.time);
    const t1 = toUTC(leg.span_end.time);

    const chart = chartRef.current;
    if (!chart) return;
    const recompute = () => {
      const ts = chart.timeScale();
      const x0 = ts.timeToCoordinate(t0);
      const x1 = ts.timeToCoordinate(t1);
      if (x0 == null || x1 == null) {
        setBottleneckRect(null);
        return;
      }
      const left = Math.min(x0, x1);
      const width = Math.max(0, Math.abs(x1 - x0));
      setBottleneckRect({ left, width, legIdx });
    };
    recompute();
    const ts = chart.timeScale();
    ts.subscribeVisibleLogicalRangeChange(recompute);
    return () => {
      ts.unsubscribeVisibleLogicalRangeChange(recompute);
    };
    // chartReady re-runs this once the chart mounts, even if data was cached first.
  }, [chartRef, chartReady, layers.bottleneck, layer1, selectedScenario]);

  // Latest line at the current bar, x synced to the timeScale.
  useEffect(() => {
    if (!layers.latest || bars.length === 0) {
      setLatestX(null);
      return;
    }
    const chart = chartRef.current;
    if (!chart) return;
    const lastTime = toUTC(bars[bars.length - 1].time);
    const recompute = () => {
      const x = chart.timeScale().timeToCoordinate(lastTime);
      setLatestX(x ?? null);
    };
    recompute();
    const ts = chart.timeScale();
    ts.subscribeVisibleLogicalRangeChange(recompute);
    return () => {
      ts.unsubscribeVisibleLogicalRangeChange(recompute);
    };
  }, [chartRef, chartReady, layers.latest, bars]);

  return { bottleneckRect, latestX };
}

// Crosshair state lives here, not in the tooltip: the tooltip is then a pure
// render of CrosshairData and never touches the chart library.
function useCrosshair({
  chartRef,
  containerRef,
  chartReady,
  bars,
  findRoleAtTime,
}: {
  chartRef: RefObject<IChartApi | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  chartReady: boolean;
  bars: Bar[];
  findRoleAtTime: (t: number) => string | null;
}): CrosshairData | null {
  const [data, setData] = useState<CrosshairData | null>(null);

  const barIndex = useMemo(() => {
    const m = new Map<number, Bar>();
    for (const b of bars) m.set(toUTC(b.time), b);
    return m;
  }, [bars]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !chartReady) return;
    const handler = (param: MouseEventParams) => {
      const t = typeof param.time === "number" ? param.time : null;
      const pt = param.point;
      if (t == null || !pt) {
        setData(null);
        return;
      }
      const bar = barIndex.get(t);
      if (!bar) {
        setData(null);
        return;
      }
      // Read width here, not in render, to keep layout reads out of render.
      const w = containerRef.current?.clientWidth ?? 0;
      setData({ time: t, bar, role: findRoleAtTime(t), x: pt.x, y: pt.y, w });
    };
    chart.subscribeCrosshairMove(handler);
    return () => chart.unsubscribeCrosshairMove(handler);
  }, [chartRef, containerRef, chartReady, barIndex, findRoleAtTime]);

  return data;
}

/**
 * The chart, as the app sees it: domain values in, domain values out.
 *
 * The lightweight-charts instance, its series, and its markers plugin are refs
 * held inside this module. They used to be the return type — five ref types the
 * component received only to hand straight back to the next hook — which is why
 * the drill and overlay logic had no reachable test surface.
 */
export function useWaveChart({
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
}: WaveChartParams): WaveChartApi {
  // Stable dep key — nuqs returns a fresh drillPath array each render.
  const drillKey = drillPath.join(".");
  const stablePath = useMemo(
    () => (drillKey === "" ? [] : drillKey.split(".").map(Number)),
    [drillKey],
  );

  const refs = useChartInstance(containerRef, scaleMode, bars, locale);
  const { chartRef, chartReady } = refs;

  const { hasDrillable, findRoleAtTime } = useChartDrill({
    chartRef,
    chartReady,
    selectedScenario,
    drillPath: stablePath,
    drillKey,
    onDrill,
  });

  const { bottleneckRect, latestX } = useChartOverlays({
    ...refs,
    chartReady,
    bars,
    activePivots,
    rawPivots,
    selectedScenario,
    compareScenario,
    drillPath: stablePath,
    layers,
    layer1,
    activeRole,
  });

  const crosshair = useCrosshair({
    chartRef,
    containerRef,
    chartReady,
    bars,
    findRoleAtTime,
  });

  const firstBarTime = useMemo(
    () => (bars.length > 0 ? toUTC(bars[0].time) : null),
    [bars],
  );
  const lastBarTime = useMemo(
    () => (bars.length > 0 ? toUTC(bars[bars.length - 1].time) : null),
    [bars],
  );

  const showRange = useCallback(
    (months: number | "all") => {
      const chart = chartRef.current;
      if (!chart || !lastBarTime || !firstBarTime) return;
      if (months === "all") {
        chart.timeScale().fitContent();
        return;
      }
      const SECS_PER_MONTH = 30 * 24 * 60 * 60;
      const from = Math.max(
        firstBarTime,
        lastBarTime - months * SECS_PER_MONTH,
      ) as UTCTimestamp;
      chart.timeScale().setVisibleRange({ from, to: lastBarTime });
    },
    [chartRef, lastBarTime, firstBarTime],
  );

  const takeScreenshot = useCallback(
    () => chartRef.current?.takeScreenshot() ?? null,
    [chartRef],
  );

  return {
    hasDrillable,
    bottleneckRect,
    latestX,
    crosshair,
    canSetRange: lastBarTime != null,
    showRange,
    takeScreenshot,
  };
}
