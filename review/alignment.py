from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType

from .selection import Selection


@dataclass(frozen=True, slots=True)
class Placement:
    positions: Mapping[str, int]
    components: Mapping[str, str]


def _place(selection: Selection, directions: dict[str, int]) -> Placement | None:
    edges: dict[str, list[tuple[str, int]]] = {}
    for packet in selection.packets:
        anchor = packet.shape.anchor
        direction = directions[packet.packet_id]
        for mark, offset in packet.shape.offsets:
            step = direction * offset
            edges.setdefault(anchor, []).append((mark, step))
            edges.setdefault(mark, []).append((anchor, -step))

    positions: dict[str, int] = {}
    components: dict[str, str] = {}
    # One arbitrary origin per connected part suffices. Begin with the reference origin.
    roots = dict.fromkeys((selection.reference.shape.anchor, *sorted(edges)))
    for root in roots:
        if root in positions:
            continue
        positions[root] = 0
        components[root] = root
        pending = deque([root])
        while pending:
            start = pending.popleft()
            for end, step in edges[start]:
                expected = positions[start] + step
                if end in positions:
                    if positions[end] != expected:
                        return None
                else:
                    positions[end] = expected
                    components[end] = root
                    pending.append(end)
    return Placement(MappingProxyType(positions), MappingProxyType(components))


def common_placements(selection: Selection) -> tuple[Placement, ...]:
    reference = selection.reference.packet_id
    reversible = [packet.packet_id for packet in selection.packets if packet.packet_id != reference]
    placements = []
    for signs in product((1, -1), repeat=len(reversible)):
        directions = dict(zip(reversible, signs))
        directions[reference] = 1
        placement = _place(selection, directions)
        if placement is not None:
            placements.append(placement)
    return tuple(placements)
