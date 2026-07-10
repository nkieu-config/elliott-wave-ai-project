from __future__ import annotations

from dataclasses import replace

from analyst.schemas.succession import NextPattern, SuccessionReport
from engine import PatternKind, Scenario, WaveNode

_MAX_LINK_SETS = 3

# +T connector size as fraction of prior S3 (p.64).
_T_LINK_MIN_FRAC = 0.01
_T_LINK_MAX_FRAC = 0.618

# p.73 — 78.6% of 3-Wave's full range / s5 leg
_S_LINK_MIN_FRAC_3W = 0.786
# p.74 — 101% of 5W-Sideway Contract/Balance
_S_LINK_MIN_FRAC_5WS = 1.01


def _leg_size(leg: WaveNode) -> float:
    return abs(leg.span_end.price - leg.span_start.price)


def _range_of(legs: list[WaveNode]) -> float:
    prices: list[float] = []
    for leg in legs:
        if leg.span_start is not None:
            prices.append(leg.span_start.price)
        if leg.span_end is not None:
            prices.append(leg.span_end.price)
    return (max(prices) - min(prices)) if prices else 0.0


def _full_range(sc: Scenario) -> float:
    return _range_of(sc.legs)


def _last_set_legs(sc: Scenario) -> list[WaveNode]:
    sets = sc.root.sets
    if not sets:
        return []
    ls = sets[-1]
    return sc.root.children[ls.leg_start : ls.leg_end + 1]


def _end_price(sc: Scenario) -> float | None:
    end = sc.root.span_end or (sc.legs[-1].span_end if sc.legs else None)
    return end.price if end else None


def _trend_sign(sc: Scenario) -> int:
    start = sc.root.span_start
    end = sc.root.span_end or (sc.legs[-1].span_end if sc.legs else None)
    if start is None or end is None:
        return 1
    return 1 if end.price >= start.price else -1


def _last_leg_sign(sc: Scenario) -> int:
    if not sc.legs:
        return _trend_sign(sc)
    leg = sc.legs[-1]
    if leg.span_start is None or leg.span_end is None:
        return _trend_sign(sc)
    return 1 if leg.span_end.price >= leg.span_start.price else -1


def _band(end: float | None, sign: int, base: float | None,
          near_frac: float, far_frac: float | None) -> tuple[float | None, float | None]:
    if end is None or not base:
        return None, None
    near = end + sign * near_frac * base
    far = end + sign * far_frac * base if far_frac is not None else None
    return near, far


def _without_price_band(report: SuccessionReport) -> SuccessionReport:
    # Link wave anchors at the END pivot; while open, drop the band (rules hold).
    patched: list[NextPattern] = []
    for npat in report.next_patterns:
        had_band = (
            npat.link_band_near is not None or npat.link_band_far is not None
        )
        rationale = npat.rationale
        if had_band:
            rationale += (
                " The link-wave price band can be projected once this "
                "pattern completes."
            )
        patched.append(replace(
            npat, link_band_near=None, link_band_far=None, rationale=rationale,
        ))
    return replace(report, next_patterns=tuple(patched))


def compute_succession(sc: Scenario) -> SuccessionReport:
    family = sc.family
    if family == "5W_TREND":
        return SuccessionReport(
            family=family, is_terminal=True, next_patterns=(),
            note=("A 5-Wave Trend admits no Link-Wave successor — both +T "
                  "(p.59) and +S (p.67) forbid linking a 5-Wave Trend."),
        )
    if family == "3W":
        report = _succession_after_3w(sc)
    elif family == "5W_SIDEWAY":
        report = _succession_after_5ws(sc)
    elif family in ("LINK_T", "LINK_S", "LINK_SE"):
        report = _succession_after_link(sc)
    else:
        return SuccessionReport(
            family=family, is_terminal=False, next_patterns=(),
            note="No Link-Wave succession rule is defined for this family.",
        )

    return report if sc.is_complete else _without_price_band(report)


def _succession_after_3w(sc: Scenario) -> SuccessionReport:
    end = _end_price(sc)
    legs = sc.legs

    # +T — connector 1%-61.8% of prior S3 (p.64), counter-trend.
    s3 = _leg_size(legs[2]) if len(legs) >= 3 else None
    t_near, t_far = _band(end, -_trend_sign(sc), s3,
                          _T_LINK_MIN_FRAC, _T_LINK_MAX_FRAC)
    # Anchor-independent sizes so LLM can quote dollars when band withheld.
    t_size = s3 * _T_LINK_MAX_FRAC if s3 is not None else None
    s_size = _full_range(sc) * _S_LINK_MIN_FRAC_3W
    plus_t = NextPattern(
        link_type="+T", next_families=("3W",),
        link_band_near=t_near, link_band_far=t_far,
        theory_pages=(57, 59, 64),
        rationale=(
            "A 3-Wave may begin a Trend linkage: a connecting wave of "
            "1%-61.8% of the previous Wave 3, then another 3-Wave resumes "
            "the trend."
        ),
        link_wave_size=t_size,
    )

    # +S — wave ≥ 78.6% of 3-Wave's full range (p.73), open above.
    s_near, _ = _band(end, -_last_leg_sign(sc), _full_range(sc),
                      _S_LINK_MIN_FRAC_3W, None)
    plus_s = NextPattern(
        link_type="+S", next_families=("3W", "5W_SIDEWAY"),
        link_band_near=s_near, link_band_far=None,
        theory_pages=(57, 67, 73),
        rationale=(
            "A 3-Wave may begin a Sideway linkage: a connecting wave of "
            "at least 78.6% of this 3-Wave's full range, then a 3-Wave or "
            "5-Wave Sideway set."
        ),
        link_wave_size=s_size,
    )
    return SuccessionReport(family="3W", is_terminal=False,
                            next_patterns=(plus_t, plus_s), note="")


