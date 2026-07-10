from __future__ import annotations

from analyst.schemas.bottleneck import BottleneckDiagnosis
from analyst.schemas.confirmation import ConfirmationReport
from analyst.schemas.decision import AlternativeBrief, DecisionSummary
from analyst.schemas.succession import SuccessionReport
from analyst.schemas.targets import TargetSet
from analyst.taxonomy import (
    ALL_SLOTS,
    SLOT_PROSE,
    humanize_family_codes,
    slot_dimension,
)


def slot_plain(name: str) -> str:
    return SLOT_PROSE.get(name, name or "n/a")


def _leg_kind(direction: str | None) -> str:
    # Parenthetical so narration states a leg's direction instead of guessing it.
    if direction == "down":
        return " (a down leg)"
    if direction == "up":
        return " (an up leg)"
    return ""


def _ranked_from_diffs(diffs: tuple) -> list[tuple[int, str, float]]:
    # Rebuild [(rank, family, prob), ...] from consecutive pair diffs.
    first = diffs[0]
    ranked = [
        (first.primary_rank, first.primary_family, first.primary_probability),
        (first.competitor_rank, first.competitor_family,
         first.competitor_probability),
    ]
    for d in diffs[1:]:
        ranked.append(
            (d.competitor_rank, d.competitor_family, d.competitor_probability)
        )
    return ranked


def _lead_descriptor(p1: float, p2: float) -> str:
    # Characterise rank-1's lead so narration doesn't overstate a sub-50% lead.
    gap = p1 - p2
    if p1 >= 0.5 and gap >= 0.2:
        return "a decisive lead"
    if gap >= 0.15:
        return "a clear lead"
    if gap >= 0.05:
        return "a moderate lead (ahead, but far from settled)"
    return "a near-tie (essentially a toss-up)"


def format_scenario_diff(diffs: tuple) -> str:
    if not diffs:
        return (
            "## Scenario Comparison\n\n"
            "Only one scenario was found for this chart — there is no rank-2 "
            "competitor to compare against.\n"
        )

    lines = ["## Scenario Comparison\n"]

    ranked = _ranked_from_diffs(diffs)
    lines.append("Relative probability of the top scenarios:\n")
    lines.append("| Rank | Pattern family | Relative probability |")
    lines.append("|---|---|---|")
    for rank, family, prob in ranked:
        lines.append(
            f"| {rank} | {humanize_family_codes(family) or 'n/a'} | {prob:.0%} |"
        )
    if len(ranked) >= 2:
        p1, p2 = ranked[0][2], ranked[1][2]
        # Round before subtracting so the gap matches the displayed percentages.
        gap_pts = round(p1 * 100) - round(p2 * 100)
        lines.append(
            f"\n**Lead strength:** rank-1 holds {_lead_descriptor(p1, p2)} over "
            f"rank-2 — {p1:.0%} vs {p2:.0%} ({gap_pts}-point gap). "
            f"Use this phrasing for the clear-vs-close call."
        )

    d = diffs[0]
    lines.append(
        f"\n### Per-check comparison — rank {d.primary_rank} vs "
        f"rank {d.competitor_rank}\n"
    )
    lines.append(f"- **This scenario's weakest check:** {slot_plain(d.primary_bottleneck)}")
    lines.append(
        f"- **Rank-{d.competitor_rank} competitor's weakest check:** "
        f"{slot_plain(d.competitor_bottleneck)}"
    )
    lines.append(f"- **Same pattern type:** {'yes' if d.pattern_kind_match else 'no'}")
    struct_edge = "a tie" if d.structural_winner == 0 else f"the rank-{d.structural_winner} scenario"
    visual_edge = "a tie" if d.visual_winner == 0 else f"the rank-{d.visual_winner} scenario"
    lines.append(f"- **Shape-and-proportion edge:** {struct_edge}")
    lines.append(f"- **Visual-appearance edge:** {visual_edge}")
    if d.slot_deltas:
        lines.append(
            "\nPer-check gap (this scenario minus the rank-"
            f"{d.competitor_rank} competitor; positive = this scenario leads). "
            "Each check is a structural/visual grade on a 0-100 scale (NOT a "
            "probability); the gap below is in check-score points:"
        )
        lines.append("\n| Check | Gap (score points) |")
        lines.append("|---|---|")
        ranked = sorted(d.slot_deltas.items(), key=lambda kv: -abs(kv[1]))
        for name, val in ranked:
            # Bare score-points (no %) — a % would read as a probability here.
            lines.append(f"| {slot_plain(name)} | {val * 100:+.0f} |")
    return "\n".join(lines) + "\n"


