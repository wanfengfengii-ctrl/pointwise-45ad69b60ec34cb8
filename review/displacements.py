from dataclasses import dataclass

from .alignment import Placement
from .requests import ReviewRequest


@dataclass(frozen=True, slots=True)
class DisplacementResult:
    start: str
    end: str
    millimeters: int | None


@dataclass(frozen=True, slots=True)
class RangeResult:
    start: str
    end: str
    minimum: int | None
    maximum: int | None


def _difference(placement: Placement, start: str, end: str) -> int | None:
    if placement.components[start] != placement.components[end]:
        return None
    return placement.positions[end] - placement.positions[start]


def evaluate_displacements(
    request: ReviewRequest, placements: tuple[Placement, ...]
) -> tuple[DisplacementResult, ...]:
    if not placements:
        raise ValueError('displacements require a common placement')
    results = []
    for start, end in request.pairs:
        value = _difference(placements[0], start, end)
        if value is not None and any(_difference(placement, start, end) != value for placement in placements[1:]):
            value = None
        results.append(DisplacementResult(start, end, value))
    return tuple(results)
