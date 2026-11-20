from collections.abc import Sequence
from dataclasses import dataclass

from issue.shape import IntervalShape, ScaleShape

from .selection import Selection


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    selection: Selection
    pairs: tuple[tuple[str, str], ...]


def packet_marks(packet) -> set[str]:
    shape = packet.shape
    if isinstance(shape, ScaleShape):
        return {mark for mark, _ in shape.offsets}
    if isinstance(shape, IntervalShape):
        return {mark for mark, _, _ in shape.spans}
    raise ValueError('unsupported fixed packet shape')


def bind_request(selection: Selection, pairs: Sequence[Sequence[str]]) -> ReviewRequest:
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes, bytearray)):
        raise ValueError('provide an ordered sequence of mark pairs')
    marks = {mark for packet in selection.packets for mark in packet_marks(packet)}
    bound = []
    for pair in pairs:
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes, bytearray)) or len(pair) != 2:
            raise ValueError('each request item must have two marks')
        start, end = pair
        for mark in (start, end):
            if type(mark) is not str or mark not in marks:
                raise ValueError(f'unknown request mark: {mark!r}')
        bound.append((start, end))
    return ReviewRequest(selection, tuple(bound))
