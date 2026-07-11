"use client";

import { ChevronRight, Star } from "lucide-react";
import { useDisclosure } from "@/lib/hooks/use-disclosure";
import { cn } from "@/lib/cn";
import { relativeStrengthPct } from "@/lib/scenario-ranking";
import { AnimatedNumber } from "@/components/ui/animated-number";
import {
  asTier,
  calibratedPct,
  type ComponentGroup,
  GROUP_META,
  resolveBottleneck,
  scoreTier,
  type SlotValue,
  type Tier,
  TIER_FG,
} from "@/lib/score-components";
import type { Scenario } from "@/lib/types";
import { TapeMeter, TIER_TONE } from "@/components/ui/tape-meter";

const fmt2 = (n: number) => n.toFixed(2);

// Soft fill so the weak-link row isn't a permanent "danger"; left tick + value
// carry the tier hue.
const TIER_SOFT: Record<Tier, string> = {
  low: "bg-down/8",
  mid: "bg-warn/8",
  high: "bg-up/8",
};

function Meter({ value, tier, parent }: { value: number; tier: Tier; parent: boolean }) {
  const pct = calibratedPct(value, { parent });
  return <TapeMeter fill={pct} tone={TIER_TONE[tier]} bare />;
}

function ChainNode({
  value,
  label,
  highlight = false,
}: {
  value: number;
  label: string;
  highlight?: boolean;
}) {
  const tier = scoreTier(value, { parent: true });
  return (
    <div
      className={cn(
        "flex-1 min-w-0 rounded px-2 py-1.5 flex flex-col items-center gap-0.5 text-center",
        highlight ? "bg-accent-soft" : "bg-panel-elev/50",
      )}
    >
      <span
        className="text-[15px] font-bold ewl-num tabular-nums leading-none"
        style={{ color: TIER_FG[tier] }}
      >
        {fmt2(value)}
      </span>
      <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-text-dim font-mono">
        {label}
      </span>
    </div>
  );
}

function ChainOp({ symbol }: { symbol: string }) {
  return (
    <span
      aria-hidden="true"
      className="self-center text-muted font-semibold text-sm select-none px-0.5"
    >
      {symbol}
    </span>
  );
}

function MeasurementGroup({
  groupKey,
  rows,
  bottleneckSlotKey,
}: {
  groupKey: ComponentGroup;
  rows: SlotValue[];
  bottleneckSlotKey: string | null;
}) {
  const meta = GROUP_META[groupKey];
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1 pl-2.5">
        <span className="text-[12px] uppercase tracking-[0.14em] font-semibold text-text-dim">
          {meta.title}
        </span>
        <span className="text-[11px] text-faint italic">{meta.question}</span>
      </div>
      <div className="divide-y divide-border border-y border-border">
        {rows.map((s) => (
          <MeasurementRow key={s.key} slot={s} isWeak={s.key === bottleneckSlotKey} />
        ))}
      </div>
    </div>
  );
}

function MeasurementRow({ slot, isWeak }: { slot: SlotValue; isWeak: boolean }) {
  const tier = scoreTier(slot.value, { parent: false });
  const fgColor = TIER_FG[tier];
  return (
    <div
      className={cn(
        "relative px-2.5 py-2 space-y-1.5 transition-colors",
        isWeak && "bg-down/[0.06]",
      )}
      title={`${slot.meta.measures}\n\nFormula: ${slot.meta.formula}`}
    >
      {isWeak && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-[3px] rounded-[2px] bg-down"
          style={{ boxShadow: "0 0 7px -1px var(--color-down)" }}
        />
      )}
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5 min-w-0">
          {isWeak && (
            <>
              <Star
                className="h-3 w-3 shrink-0 fill-current text-down"
                aria-hidden="true"
              />
              <span className="sr-only">Weak link — </span>
            </>
          )}
          <span className="text-[13px] font-semibold text-text truncate">
            {slot.meta.label}
          </span>
        </span>
        <span
          className="text-[13px] font-bold ewl-num tabular-nums shrink-0"
          style={{ color: fgColor }}
        >
          {fmt2(slot.value)}
        </span>
      </div>
      <Meter value={slot.value} tier={tier} parent={false} />
    </div>
  );
}

