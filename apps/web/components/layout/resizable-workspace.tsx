"use client";

import {
  GripVertical,
  Layers,
  PanelLeftOpen,
  PanelRightOpen,
  Settings2,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import {
  type ImperativePanelHandle,
  Panel,
  PanelGroup,
  PanelResizeHandle,
} from "react-resizable-panels";
import { usePanelControls } from "@/lib/chart-store";
import { cn } from "@/lib/cn";
import { ChartShell } from "@/components/chart/chart-shell";
import { ErrorBoundary } from "@/components/feedback/error-boundary";
import { ScenariosPanelContainer } from "@/components/scenarios/scenarios-panel-container";
import { SidePanel } from "@/components/layout/side-panel";

// % of workspace; ~45–55px — room for icon + rotated label so a collapsed pane
// stays clickable rather than vanishing.
const COLLAPSED_SIZE = 3.5;

export function ResizableWorkspace() {
  const leftRef = useRef<ImperativePanelHandle>(null);
  const rightRef = useRef<ImperativePanelHandle>(null);
  // Library is the source of truth (drag-collapse + restored layout flow through
  // onCollapse/onExpand), so the content swap matches the real size.
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const toggleLeft = useCallback(() => {
    const p = leftRef.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  }, []);
  const toggleRight = useCallback(() => {
    const p = rightRef.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  }, []);

  // Hand toggles to the global keyboard handler in a sibling subtree that can't
  // reach these refs.
  const register = usePanelControls((s) => s.register);
  useEffect(() => {
    register({ toggleLeft, toggleRight });
  }, [register, toggleLeft, toggleRight]);

  return (
    <PanelGroup
      direction="horizontal"
      autoSaveId="ewl-workspace"
      className="flex flex-1 min-h-0"
    >
      {/* Per-panel ErrorBoundary so a crash in one doesn't black out the others. */}
      <Panel
        id="sidebar"
        order={1}
        ref={leftRef}
        collapsible
        collapsedSize={COLLAPSED_SIZE}
        defaultSize={20}
        minSize={16}
        maxSize={28}
        onCollapse={() => setLeftCollapsed(true)}
        onExpand={() => setLeftCollapsed(false)}
      >
        <ErrorBoundary context="Sidebar">
          {leftCollapsed ? (
            <CollapsedRail
              side="left"
              label="Lab Notebook"
              icon={<Settings2 className="h-4 w-4" />}
              onExpand={toggleLeft}
            />
          ) : (
            <SidePanel embed onCollapse={toggleLeft} />
          )}
        </ErrorBoundary>
      </Panel>
      <ResizeHandle />
      <Panel id="chart" defaultSize={54} minSize={35} order={2}>
        <ErrorBoundary context="Chart">
          <ChartShell />
        </ErrorBoundary>
      </Panel>
      <ResizeHandle />
      <Panel
        id="scenarios"
        order={3}
        ref={rightRef}
        collapsible
        collapsedSize={COLLAPSED_SIZE}
        defaultSize={26}
        minSize={20}
        maxSize={40}
        onCollapse={() => setRightCollapsed(true)}
        onExpand={() => setRightCollapsed(false)}
      >
        <ErrorBoundary context="Scenarios">
          {rightCollapsed ? (
            <CollapsedRail
              side="right"
              label="Scenarios"
              icon={<Layers className="h-4 w-4" />}
              onExpand={toggleRight}
            />
          ) : (
            <ScenariosPanelContainer embed onCollapse={toggleRight} />
          )}
        </ErrorBoundary>
      </Panel>
    </PanelGroup>
  );
}

// Tablet (md–lg): chart + scenarios; sidebar is too narrow, so Lab Notebook
// stays a drawer. Separate autoSaveId so it can't clash with the 3-pane layout.
export function TabletWorkspace() {
  const rightRef = useRef<ImperativePanelHandle>(null);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const toggleRight = useCallback(() => {
    const p = rightRef.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  }, []);

  return (
    <PanelGroup
      direction="horizontal"
      autoSaveId="ewl-workspace-tablet"
      className="flex flex-1 min-h-0"
    >
      <Panel id="chart" defaultSize={62} minSize={45} order={1}>
        <ErrorBoundary context="Chart">
          <ChartShell />
        </ErrorBoundary>
      </Panel>
      <ResizeHandle />
      <Panel
        id="scenarios"
        order={2}
        ref={rightRef}
        collapsible
        collapsedSize={COLLAPSED_SIZE}
        defaultSize={38}
        minSize={28}
        maxSize={55}
        onCollapse={() => setRightCollapsed(true)}
        onExpand={() => setRightCollapsed(false)}
      >
        <ErrorBoundary context="Scenarios">
          {rightCollapsed ? (
            <CollapsedRail
              side="right"
              label="Scenarios"
              icon={<Layers className="h-4 w-4" />}
              onExpand={toggleRight}
            />
          ) : (
            <ScenariosPanelContainer embed onCollapse={toggleRight} />
          )}
        </ErrorBoundary>
      </Panel>
    </PanelGroup>
  );
}

function CollapsedRail({
  side,
  label,
  icon,
  onExpand,
}: {
  side: "left" | "right";
  label: string;
  icon: ReactNode;
  onExpand: () => void;
}) {
  return (
    <div
      className={cn(
        "h-full flex flex-col items-center gap-3 py-3 overflow-hidden",
        side === "left"
          ? "border-r border-border ewl-surface-sidebar"
          : "border-l border-border ewl-surface-panel",
      )}
    >
      <button
        type="button"
        onClick={onExpand}
        aria-label={`Expand ${label} panel`}
        title={`Expand ${label}`}
        className={cn(
          "grid place-items-center h-8 w-8 rounded-md shrink-0 transition-colors",
          "text-accent hover:bg-accent-soft",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        {side === "left" ? (
          <PanelLeftOpen className="h-4 w-4" />
        ) : (
          <PanelRightOpen className="h-4 w-4" />
        )}
      </button>
      <span className="shrink-0 text-faint" aria-hidden="true">
        {icon}
      </span>
      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-dim [writing-mode:vertical-rl] rotate-180 select-none">
        {label}
      </span>
    </div>
  );
}

function ResizeHandle() {
  return (
    <PanelResizeHandle
      className="group/handle relative w-px bg-border hover:bg-border-glow data-[resize-handle-state='drag']:bg-accent transition-colors"
      aria-label="Resize panel"
    >
      {/* Wider invisible hit area for easier targeting. */}
      <span className="absolute inset-y-0 -left-1.5 -right-1.5" aria-hidden="true" />
      <span
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 grid place-items-center w-4 h-8 rounded-sm bg-panel border border-border-hi text-faint opacity-0 group-hover/handle:opacity-100 group-data-[resize-handle-state='drag']/handle:opacity-100 transition-opacity"
        aria-hidden="true"
      >
        <GripVertical className="h-3 w-3" />
      </span>
    </PanelResizeHandle>
  );
}
