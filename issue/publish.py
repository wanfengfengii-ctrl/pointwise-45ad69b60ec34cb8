from intake.station import IntakeStation

from .catalog import PacketCatalog
from .envelope import Packet, PacketOrigin, make_packet
from .shape import build_shape


def issue(
    station: IntakeStation, catalog: PacketCatalog, specimen: str, scale: str, revision_id: str
) -> Packet:
    revision = station.load_revision(specimen, scale, revision_id)
    if not revision.is_frozen():
        raise ValueError('revision must be frozen before issue')
    shape = build_shape({row.mark: row.millimeters for row in revision.readings})
    origins = tuple(PacketOrigin(row.mark, row.origin.sheet, row.origin.line) for row in revision.readings)
    packet = make_packet(revision.specimen, revision.scale, revision.revision_id, shape, origins)
    catalog.save(packet)
    return packet
