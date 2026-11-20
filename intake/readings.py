from collections.abc import Mapping

from registry.specimens import Specimen

from .corrections import apply_correction
from .origins import ReadingOrigin
from .revisions import Reading, Revision
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
