"""Station Difficulty Index (SDI) computation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StationWeights:
    w_single: float = 0.4
    w_double_1: float = 0.3
    w_double_2: float = 0.3

    def __post_init__(self) -> None:
        total = self.w_single + self.w_double_1 + self.w_double_2
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Station weights must sum to 1.0, got {total}")


@dataclass(frozen=True, slots=True)
class StationDifficulty:
    station: int
    hit_rate_single: float | None
    hit_rate_double_1: float | None
    hit_rate_double_2: float | None
    sdi: float
    n_single: int
    n_double_1: int
    n_double_2: int


def _mean_hits(hits: list[bool]) -> float | None:
    if not hits:
        return None
    return sum(1 for h in hits if h) / len(hits)


def compute_sdi(
    shots: Sequence[Mapping[str, Any]],
    weights: StationWeights | None = None,
) -> list[StationDifficulty]:
    """
    SDI_s = 1 - (w_single * X_single + w_d1 * X_d1 + w_d2 * X_d2)

    Missing categories are excluded and remaining weights are renormalized.
    """
    w = weights or StationWeights()
    buckets: dict[int, dict[str, list[bool]]] = defaultdict(
        lambda: {"single": [], "d1": [], "d2": []}
    )

    for s in shots:
        station = int(s["station"])
        hit = bool(s["is_hit"])
        pair_pos = int(s["pair_position"])
        if pair_pos == 0:
            buckets[station]["single"].append(hit)
        elif pair_pos == 1:
            buckets[station]["d1"].append(hit)
        elif pair_pos == 2:
            buckets[station]["d2"].append(hit)

    results: list[StationDifficulty] = []
    for station in range(1, 9):
        b = buckets[station]
        xs = _mean_hits(b["single"])
        xd1 = _mean_hits(b["d1"])
        xd2 = _mean_hits(b["d2"])

        parts: list[tuple[float, float]] = []
        if xs is not None:
            parts.append((w.w_single, xs))
        if xd1 is not None:
            parts.append((w.w_double_1, xd1))
        if xd2 is not None:
            parts.append((w.w_double_2, xd2))

        if not parts:
            sdi = 1.0  # no data => maximally uncertain / difficult placeholder
            weighted = 0.0
        else:
            w_sum = sum(pw for pw, _ in parts)
            weighted = sum(pw * rate for pw, rate in parts) / w_sum
            sdi = 1.0 - weighted

        results.append(
            StationDifficulty(
                station=station,
                hit_rate_single=xs,
                hit_rate_double_1=xd1,
                hit_rate_double_2=xd2,
                sdi=sdi,
                n_single=len(b["single"]),
                n_double_1=len(b["d1"]),
                n_double_2=len(b["d2"]),
            )
        )
    return results
