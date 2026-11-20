from dataclasses import dataclass
from uuid import uuid4

from .shape import ScaleShape


@dataclass(frozen=True, slots=True)
class PacketOrigin:
    mark: str
    sheet: str
    line: int


@dataclass(frozen=True, slots=True)
class Packet:
    packet_id: str
    specimen: str
    scale: str
    revision_id: str
    shape: ScaleShape
    origins: tuple[PacketOrigin, ...]
    version: int = 1


def validate_packet(packet: Packet) -> Packet:
    if not isinstance(packet, Packet) or type(packet.version) is not int or packet.version != 1:
        raise ValueError('unsupported fixed packet version')
    for field in (packet.packet_id, packet.specimen, packet.scale, packet.revision_id):
        if type(field) is not str or not field or field.strip() != field or '\x00' in field:
            raise ValueError('invalid fixed packet identity')
    if not isinstance(packet.shape, ScaleShape) or type(packet.origins) is not tuple:
        raise ValueError('fixed packet needs a shape and origin rows')
    marks = {mark for mark, _ in packet.shape.offsets}
    seen = set()
    for origin in packet.origins:
        if not isinstance(origin, PacketOrigin):
            raise ValueError('invalid packet origin row')
        if type(origin.mark) is not str or origin.mark not in marks or origin.mark in seen:
            raise ValueError('fixed packet needs exactly one origin for each measured mark')
        if type(origin.sheet) is not str or not origin.sheet.strip() or '\x00' in origin.sheet:
            raise ValueError('invalid packet origin sheet')
        if type(origin.line) is not int or origin.line < 1:
            raise ValueError('invalid packet origin line')
        seen.add(origin.mark)
    if seen != marks:
        raise ValueError('fixed packet origin rows are incomplete')
    return packet


def make_packet(
    specimen: str, scale: str, revision_id: str, shape: ScaleShape, origins, *, packet_id: str | None = None
) -> Packet:
    identifier = uuid4().hex if packet_id is None else packet_id
    try:
        origin_rows = tuple(origins)
    except TypeError as exc:
        raise ValueError('fixed packet needs a sequence of origin rows') from exc
    return validate_packet(Packet(identifier, specimen, scale, revision_id, shape, origin_rows))
