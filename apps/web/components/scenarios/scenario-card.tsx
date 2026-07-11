import { CheckCircle2, GitCompare, Hourglass } from "lucide-react";
import { memo } from "react";
import { cn } from "@/lib/cn";
import { relativeStrengthPct } from "@/lib/scenario-ranking";
import { familyColor, patternSubtype, prettyFamily, roleShort } from "@/lib/scenario-format";
import { asTier } from "@/lib/score-components";
import type { Scenario } from "@/lib/types";
import { RankBadge } from "@/components/scenarios/scenario-bits";
import { TapeMeter, TIER_TONE } from "@/components/ui/tape-meter";

// memo'd so only cards whose selection/compare state flipped re-render on a
// pick, not the whole 60+ row list.
export const ScenarioCard = memo(function ScenarioCard({
  scoreRank,
  medalRank,
  scenario,
  topScore,
  selected,
  isCompared,
  canCompare,
  onSelect,
  onToggleCompare,
}: {
  scoreRank: number;
  medalRank: 1 | 2 | 3 | null;
  scenario: Scenario;
  /** Highest score across the set — normalises the relative-strength bar/figure. */
  topScore: number;
  selected: boolean;
  isCompared: boolean;
  canCompare: boolean;
  onSelect: (id: string) => void;
  onToggleCompare: (sc: Scenario) => void;
}) {
  const color = familyColor(scenario.family);
  const pct = relativeStrengthPct(scenario.score, topScore);
  // Bar length = relative strength; hue = absolute tier (different questions).
  const tone = TIER_TONE[asTier(scenario.confidence_tier.key)];
  const formingRole =
    !scenario.is_complete && scenario.open_subtree ? scenario.open_subtree.role : null;

  return (
    <li className="relative">
      <button
        type="button"
        onClick={() => onSelect(scenario.id)}
        aria-pressed={selected}
        data-scenario-id={scenario.id}
        className={cn(
          // Flat row, not a card — selection is the parent's gliding band.
          "group relative w-full text-left rounded transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset",
          !selected && "hover:bg-panel-elev/50",
        )}
      >
        {/* Family identity tick — no glow; the selection band is the one halo. */}
        <span
          aria-hidden="true"
          className="absolute left-1 top-1/2 -translate-y-1/2 h-3.5 w-[3px] rounded-[2px]"
          style={{ background: color }}
        />

        <div className="flex items-center gap-3 pl-4 pr-3.5 py-2.5">
          <RankBadge scoreRank={scoreRank} medalRank={medalRank} selected={selected} />

          <div className="flex-1 min-w-0 space-y-1.5">
            <div className="flex items-baseline gap-2">
              <span
                className="text-[12px] font-bold uppercase tracking-[0.1em]"
                style={{ color }}
              >
                {prettyFamily(scenario.family)}
              </span>
              {scenario.pattern_label && (
                <span className="text-[12px] text-muted truncate">
                  {patternSubtype(scenario.pattern_label)}
                </span>
              )}
              {scenario.is_complete ? (
                <CheckCircle2
                  className="ml-auto h-3 w-3 text-up shrink-0"
                  aria-label="Complete"
                />
              ) : (
                <span
                  className="ml-auto inline-flex items-center gap-1 text-[11px] text-warn ewl-num font-semibold uppercase tracking-[0.1em] shrink-0"
                  aria-label={formingRole ? `Open — forming ${roleShort(formingRole)}` : "Open"}
                >
                  <Hourglass className="h-2.5 w-2.5" />
                  {formingRole && <span>{roleShort(formingRole)}</span>}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <TapeMeter fill={pct} tone={tone} bare animate={false} />
              </div>
              <span
                className={cn(
                  "text-[13px] ewl-num shrink-0 font-semibold tabular-nums",
                  selected ? "text-accent-bright" : "text-text",
                )}
              >
                {pct}
                <span className="text-[10px] text-faint">%</span>
              </span>
            </div>
          </div>
        </div>
      </button>
      {/* Outside the main button so its click doesn't bubble into onSelect. */}
      {canCompare && (
        <div className="absolute top-1 right-1">
          <button
            type="button"
            onClick={() => onToggleCompare(scenario)}
            aria-label={isCompared ? "Stop comparing" : "Compare against selected"}
            aria-pressed={isCompared}
            title={isCompared ? "Stop comparing" : "Compare against selected"}
            className={cn(
              "relative grid place-items-center w-6 h-6 rounded transition-[background-color,color,opacity] after:absolute after:inset-[-10px] after:content-['']",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              "[@media(hover:none)]:opacity-100",
              isCompared
                ? "text-violet bg-violet-soft opacity-100"
                : "text-faint opacity-0 group-hover:opacity-100 hover:text-text hover:bg-panel-elev",
            )}
          >
            <GitCompare className="h-3 w-3" />
          </button>
        </div>
      )}
    </li>
  );
});