def format_bottleneck(bd: BottleneckDiagnosis) -> str:
    ref = bd.theory_ref
    # Each page in its own (p.N) so the gate regex picks them up.
    pages = (
        " ".join(f"(p.{p})" for p in ref.pages)
        if ref.pages else "(no theory binding)"
    )
    binding = ref.binding.replace("_", " ")
    return (
        f"## Bottleneck Diagnosis\n\n"
        # No trailing "check" — the label has it; avoids "weakest check is … check".
        f"- **Weakest check:** {slot_plain(bd.slot_name)} "
        f"({bd.dimension}-dimension)\n"
        f"- **Binding:** {binding} — {ref.concept} {pages}\n"
        f"- **Note:** {ref.note}\n"
        f"\n{bd.plain_explanation}\n"
    )


def format_confirmation(rep: ConfirmationReport) -> str:
    if not rep.is_applicable:
        cite = (
            f"(p.{rep.not_applicable_reason.citation})"
            if rep.not_applicable_reason.citation else "(no citation)"
        )
        return (
            f"## Confirmation\n\n"
            f"**Not applicable** — "
            f"{humanize_family_codes(rep.not_applicable_reason.text)} {cite}\n"
        )
    rows = ["| Level | Condition | Met | Triggered at bar | Page |", "|---|---|---|---|---|"]
    for lv in rep.levels:
        rows.append(
            f"| {lv.name} | {lv.condition} | "
            f"{'✓' if lv.met else '✗'} | "
            f"{lv.triggered_at_bar if lv.triggered_at_bar is not None else '—'} | "
            f"(p.{lv.theory_page}) |"
        )
    highest = rep.highest_met or "none"
    return (
        f"## Confirmation ({humanize_family_codes(rep.family)})\n\n"
        + "\n".join(rows)
        + f"\n\n**Current level:** {highest}\n"
    )


_FIB_PER_GROUP_CAP = 2
_FIB_TOTAL_CAP = 16


def _diversified_fib_flow_subset(targets: tuple) -> list:
    # Group by stem so every source contributes (flat slice would only show s1).
    groups: dict[str, list] = {}
    for t in targets:
        stem = t.name.rsplit("_", 1)[0]
        groups.setdefault(stem, []).append(t)
    out: list = []
    for items in groups.values():
        for t in items[:_FIB_PER_GROUP_CAP]:
            out.append(t)
            if len(out) >= _FIB_TOTAL_CAP:
                return out
    return out


def format_targets(ts: TargetSet) -> str:
    lines = ["## Targets\n"]
    if ts.confirmation_targets:
        lines.append("### Confirmation-driven")
        for t in ts.confirmation_targets:
            # Em-dash + standalone (p.N) preserves gate regex match.
            lines.append(
                f"- {t.name}: ${t.price:.2f} — "
                f"{humanize_family_codes(t.derivation)} (p.{t.theory_page})"
            )

    # Separate heading so forecast can't be presented as measured.
    projected = tuple(t for t in ts.fib_flow_targets if t.type == "projected")
    measured = tuple(t for t in ts.fib_flow_targets if t.type != "projected")

    if measured:
        lines.append("\n### Fibonacci Flow")
        visible = _diversified_fib_flow_subset(measured)
        for t in visible:
            lines.append(f"- {t.name}: ${t.price:.2f} (p.{t.theory_page})")
        omitted = len(measured) - len(visible)
        if omitted > 0:
            lines.append(f"- … and {omitted} more (omitted for brevity).")
    if projected:
        # Filter to golden-ratio core — 0.236/1.0 led the LLM to quote ratios
        # that don't match the Decision Summary band.
        key_projected_levels = {"0.382", "0.5", "0.618"}

        def _is_key(target) -> bool:
            level = target.name.rsplit("_", 1)[-1]
            return level in key_projected_levels
        visible_proj = [t for t in projected if _is_key(t)]
        hidden_count = len(projected) - len(visible_proj)
        # Fall back to full list if filtering dropped everything.
        rendered_proj = visible_proj if visible_proj else list(projected)
        lines.append("\n### Projected (pattern still open)")
        for t in rendered_proj:
            lines.append(f"- {t.name}: ${t.price:.2f} (p.{t.theory_page})")
        if visible_proj and hidden_count > 0:
            lines.append(
                f"- … {hidden_count} additional Fibonacci levels "
                f"(0.236, 0.786, 1.0) computed but omitted — quote "
                f"only the 0.382 / 0.5 / 0.618 trio above."
            )

    lines.append(
        f"\n**Invalidation:** ${ts.invalidation.price:.2f} — "
        f"{humanize_family_codes(ts.invalidation.derivation)}"
    )
    return "\n".join(lines)


