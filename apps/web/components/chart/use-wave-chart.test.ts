// @vitest-environment jsdom
//
// These go through useWaveChart, the hook's only export. The drill, overlay and
// crosshair logic used to sit behind three hooks that traded five lightweight-charts
// refs between them, so reaching it from a test meant constructing the ref tangle —
// and none of it was tested. The seam is the test surface now.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const chartApi = vi.hoisted(() => ({
  fitContent: vi.fn(),
  setVisibleRange: vi.fn(),
  timeToCoordinate: vi.fn((t: number) => t / 100),
  subscribeVisibleLogicalRangeChange: vi.fn(),
  unsubscribeVisibleLogicalRangeChange: vi.fn(),
  takeScreenshot: vi.fn(() => ({ tag: "canvas" })),
  clickHandlers: [] as ((p: unknown) => void)[],
  crosshairHandlers: [] as ((p: unknown) => void)[],
  priceLines: [] as unknown[],
}));

vi.mock("lightweight-charts", () => {
  const series = {
    setData: vi.fn(),
    applyOptions: vi.fn(),
    createPriceLine: vi.fn((o: unknown) => {
      chartApi.priceLines.push(o);
      return o;
    }),
    removePriceLine: vi.fn((pl: unknown) => {
      chartApi.priceLines = chartApi.priceLines.filter((p) => p !== pl);
    }),
  };
  const chart = {
    addSeries: vi.fn(() => series),
    removeSeries: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    timeScale: vi.fn(() => chartApi),
    remove: vi.fn(),
    takeScreenshot: chartApi.takeScreenshot,
    subscribeClick: vi.fn((h) => chartApi.clickHandlers.push(h)),
    unsubscribeClick: vi.fn(),
    subscribeCrosshairMove: vi.fn((h) => chartApi.crosshairHandlers.push(h)),
    unsubscribeCrosshairMove: vi.fn(),
  };
  return {
    createChart: vi.fn(() => chart),
    CandlestickSeries: {},
    createSeriesMarkers: vi.fn(() => ({ setMarkers: vi.fn() })),
  };
});

// Exercised exhaustively by lib/chart/draw-overlays.test.ts; stubbed here so these
// tests are about the hook's orchestration, not the drawing.
vi.mock("@/lib/chart/draw-overlays", () => ({
  drawOverlays: vi.fn(() => ({ overlays: [], subLegSeries: [], markers: [] })),
}));

import { useWaveChart, type WaveChartParams } from "./use-wave-chart";
import { allLayersOff, makePivot, makeScenario, makeWave } from "@/lib/test-support/waves";
import type { Bar, Layer1Result, Scenario, Wave } from "@/lib/types";

const T0 = "2024-01-01T00:00:00";
const T1 = "2024-01-08T00:00:00";
const T2 = "2024-01-15T00:00:00";

const bar = (time: string, c = 100): Bar => ({
  time, open: c, high: c + 1, low: c - 1, close: c, volume: 0,
});
const windowA: Bar[] = [bar(T0), bar(T1), bar(T2)];
const windowB: Bar[] = [bar("2020-06-01", 50), bar("2020-06-08", 52)];

const utc = (iso: string) => Math.floor(Date.parse(`${iso}Z`) / 1000);

const leg = (role: string, from: string, to: string, children: Wave[] = []): Wave =>
  makeWave(role, {
    span_start: makePivot({ time: from }),
    span_end: makePivot({ time: to }),
    children,
  });

// s1 spans T0→T1 and has sub-waves (drillable); s2 spans T1→T2 and does not.
const drillableScenario = (): Scenario =>
  makeScenario({
    root: makeWave("root", {
      children: [
        leg("s1", T0, T1, [leg("a", T0, T1), leg("b", T0, T1)]),
        leg("s2", T1, T2),
      ],
    }),
  });

const params = (over: Partial<WaveChartParams> = {}): WaveChartParams => ({
  containerRef: { current: document.createElement("div") },
  locale: "en-US",
  scaleMode: "linear",
  bars: windowA,
  activePivots: [],
  rawPivots: [],
  selectedScenario: null,
  compareScenario: null,
  drillPath: [],
  onDrill: vi.fn(),
  layers: allLayersOff(),
  layer1: null,
  activeRole: null,
  ...over,
});

const render = (over: Partial<WaveChartParams> = {}) =>
  renderHook((p: WaveChartParams) => useWaveChart(p), { initialProps: params(over) });

beforeEach(() => {
  chartApi.clickHandlers = [];
  chartApi.crosshairHandlers = [];
  chartApi.priceLines = [];
});
afterEach(() => vi.clearAllMocks());

describe("data window", () => {
  it("fits the chart on initial data load", () => {
    render();
    expect(chartApi.fitContent).toHaveBeenCalledTimes(1);
  });

  it("refits only when the data window changes, not on a same-window re-render", () => {
    const { rerender } = render();
    expect(chartApi.fitContent).toHaveBeenCalledTimes(1);

    // Same window, new array ref (e.g. overlay update re-renders) → keep user's zoom.
    rerender(params({ bars: [...windowA] }));
    expect(chartApi.fitContent).toHaveBeenCalledTimes(1);

    // Different window (ticker / period switch) → refit.
    rerender(params({ bars: windowB }));
    expect(chartApi.fitContent).toHaveBeenCalledTimes(2);
  });
});