def _succession_after_5ws(sc: Scenario) -> SuccessionReport:
    end = _end_price(sc)
    legs = sc.legs

    # +S size basis: Expand → 78.6% of s5 (p.73); CB → 101% of pattern range (p.74).
    if sc.pattern_kind == PatternKind.FIVE_SIDEWAY_EXPAND:
        base = _leg_size(legs[4]) if len(legs) >= 5 else None
        min_frac, pages = _S_LINK_MIN_FRAC_3W, (57, 67, 73)
        basis = "78.6% of the Wave 5 leg"
    else:
        base = _full_range(sc)
        min_frac, pages = _S_LINK_MIN_FRAC_5WS, (57, 67, 74)
        basis = "101% of this pattern's full range"

    s_near, _ = _band(end, -_last_leg_sign(sc), base, min_frac, None)
    s_size = base * min_frac if base is not None else None
    plus_s = NextPattern(
        link_type="+S", next_families=("3W", "5W_SIDEWAY"),
        link_band_near=s_near, link_band_far=None,
        theory_pages=pages,
        rationale=(
            f"A 5-Wave Sideway may be linked only by a Sideway linkage — a "
            f"Trend linkage cannot link any 5-Wave. The Sideway link wave "
            f"must exceed {basis}, followed by a 3-Wave or 5-Wave Sideway "
            f"set."
        ),
        link_wave_size=s_size,
    )
    return SuccessionReport(family="5W_SIDEWAY", is_terminal=False,
                            next_patterns=(plus_s,), note="")


def _succession_after_link(sc: Scenario) -> SuccessionReport:
    family = sc.family
    # An open link root whose first set hasn't closed has sets=None (0 completed
    # sets) — targets.py guards the same field; succession must too, else layer1 500s.
    n_sets = len(sc.root.sets or [])
    if n_sets >= _MAX_LINK_SETS:
        return SuccessionReport(
            family=family, is_terminal=True, next_patterns=(),
            note=(f"This Link-Wave already holds {n_sets} sets — theory caps "
                  f"a linkage at 3 sets (p.59) (p.67)."),
        )

    end = _end_price(sc)
    last_set = _last_set_legs(sc)

    if family == "LINK_T":
        # +T extension — connector 1%-61.8% of last set's S3 (p.64).
        s3 = _leg_size(last_set[2]) if len(last_set) >= 3 else None
        near, far = _band(end, -_trend_sign(sc), s3,
                          _T_LINK_MIN_FRAC, _T_LINK_MAX_FRAC)
        ext_size = s3 * _T_LINK_MAX_FRAC if s3 is not None else None
        extend = NextPattern(
            link_type="+T", next_families=("3W",),
            link_band_near=near, link_band_far=far,
            theory_pages=(57, 59, 64),
            rationale=(
                f"This Trend linkage holds {n_sets} set(s) and may take one "
                f"more 3-Wave (3 sets maximum); the connecting wave spans "
                f"1%-61.8% of the last set's Wave 3."
            ),
            link_wave_size=ext_size,
        )
    else:  # LINK_S / LINK_SE
        # +S extension size depends on the last set's kind, mirroring the standalone
        # 5WS rule: Expand → 78.6% of its Wave 5 leg (p.73); Contract/Balance → 101%
        # of its range (p.74); a 3W set → 78.6% of its full range (p.73).
        last_kind = sc.root.sets[-1].pattern_kind if sc.root.sets else None
        if last_kind == PatternKind.FIVE_SIDEWAY_EXPAND:
            base = _leg_size(last_set[4]) if len(last_set) >= 5 else None
            min_frac, s_pages = _S_LINK_MIN_FRAC_3W, (57, 67, 73)
            basis = "78.6% of the last set's Wave 5 leg"
        elif last_kind in (PatternKind.FIVE_SIDEWAY_CONTRACT, PatternKind.FIVE_SIDEWAY_BALANCE):
            base = _range_of(last_set)
            min_frac, s_pages = _S_LINK_MIN_FRAC_5WS, (57, 67, 74)
            basis = "101% of the last set's full range"
        else:
            base = _range_of(last_set)
            min_frac, s_pages = _S_LINK_MIN_FRAC_3W, (57, 67, 73)
            basis = "78.6% of the last set's full range"
        near, _ = _band(end, -_last_leg_sign(sc), base, min_frac, None)
        ext_size = base * min_frac if base else None
        extend = NextPattern(
            link_type="+S", next_families=("3W", "5W_SIDEWAY"),
            link_band_near=near, link_band_far=None,
            theory_pages=s_pages,
            rationale=(
                f"This Sideway linkage holds {n_sets} set(s) and may take "
                f"one more 3-Wave or 5-Wave Sideway (3 sets maximum); the "
                f"link wave spans at least {basis}."
            ),
            link_wave_size=ext_size,
        )
    return SuccessionReport(family=family, is_terminal=False,
                            next_patterns=(extend,), note="")