_LINK_TYPE_DISPLAY: dict[str, str] = {
    "+T": "Trend linkage",
    "+S": "Sideway linkage",
    "+SE": "Sideway-Expand linkage",
}


def format_succession(
    report: SuccessionReport, current_price: float | None = None,
) -> str:
    # link_type plain-English (raw +T/+S trips gate); current_price → %-from-current.
    header = "## What Can Follow This Pattern\n"
    if report.is_terminal or not report.next_patterns:
        note = report.note or "No Link-Wave succession applies to this family."
        return f"{header}\n{note}\n"

    def _pct_from(price: float) -> str:
        if current_price is None or current_price <= 0:
            return ""
        pct = (price - current_price) / current_price * 100.0
        return f" ({_fmt_pct(pct)} from current)"

    lines = [header]
    for npat in report.next_patterns:
        pages = " ".join(f"(p.{p})" for p in npat.theory_pages)
        families = humanize_family_codes(" or ".join(npat.next_families))
        link_display = _LINK_TYPE_DISPLAY.get(npat.link_type, npat.link_type)
        lines.append(f"### {link_display} → {families}")
        lines.append(f"- {npat.rationale} {pages}")
        if npat.link_band_near is not None and npat.link_band_far is not None:
            lo, hi = sorted((npat.link_band_near, npat.link_band_far))
            lines.append(
                f"- Projected link-wave band: ${lo:.2f}{_pct_from(lo)} "
                f"to ${hi:.2f}{_pct_from(hi)}"
            )
        elif npat.link_band_near is not None:
            lines.append(
                f"- Projected link-wave reaches at least "
                f"${npat.link_band_near:.2f}{_pct_from(npat.link_band_near)} "
                f"(open-ended — the link is sideways)"
            )
        # Surface SIZE in dollars when band is withheld so LLM quotes a concrete number.
        if (
            npat.link_wave_size is not None
            and npat.link_band_near is None
            and npat.link_band_far is None
        ):
            # +T size is the 61.8% cap (a maximum); +S size is the 78.6%/101%
            # floor (a minimum) — labelling both "at least" inverts the +T bound.
            bound = "up to" if npat.link_type == "+T" else "at least"
            lines.append(
                f"- Link wave size (band not yet anchorable while the "
                f"pattern is open): {bound} ${npat.link_wave_size:.2f} "
                f"in price span"
            )
    return "\n".join(lines) + "\n"


def _fmt_pct(p: float) -> str:
    sign = "+" if p > 0 else ("-" if p < 0 else "±")
    return f"{sign}{abs(p):.1f}%"


_INTERVAL_TO_CHART_PROSE: dict[str, str] = {
    "1m": "1-minute chart",
    "5m": "5-minute chart",
    "15m": "15-minute chart",
    "30m": "30-minute chart",
    "1h": "hourly chart",
    "4h": "4-hour chart",
    "1d": "daily chart",
    "1w": "weekly chart",
}


_STAGE_PROSE: dict[str, str] = {
    "early":     ("EARLY — price is near the open wave's start; the projection "
                  "band is still mostly ahead. Talk about the band as the "
                  "upcoming destination."),
    "mid":       ("MID-WAVE — price sits inside the projection band; the open "
                  "wave is unfolding as theory expects. Talk about the band's "
                  "far edge as the upcoming completion."),
    "late":      ("LATE — price is approaching the far edge of the band; the "
                  "projection is nearly exhausted. Frame completion as "
                  "imminent rather than upcoming."),
    "overshot":  ("OVERSHOT — price has crossed BEYOND the band's far edge. "
                  "Do NOT describe the band as 'where the move is going' — "
                  "it is now behind. Treat this as a meaningful event: the "
                  "open wave is running past theory's expectation, which may "
                  "signal the count is about to invalidate (price keeps "
                  "going) or that the wave is exhausted near here."),
    "complete":  ("COMPLETE — the pattern is closed; the projection band "
                  "describes the measured Fibonacci Flow targets after "
                  "completion, not an upcoming destination."),
    "unknown":   ("STAGE UNCLEAR — the band or open-wave start could not be "
                  "established."),
}


