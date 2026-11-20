from dataclasses import dataclass

from .origins import ReadingOrigin, validate_origin


@dataclass(frozen=True, slots=True)
class Reading:
    mark: str
    millimeters: int
    origin: ReadingOrigin

    def __post_init__(self) -> None:
        if type(self.millimeters) is not int:
            raise ValueError(f'reading for {self.mark} must be an integer in millimeters')
        validate_origin(self.origin)


@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: str
    specimen: str
    scale: str
    base_revision: str | None
    readings: tuple[Reading, ...]
    frozen: bool

    def belongs_to(self, specimen: str, scale: str) -> bool:
        return self.specimen == specimen and self.scale == scale

    def is_frozen(self) -> bool:
        return self.frozen
