from collections.abc import Mapping

from registry.specimens import Specimen

from .corrections import apply_correction, apply_range_correction
from .origins import ReadingOrigin
from .revisions import RangeReading, RangeRevision, Reading, Revision
from .station import IntakeStation


def validate_readings(
    specimen: Specimen, positions: Mapping[str, int], origins: Mapping[str, ReadingOrigin]
) -> tuple[Reading, ...]:
    if not isinstance(positions, Mapping) or not isinstance(origins, Mapping):
        raise ValueError('readings and origins must be mappings')
    if not positions or positions.keys() != origins.keys():
        raise ValueError('provide a reading and an origin for every submitted mark')
    readings = []
    for mark, millimeters in positions.items():
        specimen.marks.require_mark(mark)
        readings.append(Reading(mark, millimeters, origins[mark]))
    return tuple(sorted(readings, key=lambda reading: reading.mark))


def record(
    station: IntakeStation,
    specimen: str,
    scale: str,
    positions: Mapping[str, int],
    origins: Mapping[str, ReadingOrigin],
    *,
    base_revision: str | None = None,
) -> Revision:
    owner = station.registry.load_specimen(specimen)
    owner.scales.require_scale(scale)
    readings = validate_readings(owner, positions, origins)
    if base_revision is not None:
        base = station.load_revision(specimen, scale, base_revision)
        readings = apply_correction(base, specimen, scale, readings)
    return station.append_revision(specimen, scale, readings, base_revision)


def _bounds(mark: str, value) -> tuple[int, int]:
    if type(value) is int:
        return value, value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lower, upper = value
        if type(lower) is int and type(upper) is int and lower <= upper:
            return lower, upper
    raise ValueError(f'range reading for {mark} must be an integer or an ordered integer pair')


def validate_range_readings(
    specimen: Specimen, positions: Mapping[str, object], origins: Mapping[str, ReadingOrigin]
) -> tuple[RangeReading, ...]:
    if not isinstance(positions, Mapping) or not isinstance(origins, Mapping):
        raise ValueError('readings and origins must be mappings')
    if not positions or positions.keys() != origins.keys():
        raise ValueError('provide a reading and an origin for every submitted mark')
    readings = []
    for mark, value in positions.items():
        specimen.marks.require_mark(mark)
        lower, upper = _bounds(mark, value)
        readings.append(RangeReading(mark, lower, upper, origins[mark]))
    return tuple(sorted(readings, key=lambda reading: reading.mark))


def record_ranges(
    station: IntakeStation,
    specimen: str,
    scale: str,
    positions: Mapping[str, object],
    origins: Mapping[str, ReadingOrigin],
    *,
    base_revision: str | None = None,
) -> RangeRevision:
    owner = station.registry.load_specimen(specimen)
    owner.scales.require_scale(scale)
    readings = validate_range_readings(owner, positions, origins)
    if base_revision is not None:
        base = station.load_any_revision(specimen, scale, base_revision)
        kept = tuple(
            row if isinstance(row, RangeReading)
            else RangeReading(row.mark, row.millimeters, row.millimeters, row.origin)
            for row in base.readings
        )
        readings = apply_range_correction(kept, readings)
    return station.append_range_revision(specimen, scale, readings, base_revision)