def format_decision_summary(ds: DecisionSummary) -> str:
    lines = ["## Decision Summary\n"]
    lines.append(f"- **Current price:** ${ds.current.price:,.2f}")
    if ds.open_wave_start is not None:
        delta = ((ds.current.price - ds.open_wave_start) / ds.open_wave_start
                 * 100 if ds.open_wave_start > 0 else 0)
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- **Open wave started at:** ${ds.open_wave_start:,.2f} "
            f"({sign}{delta:.1f}% to current)"
        )
    if ds.open_wave_direction is not None:
        # Differentiator's "watch for fifth leg X-ward" needs this; else model guesses.
        arrow = "↑ UP" if ds.open_wave_direction == "up" else "↓ DOWN"
        lines.append(
            f"- **Open wave direction:** {arrow} — by Elliott Wave "
            f"alternation, the open wave is expected to travel "
            f"{ds.open_wave_direction.upper()} from its start"
        )
    if ds.wave_progress_pct is not None:
        lines.append(
            f"- **Wave progress:** {ds.wave_progress_pct:.0f}% of the "
            f"projection band's span from the open wave's start"
        )
    if ds.overshoot_amount is not None and ds.overshoot_pct_of_span is not None:
        # Distinct from Wave progress — distance past the edge, not from the start.
        lines.append(
            f"- **Overshoot beyond far edge:** +${ds.overshoot_amount:,.2f} "
            f"({ds.overshoot_pct_of_span:.0f}% of the band span past the far "
            f"edge) — quote this for the amount exceeded, NOT the wave-progress %"
        )
    if ds.stage and ds.stage != "unknown":
        # _STAGE_PROSE already opens with the label — prepending ds.stage doubles it.
        lines.append(
            f"- **Stage:** {_STAGE_PROSE.get(ds.stage, _STAGE_PROSE['unknown'])}"
        )
    if ds.target_high is not None and ds.target_low is not None:
        lo, hi = ds.target_low, ds.target_high
        lines.append(
            f"- **Projection band:** ${lo.price:,.2f} "
            f"({_fmt_pct(lo.pct_from_current)} from current) to "
            f"${hi.price:,.2f} ({_fmt_pct(hi.pct_from_current)} from current)"
        )
    if ds.invalidation is not None:
        lines.append(
            f"- **Invalidation:** ${ds.invalidation.price:,.2f} "
            f"({_fmt_pct(ds.invalidation.pct_from_current)} from current)"
        )
    if ds.risk_reward is not None:
        lines.append(
            f"- **Risk:Reward:** 1 : {ds.risk_reward:.1f} "
            f"(reward measured to the band's midpoint)"
        )
    if ds.direction is not None:
        lines.append(f"- **Implied direction:** {ds.direction}")
    if ds.horizon_bars is not None:
        line = (
            f"- **Rough time horizon:** ~{ds.horizon_bars} bars to complete "
            f"the open wave"
        )
        if ds.horizon_human and ds.bar_interval:
            chart_label = _INTERVAL_TO_CHART_PROSE.get(
                ds.bar_interval, f"{ds.bar_interval} chart",
            )
            line += f" (≈ {ds.horizon_human} on this {chart_label})"
        line += " — median of formed legs, not a theory guarantee"
        lines.append(line)
    return "\n".join(lines) + "\n"


