from collections.abc import Sequence
from dataclasses import dataclass

from issue.catalog import PacketCatalog
from issue.envelope import Packet


@dataclass(frozen=True, slots=True)
class Selection:
    specimen: str
    packets: tuple[Packet, ...]
    reference: Packet


def select_packets(catalog: PacketCatalog, packet_ids: Sequence[str], reference_packet_id: str) -> Selection:
    if not isinstance(packet_ids, Sequence) or isinstance(packet_ids, (str, bytes, bytearray)):
        raise ValueError('provide an ordered sequence of fixed packet numbers')
    identifiers = tuple(packet_ids)
    if not 1 <= len(identifiers) <= 3:
        raise ValueError('select one to three fixed packets')
    if any(type(identifier) is not str or not identifier for identifier in identifiers):
        raise ValueError('invalid fixed packet number')
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('duplicate fixed packet number')
    if type(reference_packet_id) is not str or reference_packet_id not in identifiers:
        raise ValueError('reference packet is not selected')
    packets = tuple(catalog.get(identifier) for identifier in identifiers)
    reference = packets[identifiers.index(reference_packet_id)]
    if any(packet.specimen != reference.specimen for packet in packets):
        raise ValueError('selected packets belong to different specimens')
    return Selection(reference.specimen, packets, reference)
