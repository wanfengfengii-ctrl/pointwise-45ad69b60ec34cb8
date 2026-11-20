from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScaleShape:
    anchor: str
    offsets: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.offsets) is not tuple or not self.offsets:
            raise ValueError('shape requires a nonempty tuple of mark offsets')
        seen = {}
        for row in self.offsets:
            if type(row) is not tuple or len(row) != 2:
                raise ValueError('invalid mark offset row')
            mark, offset = row
            if type(mark) is not str or not mark or mark.strip() != mark or '\x00' in mark:
                raise ValueError('invalid shape mark')
            if mark in seen or type(offset) is not int:
                raise ValueError('shape marks must be unique and offsets must be integers')
            seen[mark] = offset
        if type(self.anchor) is not str or seen.get(self.anchor) != 0:
            raise ValueError('shape anchor must be a measured mark at offset zero')

    def offset_of(self, mark: str) -> int:
        for name, offset in self.offsets:
            if name == mark:
                return offset
        raise LookupError(f'mark absent from shape: {mark}')


def build_shape(positions: Mapping[str, int]) -> ScaleShape:
    if not isinstance(positions, Mapping) or not positions:
        raise ValueError('shape requires measured marks')
    for mark, position in positions.items():
        if type(mark) is not str or type(position) is not int:
            raise ValueError('shape requires named integer readings')
    anchor = min(positions)
    origin = positions[anchor]
    offsets = tuple((mark, positions[mark] - origin) for mark in sorted(positions))
    return ScaleShape(anchor, offsets)
