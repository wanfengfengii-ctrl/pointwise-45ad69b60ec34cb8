from .revisions import RangeReading, Reading, Revision


def apply_correction(
    base: Revision, specimen: str, scale: str, updates: tuple[Reading, ...]
) -> tuple[Reading, ...]:
    if not base.belongs_to(specimen, scale):
        raise ValueError('correction base belongs to another specimen or scale')
    merged = {reading.mark: reading for reading in base.readings}
    merged.update((reading.mark, reading) for reading in updates)
    return tuple(merged[mark] for mark in sorted(merged))


def apply_range_correction(
    base_readings: tuple[RangeReading, ...], updates: tuple[RangeReading, ...]
) -> tuple[RangeReading, ...]:
    merged = {reading.mark: reading for reading in base_readings}
    merged.update((reading.mark, reading) for reading in updates)
    return tuple(merged[mark] for mark in sorted(merged))