function HowScoringWorks() {
  const { open, triggerProps, contentProps } = useDisclosure();
  return (
    <div className="border-t border-border">
      <button
        type="button"
        {...triggerProps}
        className="w-full flex items-center gap-1.5 px-1 py-2 text-[12px] uppercase tracking-[0.14em] font-semibold text-text-dim hover:text-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
      >
        <ChevronRight
          className={cn("h-3 w-3 transition-transform", open && "rotate-90")}
          aria-hidden="true"
        />
        How scoring works
      </button>
      {open && (
        <div
          {...contentProps}
          aria-label="How scoring works"
          className="px-1 pb-3 pt-1 space-y-2 text-[12px] text-text-dim leading-relaxed"
        >
          <p>
            Every total keeps only its <b>weakest</b> input — one bad measurement caps
            everything built on top of it.
          </p>
          <div className="rounded bg-bg/60 px-3 py-2 ewl-num text-[12px] space-y-1">
            <div>
              <Code>Total</Code> = <Code>Quality</Code> × <Code>Progress</Code>
            </div>
            <div>
              <Code>Quality</Code> = worst of Structure and Visual
            </div>
            <div>
              <Code>Structure</Code> = worst of Speed, Fibonacci, Pullback
            </div>
            <div>
              <Code>Visual</Code> = worst of Pivots, Smoothness{" "}
              <span className="text-faint">(needs price bars)</span>
            </div>
            <div>
              <Code>Progress</Code> = share of the pattern&apos;s required waves in place (0–1)
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold text-accent-bright">{children}</span>;
}

// PERCENT OF THE TOP score — different framing than the KPI bar's Confidence
// cell (absolute score) so they complement, not echo. Bar = relative rank;
// colour = absolute tier.
export function ConvictionReadout({
  scenario,
  topScore,
  rank,
  totalScenarios,
}: {
  scenario: Scenario;
  topScore: number;
  rank: number | null;
  totalScenarios: number;
}) {
  const pct = relativeStrengthPct(scenario.score, topScore);
  const tierKey = asTier(scenario.confidence_tier.key);
  const fg = TIER_FG[tierKey];
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="text-[12px] uppercase tracking-[0.14em] font-semibold text-text-dim">
          Relative strength
        </span>
        {rank !== null && totalScenarios > 0 && (
          <span className="text-[12px] ewl-num text-faint">
            #{rank} of {totalScenarios}
          </span>
        )}
      </div>
      <div className="flex items-end gap-3">
        <span
          className="ewl-num font-bold leading-none text-[32px] tabular-nums"
          style={{ color: fg }}
          aria-label={`Relative strength ${pct} percent of the top scenario`}
        >
          <AnimatedNumber value={pct} format={(n) => String(Math.round(n))} />
          <span className="text-[15px] text-muted">%</span>
        </span>
        <span className="mb-0.5 flex items-baseline gap-1.5 text-[12px] ewl-num text-muted">
          <span className="text-text-dim">{scenario.score.toFixed(2)}</span>
          <span className="uppercase tracking-[0.1em] font-semibold" style={{ color: fg }}>
            {scenario.confidence_tier.word}
          </span>
        </span>
      </div>
      <div className="mt-2">
        <TapeMeter fill={Math.max(2, pct)} tone={TIER_TONE[tierKey]} bare />
      </div>
    </div>
  );
}

// Colour follows the slot's tier (rose only when genuinely low). null if no slots.
export function WeakLinkRow({ scenario }: { scenario: Scenario }) {
  const { kind, progress, slot } = resolveBottleneck(scenario);
  let title: string;
  let value: number;
  let tier: Tier;
  let parent: boolean;
  if (kind === "progress" && progress !== null) {
    title = "Pattern still incomplete";
    value = progress;
    parent = true;
    tier = scoreTier(progress, { parent: true });
  } else if (kind === "slot" && slot) {
    title = `${slot.meta.label} is the weak link`;
    value = slot.value;
    parent = false;
    tier = scoreTier(slot.value, { parent: false });
  } else {
    return null;
  }
  const fg = TIER_FG[tier];
  return (
    <div className={cn("relative rounded px-3 py-2 pl-3.5 space-y-1.5", TIER_SOFT[tier])}>
      <span
        aria-hidden="true"
        className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-[3px] rounded-[2px]"
        style={{ background: fg, boxShadow: `0 0 7px -1px ${fg}` }}
      />
      <div className="flex items-center gap-2">
        <Star className="h-3 w-3 shrink-0 fill-current" style={{ color: fg }} aria-hidden="true" />
        <span className="text-[13px] font-semibold text-text flex-1 min-w-0 truncate">
          {title}
        </span>
        <span className="text-[13px] font-bold ewl-num tabular-nums shrink-0" style={{ color: fg }}>
          {fmt2(value)}
        </span>
      </div>
      <Meter value={value} tier={tier} parent={parent} />
    </div>
  );
}

export function ScoreChainRow({ scenario }: { scenario: Scenario }) {
  const c = scenario.score_components;
  const total = c.total ?? scenario.score;
  const quality = c.quality ?? null;
  const progress = c.commitment ?? null;
  const q = quality ?? total;
  const hasProgress = progress !== null;
  return (
    <div className="flex items-stretch gap-1.5">
      <ChainNode value={q} label="Quality" />
      {hasProgress && (
        <>
          <ChainOp symbol="×" />
          <ChainNode value={progress} label="Progress" />
        </>
      )}
      <ChainOp symbol="=" />
      <ChainNode value={total} label="Total" highlight />
    </div>
  );
}

export function MeasurementsBreakdown({ scenario }: { scenario: Scenario }) {
  const { slot, slots } = resolveBottleneck(scenario);
  const hasVisual = slots.some((s) => s.meta.group === "visual");
  const structural = slots.filter((s) => s.meta.group === "structural");
  const visual = slots.filter((s) => s.meta.group === "visual");
  return (
    <div className="space-y-3">
      {structural.length > 0 && (
        <MeasurementGroup groupKey="structural" rows={structural} bottleneckSlotKey={slot?.key ?? null} />
      )}
      {visual.length > 0 && (
        <MeasurementGroup groupKey="visual" rows={visual} bottleneckSlotKey={slot?.key ?? null} />
      )}
      {!hasVisual && (
        <p className="text-[12px] text-muted italic leading-snug">
          Visual checks (Pivots, Smoothness) need price bars — they are not part of this
          scenario&apos;s score.
        </p>
      )}
      <HowScoringWorks />
    </div>
  );
}
