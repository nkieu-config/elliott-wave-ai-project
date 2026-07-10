from __future__ import annotations

import math

from ..scoring_config import ScoringConfig
from ..types import _Leg
from .constants import LOG_FIB_LEVELS
from .helpers import _log_cv_score


def _bar_span(leg: _Leg) -> int | None:
    if leg.span_start is None or leg.span_end is None:
        return None
    if leg.span_start.bar_index is None or leg.span_end.bar_index is None:
        return None
    return leg.span_end.bar_index - leg.span_start.bar_index


def _price_len(leg: _Leg) -> float:
    # Net-span-0 sub-patterns (3W S2_LONGER_S3_SHORTER) fall back to intra-path sum.
    direct = abs(leg.span_end.price - leg.span_start.price)
    if direct > 0 or not leg.sub_legs:
        return direct
    return sum(abs(s.span_end.price - s.span_start.price) for s in leg.sub_legs)


def _leg_speeds(legs: list[_Leg]) -> list[float] | None:
    speeds: list[float] = []
    for leg in legs:
        bar_span = _bar_span(leg)
        price_len = _price_len(leg)
        if bar_span is None or bar_span <= 0 or price_len <= 0:
            return None
        speeds.append(price_len / bar_span)
    return speeds


def speed_cluster(legs: list[_Leg], config: ScoringConfig | None = None) -> float | None:
    cfg = config or ScoringConfig()
    if len(legs) < 2:
        return None
    speeds = _leg_speeds(legs)
    if speeds is None:
        return None
    return _log_cv_score(speeds, K=cfg.k_sigma)


def speed_cluster_verbose(
    legs: list[_Leg], config: ScoringConfig | None = None
) -> tuple[float | None, dict]:
    cfg = config or ScoringConfig()
    if len(legs) < 2:
        return None, {}
    speeds = _leg_speeds(legs)
    if speeds is None:
        return None, {}
    score = _log_cv_score(speeds, K=cfg.k_sigma)
    return score, {"leg_speeds": speeds, "log_cv_score": score}


def _push_sizes(legs: list[_Leg]) -> list[float]:
    push = legs[0::2]
    return [_price_len(leg) for leg in push if _price_len(leg) > 0]


def fib_push_pairs(legs: list[_Leg], config: ScoringConfig | None = None) -> float | None:
    cfg = config or ScoringConfig()
    sizes = _push_sizes(legs)
    if len(sizes) < 2:
        return None
    scores: list[float] = []
    for i in range(len(sizes)):
        for j in range(i + 1, len(sizes)):
            log_ratio = math.log(sizes[j] / sizes[i])
            d = min(abs(log_ratio - lf) for lf in LOG_FIB_LEVELS)
            scores.append(math.exp(-d / cfg.log_tol_fib))
    if not scores:
        return None
    return sum(scores) / len(scores)


# Plain fib_push_pairs duplicates this loop rather than projecting _verbose(...)[0]:
# the beam hot path must not pay for the per-pair detail dict allocated here.
def fib_push_pairs_verbose(
    legs: list[_Leg], config: ScoringConfig | None = None
) -> tuple[float | None, dict]:
    cfg = config or ScoringConfig()
    sizes = _push_sizes(legs)
    if len(sizes) < 2:
        return None, {}
    pairs: list[dict] = []
    scores: list[float] = []
    for i in range(len(sizes)):
        for j in range(i + 1, len(sizes)):
            log_ratio = math.log(sizes[j] / sizes[i])
            d, nearest = min(
                ((abs(log_ratio - lf), lf) for lf in LOG_FIB_LEVELS),
                key=lambda x: x[0],
            )
            s = math.exp(-d / cfg.log_tol_fib)
            scores.append(s)
            pairs.append(
                {
                    "pair": (i, j),
                    "log_ratio": log_ratio,
                    "nearest_log_fib": nearest,
                    "distance": d,
                    "score": s,
                }
            )
    if not scores:
        return None, {}
    return sum(scores) / len(scores), {"pairs": pairs}


def _pull_depth_pairs(
    legs: list[_Leg], cfg: ScoringConfig
) -> list[tuple[int, float, bool, float]]:
    out: list[tuple[int, float, bool, float]] = []
    for i in range(0, len(legs) - 1, 2):
        push, pull = legs[i], legs[i + 1]
        push_len = _price_len(push)
        if push_len <= 0:
            continue
        depth = _price_len(pull) / push_len
        in_window = cfg.pull_depth_lo <= depth <= cfg.pull_depth_hi
        if in_window:
            score = 1.0
        else:
            dist = min(abs(depth - cfg.pull_depth_lo), abs(depth - cfg.pull_depth_hi))
            score = math.exp(-dist / cfg.pull_depth_tol)
        out.append((i, depth, in_window, score))
    return out


def pull_depth_discipline(legs: list[_Leg], config: ScoringConfig | None = None) -> float | None:
    cfg = config or ScoringConfig()
    pairs = _pull_depth_pairs(legs, cfg)
    if not pairs:
        return None
    return sum(score for *_, score in pairs) / len(pairs)


def pull_depth_discipline_verbose(
    legs: list[_Leg], config: ScoringConfig | None = None
) -> tuple[float | None, dict]:
    cfg = config or ScoringConfig()
    pairs = _pull_depth_pairs(legs, cfg)
    if not pairs:
        return None, {}
    scores = [score for *_, score in pairs]
    detail = [
        {"pair": (i, i + 1), "depth": depth, "in_window": in_window, "score": score}
        for i, depth, in_window, score in pairs
    ]
    return sum(scores) / len(scores), {"pairs": detail}
