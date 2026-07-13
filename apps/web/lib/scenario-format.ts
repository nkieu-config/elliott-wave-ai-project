import type { ClosedWave, SampleData, Scenario, Wave } from "./types";

// Family hues must not collide with the tier scale (down/warn/up). TREND uses
// blue, not accent (=--color-up): a green badge would falsely read as bullish.
export const FAMILY_COLORS: Record<string, string> = {
  "5W_TREND": "var(--color-blue)",
  "5W_SIDEWAY": "var(--color-cyan)",
  "3W": "var(--color-violet)",
};

export function familyColor(family: string): string {
  return FAMILY_COLORS[family] ?? "var(--color-muted)";
}

export function prettyFamily(family: string): string {
  return family.replaceAll("_", " "); // every underscore, not just the first
}

export function prettyFamilyUpper(family: string): string {
  return prettyFamily(family).toUpperCase();
}

// Subtype slice of "<family> · <subtype>"; family already shown on the chip.
export function patternSubtype(label: string | null): string {
  if (!label) return "";
  const idx = label.lastIndexOf("·");
  return (idx === -1 ? label : label.slice(idx + 1)).trim();
}

// Parser-internal roles s1..s5 display as Elliott W1..W5.
const ROLE_SHORT: Record<string, string> = {
  anchor: "ANCHOR",
  s1: "W1",
  s2: "W2",
  s3: "W3",
  s4: "W4",
  s5: "W5",
  link: "LINK",
  set_1: "SET1",
  set_2: "SET2",
  set_3: "SET3",
};
export function roleShort(role: string): string {
  return ROLE_SHORT[role] ?? role.toUpperCase();
}

// Drawable child legs (skip anchor, require span_end). Drill indices index into
// THIS filtered array.
export function drawableLegs(node: Wave): ClosedWave[] {
  return node.children.filter(
    (c): c is ClosedWave => c.role !== "anchor" && c.span_end !== null,
  );
}

// Null if any index is stale (caller falls back to root).
export function resolveScopeNode(scenario: Scenario, path: number[]): Wave | null {
  let node: Wave = scenario.root;
  for (const idx of path) {
    const next = drawableLegs(node)[idx];
    if (!next) return null;
    node = next;
  }
  return node;
}

// Invalid path falls back to root legs so the chart never goes blank.
export function scopeLegs(scenario: Scenario, path: number[]): ClosedWave[] {
  const node = resolveScopeNode(scenario, path);
  return drawableLegs(node ?? scenario.root);
}

// Short-circuit (no array alloc) — called per-leg on hot draw/drill paths.
export function isDrillable(leg: Wave): boolean {
  return leg.children.some((c) => c.role !== "anchor" && c.span_end !== null);
}

// Starts with Root, then one crumb per resolved leg; stops early at a stale
// index so the trail never lies.
export function buildDrillCrumbs(
  scenario: Scenario,
  path: number[],
): { label: string; path: number[] }[] {
  const crumbs: { label: string; path: number[] }[] = [{ label: "Root", path: [] }];
  let node = scenario.root;
  for (let i = 0; i < path.length; i++) {
    const leg = drawableLegs(node)[path[i]];
    if (!leg) break;
    crumbs.push({ label: roleShort(leg.role), path: path.slice(0, i + 1) });
    node = leg;
  }
  return crumbs;
}

// ?scenario= id if it still exists, else top scorer, else first, else null.
export function findSelectedScenario(
  data: SampleData | undefined,
  selectedId: string | null,
): Scenario | null {
  if (!data?.report) return data?.top_scenario ?? null;
  if (selectedId) {
    const hit = data.report.scenarios.find((s) => s.id === selectedId);
    if (hit) return hit;
  }
  return data.top_scenario ?? data.report.scenarios[0] ?? null;
}
