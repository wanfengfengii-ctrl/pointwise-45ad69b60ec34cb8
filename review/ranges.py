"""区间件共同摆放：整尺择向、单整数平移和同名点重合的差分约束求解。"""
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType

from issue.shape import IntervalShape, ScaleShape

from .displacements import RangeResult
from .selection import Selection


def piece_spans(packet) -> dict[str, tuple[int, int]]:
    shape = packet.shape
    if isinstance(shape, ScaleShape):
        return {mark: (offset, offset) for mark, offset in shape.offsets}
    if isinstance(shape, IntervalShape):
        return {mark: (lower, upper) for mark, lower, upper in shape.spans}
    raise ValueError('unsupported fixed packet shape')


def _mark_components(packets) -> dict[str, int]:
    parent = {}

    def find(mark: str) -> str:
        parent.setdefault(mark, mark)
        root = mark
        while parent[root] != root:
            root = parent[root]
        while parent[mark] != root:
            parent[mark], mark = root, parent[mark]
        return root

    for packet in packets:
        marks = sorted(piece_spans(packet))
        for mark in marks[1:]:
            first, second = find(marks[0]), find(mark)
            if first != second:
                parent[second] = first
    roots = {}
    components = {}
    for packet in packets:
        for mark in piece_spans(packet):
            root = find(mark)
            if root not in roots:
                roots[root] = len(roots)
            components[mark] = roots[root]
    return components


def _constraint_edges(selection: Selection, directions: dict[str, int]) -> list[tuple]:
    edges = []
    for packet in selection.packets:
        piece = ('piece', packet.packet_id)
        direction = directions[packet.packet_id]
        for mark, (lower, upper) in piece_spans(packet).items():
            low = min(direction * lower, direction * upper)
            high = max(direction * lower, direction * upper)
            node = ('mark', mark)
            # position(mark) - shift(piece) <= high
            edges.append((piece, node, high))
            # shift(piece) - position(mark) <= -low
            edges.append((node, piece, -low))
    return edges


def _shortest_paths(nodes: list, edges: list[tuple]):
    index = {node: number for number, node in enumerate(nodes)}
    size = len(nodes)
    dist = [[0 if row == col else None for col in range(size)] for row in range(size)]
    for start, end, weight in edges:
        row, col = index[start], index[end]
        if dist[row][col] is None or weight < dist[row][col]:
            dist[row][col] = weight
    for pivot in range(size):
        for row in range(size):
            leg_in = dist[row][pivot]
            if leg_in is None:
                continue
            for col in range(size):
                leg_out = dist[pivot][col]
                if leg_out is None:
                    continue
                candidate = leg_in + leg_out
                if dist[row][col] is None or candidate < dist[row][col]:
                    dist[row][col] = candidate
    if any(dist[number][number] < 0 for number in range(size)):
        return None
    return index, dist


@dataclass(frozen=True, slots=True)
class RangeAlignment:
    components: Mapping[str, int]
    solutions: tuple  # one (index, dist) shortest-path table per feasible direction assignment


def align_ranges(selection: Selection) -> RangeAlignment:
    nodes = [('piece', packet.packet_id) for packet in selection.packets]
    marks = set()
    for packet in selection.packets:
        marks.update(piece_spans(packet))
    nodes.extend(('mark', mark) for mark in sorted(marks))
    reference = selection.reference.packet_id
    reversible = [packet.packet_id for packet in selection.packets if packet.packet_id != reference]
    solutions = []
    for signs in product((1, -1), repeat=len(reversible)):
        directions = dict(zip(reversible, signs))
        directions[reference] = 1
        solved = _shortest_paths(nodes, _constraint_edges(selection, directions))
        if solved is not None:
            solutions.append(solved)
    components = MappingProxyType(_mark_components(selection.packets))
    return RangeAlignment(components, tuple(solutions))


def evaluate_ranges(pairs: tuple[tuple[str, str], ...], alignment: RangeAlignment) -> tuple[RangeResult, ...]:
    if not alignment.solutions:
        raise ValueError('range displacements require a common placement')
    results = []
    for start, end in pairs:
        if start == end:
            results.append(RangeResult(start, end, 0, 0))
            continue
        if alignment.components[start] != alignment.components[end]:
            results.append(RangeResult(start, end, None, None))
            continue
        low = high = None
        for index, dist in alignment.solutions:
            row = index[('mark', start)]
            col = index[('mark', end)]
            candidate_high = dist[row][col]
            candidate_low = -dist[col][row]
            low = candidate_low if low is None else min(low, candidate_low)
            high = candidate_high if high is None else max(high, candidate_high)
        results.append(RangeResult(start, end, low, high))
    return tuple(results)
