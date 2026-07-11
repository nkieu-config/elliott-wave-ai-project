"use client";

import { AlertTriangle, ChevronDown, Loader2, RotateCw } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryStates } from "nuqs";
import {
  useCompareScenario,
  useDrillPath,
  useLayers,
  useSelectedScenario,
} from "@/lib/chart-store";
import { cn } from "@/lib/cn";
import { asScaleMode, configParsers } from "@/lib/config";
import { useLayer1, usePipeline } from "@/lib/query";
import { findSelectedScenario, resolveScopeNode } from "@/lib/scenario-format";
import { DrillBreadcrumb } from "@/components/chart/drill-breadcrumb";
import { HeroNarrative } from "@/components/feedback/hero-narrative";
import { InputStateStrip } from "@/components/feedback/input-state-strip";
import { ReadingPanel } from "@/components/analyst/reading-panel";
import { LayersBar } from "@/components/chart/layers-bar";

// Browser-only (canvas) and ~50KB; split off the initial JS path. Chunk fetch
// races the pipeline request, so it's usually ready by data-land.
const WaveChart = dynamic(() => import("./wave-chart").then((m) => m.WaveChart), {
  ssr: false,
  loading: () => <SkeletonChart />,
});

// The CSS reduced-motion rule doesn't reach JS scrollTo/scrollBy — honor it here.
const scrollBehavior = (): ScrollBehavior =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "auto"
    : "smooth";