describe("drill", () => {
  it("reports hasDrillable only when a leg in scope has sub-waves", () => {
    expect(render({ selectedScenario: drillableScenario() }).result.current.hasDrillable).toBe(true);
    // Drilled into s1, whose own children are leaves.
    expect(
      render({ selectedScenario: drillableScenario(), drillPath: [0] }).result.current.hasDrillable,
    ).toBe(false);
    expect(render().result.current.hasDrillable).toBe(false);
  });

  it("drills into the leg whose span contains the clicked time", () => {
    const onDrill = vi.fn();
    render({ selectedScenario: drillableScenario(), onDrill });

    act(() => chartApi.clickHandlers.forEach((h) => h({ time: utc(T0) + 60 })));
    expect(onDrill).toHaveBeenCalledWith([0]);
  });

  it("ignores a click on a leg with no sub-waves to drill into", () => {
    const onDrill = vi.fn();
    render({ selectedScenario: drillableScenario(), onDrill });

    // Inside s2, which is not drillable.
    act(() => chartApi.clickHandlers.forEach((h) => h({ time: utc(T2) - 60 })));
    expect(onDrill).not.toHaveBeenCalled();
  });

  it("zooms to the drilled span, and refits only when leaving the drill", () => {
    const { rerender } = render({ selectedScenario: drillableScenario() });
    chartApi.fitContent.mockClear();

    rerender(params({ selectedScenario: drillableScenario(), drillPath: [0] }));
    expect(chartApi.setVisibleRange).toHaveBeenCalledTimes(1);
    expect(chartApi.fitContent).not.toHaveBeenCalled();

    rerender(params({ selectedScenario: drillableScenario(), drillPath: [] }));
    expect(chartApi.fitContent).toHaveBeenCalledTimes(1);
  });
});

describe("price lines", () => {
  const layer1 = {
    targets: {
      confirmation_targets: [
        { name: "c1", price: 10, type: "retracement", theory_page: 1, derivation: "" },
      ],
      fib_flow_targets: [],
      invalidation: {
        name: "inv", price: 5, type: "invalidation", theory_page: 2, derivation: "",
      },
    },
  } as unknown as Layer1Result;

  it("draws nothing while both target layers are off", () => {
    render({ layer1 });
    expect(chartApi.priceLines).toHaveLength(0);
  });

  it("draws confirmation and invalidation lines when their layers are on", () => {
    render({ layer1, layers: allLayersOff({ fib_targets: true, invalidation: true }) });
    expect(chartApi.priceLines).toHaveLength(2);
  });

  it("clears its lines when a layer is switched back off", () => {
    const { rerender } = render({
      layer1,
      layers: allLayersOff({ fib_targets: true, invalidation: true }),
    });
    expect(chartApi.priceLines).toHaveLength(2);

    rerender(params({ layer1, layers: allLayersOff() }));
    expect(chartApi.priceLines).toHaveLength(0);
  });
});

describe("latest marker", () => {
  it("is null while the layer is off and placed at the last bar when on", () => {
    expect(render().result.current.latestX).toBeNull();

    const { result } = render({ layers: allLayersOff({ latest: true }) });
    expect(result.current.latestX).toBe(utc(T2) / 100);
  });
});

describe("crosshair", () => {
  it("resolves the hovered bar and the leg role under the cursor", () => {
    const { result } = render({ selectedScenario: drillableScenario() });

    act(() =>
      chartApi.crosshairHandlers.forEach((h) =>
        h({ time: utc(T1), point: { x: 42, y: 7 } }),
      ),
    );
    expect(result.current.crosshair?.bar.time).toBe(T1);
    expect(result.current.crosshair?.role).toBe("s1");
    expect(result.current.crosshair?.x).toBe(42);
  });

  it("clears when the cursor leaves the plot or sits off a bar", () => {
    const { result } = render();

    act(() => chartApi.crosshairHandlers.forEach((h) => h({ time: utc(T1), point: { x: 1, y: 1 } })));
    expect(result.current.crosshair).not.toBeNull();

    act(() => chartApi.crosshairHandlers.forEach((h) => h({ time: undefined, point: undefined })));
    expect(result.current.crosshair).toBeNull();
  });
});

describe("range + screenshot", () => {
  it("fits the whole count for 'all' and windows back from the last bar otherwise", () => {
    const { result } = render();
    chartApi.fitContent.mockClear();

    act(() => result.current.showRange("all"));
    expect(chartApi.fitContent).toHaveBeenCalledTimes(1);

    act(() => result.current.showRange(1));
    expect(chartApi.setVisibleRange).toHaveBeenCalledWith({
      from: expect.any(Number),
      to: utc(T2),
    });
  });

  it("reports canSetRange only when there are bars", () => {
    expect(render().result.current.canSetRange).toBe(true);
    expect(render({ bars: [] }).result.current.canSetRange).toBe(false);
  });

  it("hands back the chart canvas without exposing the chart", () => {
    const { result } = render();
    expect(result.current.takeScreenshot()).toEqual({ tag: "canvas" });
  });
});
