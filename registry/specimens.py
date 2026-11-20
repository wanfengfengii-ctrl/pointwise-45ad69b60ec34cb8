from dataclasses import dataclass

from .marks import MarkRoster
from .scales import ScaleRoster


def validate_specimen_number(number: str) -> str:
    if type(number) is not str or not number or number.strip() != number or '\x00' in number:
        raise ValueError('invalid specimen number')
    return number


@dataclass(frozen=True, slots=True)
class Specimen:
    number: str
    scales: ScaleRoster
    marks: MarkRoster

    def same_rosters(self, other: 'Specimen') -> bool:
        return self.scales == other.scales and self.marks == other.marks