def format_weakness_detail(
    bottleneck: BottleneckDiagnosis | None,
    score_components: dict | None,
    intermediates_map: dict | None = None,
) -> str:
    # intermediates_map = AnalysisResult.score_intermediates; lets 2nd/3rd slots quote per-leg.
    if bottleneck is None or not score_components:
        return ""
    active_slots = {
        k for k in score_components
        if k in ALL_SLOTS
        and isinstance(score_components.get(k), (int, float))
    }
    if not active_slots:
        return ""
    # Back-compat: fall back to verbose-dict-style components for legacy callers.
    inter_map = intermediates_map or score_components.get("intermediates", {}) or {}
    ranked = sorted(active_slots, key=lambda s: score_components[s])[:3]
    if not ranked:
        return ""

    lines = ["## Top-3 Weakness Detail\n"]
    for rank, slot in enumerate(ranked, start=1):
        plain = SLOT_PROSE.get(slot, slot)
        ordinal = ("weakest", "second-weakest", "third-weakest")[rank - 1]
        inter = inter_map.get(slot, {})
        detail = _slot_detail_line(slot, inter)
        if detail:
            lines.append(f"- **{ordinal.title()} — {plain}:** {detail}")
        else:
            # Phrased as "<dim>-dimension slot; ranked by score only" — not a warning.
            dim = slot_dimension(slot)
            lines.append(
                f"- **{ordinal.title()} — {plain}:** {dim}-dimension "
                f"slot; ranked by score only for this scenario."
            )
    return "\n".join(lines) + "\n"


def _slot_detail_line(slot: str, inter: dict) -> str:
    # Denser bottleneck._build_explanation — fits a top-3 list.
    if slot == "speed_cluster":
        speeds = inter.get("leg_speeds", [])
        if speeds:
            lo, hi = min(speeds), max(speeds)
            spread = f"{hi/lo:.2f}×" if lo > 0 else "extreme"
            return (
                f"leg pace ranges {lo:.2f}–{hi:.2f} (price per bar), "
                f"a {spread} spread"
            )
    if slot == "fib_push_pairs":
        pairs = inter.get("pairs", [])
        if pairs:
            worst = max(pairs, key=lambda p: p["distance"])
            return (
                f"worst pair {worst['pair']} sits {worst['distance']:.3f} "
                f"from the nearest Fibonacci level"
            )
    if slot == "pull_depth_discipline":
        pairs = inter.get("pairs", [])
        if pairs:
            in_window = sum(1 for p in pairs if p.get("in_window"))
            out_window = len(pairs) - in_window
            depths = ", ".join(
                f"{p['depth']:.3f}" for p in pairs if not p.get("in_window")
            )
            if out_window:
                return (
                    f"{out_window} of {len(pairs)} pullbacks fall outside the "
                    f"healthy 0.382-0.618 window (depths: {depths or 'n/a'})"
                )
            return (
                f"all {len(pairs)} pullbacks sit inside the 0.382-0.618 "
                f"window but cluster at the band's edges"
            )
    if slot == "leg_smoothness":
        per_leg = inter.get("per_leg", [])
        if per_leg:
            worst = max(per_leg, key=lambda leg: leg.get("ratio", 0.0))
            kind = _leg_kind(worst.get("direction"))
            return (
                f"leg {worst['leg_idx'] + 1}{kind}'s deepest counter-swing — its "
                f"largest move AGAINST the leg's own direction — ran "
                f"{worst['ratio']:.3f}× the leg's net travel (its drawdown "
                f"ratio), measured within this leg only; a clean impulse stays "
                f"under 1.0"
            )
    if slot == "pivot_sharpness":
        per_pivot = inter.get("per_pivot", [])
        if per_pivot:
            worst = min(per_pivot, key=lambda p: p.get("sharpness_score", 1.0))
            return (
                f"pivot {worst['pivot_idx']} is the dullest turning point on "
                f"the chart"
            )
    return ""


def format_alternative_brief(brief: AlternativeBrief) -> str:
    lines = ["## Alternative Scenario\n"]
    lines.append(
        f"- **Rank-2 family:** {humanize_family_codes(brief.family_label)}"
    )
    if brief.direction is not None:
        lines.append(f"- **Implied direction (from current):** {brief.direction}")
    if brief.stage and brief.stage != "unknown":
        lines.append(f"- **Stage of its open wave:** {brief.stage.upper()}")
    if brief.target_low is not None and brief.target_high is not None:
        lines.append(
            f"- **Projection band:** ${brief.target_low.price:,.2f} "
            f"({_fmt_pct(brief.target_low.pct_from_current)} from current) "
            f"to ${brief.target_high.price:,.2f} "
            f"({_fmt_pct(brief.target_high.pct_from_current)} from current)"
        )
    if brief.invalidation is not None:
        lines.append(
            f"- **Invalidation:** ${brief.invalidation.price:,.2f} "
            f"({_fmt_pct(brief.invalidation.pct_from_current)} from current)"
        )
    return "\n".join(lines) + "\n"