export function ChartShell() {
  const [config] = useQueryStates(configParsers);
  const query = usePipeline(config);

  const scenarios = useMemo(
    () => query.data?.report?.scenarios ?? [],
    [query.data],
  );
  const [selectedId, setSelectedId] = useSelectedScenario();
  const [compareId, setCompareId] = useCompareScenario();
  const { layers } = useLayers();
  const [drillPath, setDrillPath] = useDrillPath();
  const onDrill = useCallback((path: number[]) => void setDrillPath(path), [setDrillPath]);

  // Gated on dataUpdatedAt so only a fresh dataset re-seeds selection;
  // otherwise a refetch would clobber the user's manual click.
  const fetchedAtRef = useRef<number>(0);
  useEffect(() => {
    if (!query.dataUpdatedAt || query.dataUpdatedAt === fetchedAtRef.current) return;
    fetchedAtRef.current = query.dataUpdatedAt;
    if (scenarios.length === 0) return;
    const stillThere = selectedId && scenarios.some((s) => s.id === selectedId);
    if (!stillThere) {
      const top = [...scenarios].sort((a, b) => b.score - a.score)[0];
      void setSelectedId(top.id);
    }
  }, [query.dataUpdatedAt, scenarios, selectedId, setSelectedId]);

  const selectedScenario = useMemo(
    () => findSelectedScenario(query.data, selectedId),
    [query.data, selectedId],
  );

  // Keyed on (config × scenario_id) so the cache entry is shared with KpiRow.
  const layer1Query = useLayer1(config, selectedScenario?.id ?? null);
  const layer1 = layer1Query.data ?? null;

  // Reset drill scope on selection change, but not on mount, so a shared
  // ?scenario=…&drill=… link keeps its drilled view.
  const prevSelRef = useRef(selectedId);
  useEffect(() => {
    if (prevSelRef.current === selectedId) return;
    prevSelRef.current = selectedId;
    if (drillPath.length > 0) void setDrillPath([]);
  }, [selectedId, drillPath, setDrillPath]);

  // Self-heal a stale/invalid drill path (structure changed, or bad shared link).
  useEffect(() => {
    if (drillPath.length === 0 || !selectedScenario) return;
    if (resolveScopeNode(selectedScenario, drillPath) === null) void setDrillPath([]);
  }, [selectedScenario, drillPath, setDrillPath]);

  // Drop a stale ?compare= id absent from the report, else compare silently breaks.
  const compareScenario = useMemo(() => {
    if (!compareId) return null;
    const hit = scenarios.find((s) => s.id === compareId);
    return hit ?? null;
  }, [scenarios, compareId]);

  // Cue shown only while the column is at the top AND overflows. ResizeObserver
  // re-evals because the chart's autoSize settles a frame late.
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showCue, setShowCue] = useState(false);
  const evalCue = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setShowCue(el.scrollTop < 24 && el.scrollHeight - el.clientHeight > 48);
  }, []);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => evalCue());
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    evalCue();
    return () => ro.disconnect();
  }, [evalCue]);

  // Scroll to top on scenario change so a fresh chart isn't off-screen above a
  // scrolled-down reader. Skip the mount run.
  const didMountScrollRef = useRef(false);
  useEffect(() => {
    if (!didMountScrollRef.current) {
      didMountScrollRef.current = true;
      return;
    }
    scrollRef.current?.scrollTo({ top: 0, behavior: scrollBehavior() });
  }, [selectedId]);

  return (
    // w-full: on mobile ChartShell is a no-grow flex item; without it the shell
    // collapses to intrinsic width, not the viewport.
    <div className="relative flex flex-col h-full w-full min-w-0 min-h-0 bg-bg">
      {/* Fixed toolbar — stays put while the chart + reading scroll below. */}
      <div className="shrink-0">
        <HeroNarrative data={query.data} error={query.error} />
        <InputStateStrip data={query.data} />
        <LayersBar scenario={selectedScenario} layer1={layer1} drilled={drillPath.length > 0} />
        {selectedScenario && (
          <DrillBreadcrumb
            scenario={selectedScenario}
            path={drillPath}
            onNavigate={onDrill}
            onReset={() => onDrill([])}
          />
        )}
      </div>
      {/* Chart at fixed height (static fit-the-count, not pan/zoom), AI Reading
          flows below. Chart's wheel is disabled so a wheel over it pages the
          column, not zooms. */}
      <div
        ref={scrollRef}
        onScroll={evalCue}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain"
      >
        {/* 48vh so the AI Reading tabs peek above the fold on a ~768px laptop. */}
        <div className="h-[clamp(300px,48vh,620px)] relative">
          {query.data ? (
            <WaveChart
              symbol={query.data.meta.symbol}
              scaleMode={asScaleMode(query.data.meta.config.scale_mode)}
              bars={query.data.bars}
              activePivots={query.data.active_pivots}
              rawPivots={query.data.raw_pivots}
              selectedScenario={selectedScenario}
              compareScenario={compareScenario}
              onClearCompare={() => void setCompareId(null)}
              onSwapCompare={
                compareScenario && selectedScenario
                  ? () => {
                      const prevSel = selectedScenario.id;
                      void setSelectedId(compareScenario.id);
                      void setCompareId(prevSel);
                    }
                  : undefined
              }
              layers={layers}
              layer1={layer1}
              drillPath={drillPath}
              onDrill={onDrill}
            />
          ) : query.isError ? (
            <ErrorState
              message={query.error?.message ?? "Unknown error"}
              onRetry={() => query.refetch()}
            />
          ) : (
            <SkeletonChart />
          )}
        </div>
        <ReadingPanel />
      </div>
      <button
        type="button"
        onClick={() =>
          scrollRef.current?.scrollBy({
            top: Math.round(scrollRef.current.clientHeight * 0.82),
            behavior: scrollBehavior(),
          })
        }
        aria-label="Scroll down to AI Reading"
        tabIndex={showCue ? 0 : -1}
        className={cn(
          "absolute inset-x-0 bottom-0 z-10 flex items-end justify-center pb-1.5 h-14",
          "bg-gradient-to-t from-bg via-bg/70 to-transparent",
          "transition-opacity duration-300",
          showCue ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
      >
        <span className="inline-flex items-center gap-1 text-[12px] font-semibold uppercase tracking-[0.14em] text-text-dim bg-panel-elev border border-border-hi rounded-full px-2.5 py-1 shadow-sm">
          AI Reading
          <ChevronDown className="h-3 w-3 animate-bounce" aria-hidden="true" />
        </span>
      </button>
    </div>
  );
}

function SkeletonChart() {
  return (
    <div className="absolute inset-0 flex flex-col p-4 gap-3">
      <div className="flex items-center gap-3 text-muted text-[12px] font-medium uppercase tracking-[0.12em]">
        <Loader2 className="h-4 w-4 animate-spin text-accent" />
        Fetching pipeline…
      </div>
      <div className="flex-1 ewl-skeleton rounded-md min-h-0" />
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const isNetwork = /fetch|network|failed|ECONNREFUSED/i.test(message);
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 px-6">
      <span className="grid place-items-center h-14 w-14 rounded-lg border border-down/40 bg-down/10 text-down">
        <AlertTriangle className="h-7 w-7" />
      </span>
      <div className="text-center max-w-lg space-y-2">
        <div className="text-sm font-semibold text-text">
          Pipeline request failed
        </div>
        <div className="text-[13px] ewl-num text-muted break-all bg-panel border border-border rounded-md px-3 py-2">
          {message}
        </div>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-2 h-10 px-4 rounded-md border border-border-glow bg-accent-soft text-accent-bright text-xs font-semibold hover:bg-accent/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <RotateCw className="h-3.5 w-3.5" />
        Retry
      </button>
      {isNetwork && (
        <div className="text-center max-w-md space-y-1">
          <p className="text-[12px] uppercase tracking-[0.12em] text-muted font-semibold">
            Backend not reachable
          </p>
          <p className="text-[13px] text-faint ewl-num bg-panel border border-border rounded-md px-3 py-1.5">
            uv run uvicorn apps.api.main:app --port 8000
          </p>
        </div>
      )}
    </div>
  );
}
