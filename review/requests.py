from collections.abc import Sequence
from dataclasses import dataclass

from .selection import Selection


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    selection: Selection
    pairs: tuple[tuple[str, str], ...]


def bind_request(selection: Selection, pairs: Sequence[Sequence[str]]) -> ReviewRequest:
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes, bytearray)):
        raise ValueError('provide an ordered sequence of mark pairs')
    marks = {mark for packet in selection.packets for mark, _ in packet.shape.offsets}
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
