from collections.abc import Iterable
from dataclasses import dataclass

from issue.envelope import Packet


@dataclass(frozen=True, slots=True)
class ReportOrigin:
    packet_id: str
    revision_id: str
    mark: str
    sheet: str
    line: int

    def to_record(self) -> list[str]:
        return [self.packet_id, self.revision_id, self.mark, self.sheet, hex(self.line)]

    @classmethod
    def from_record(cls, row: list[str]) -> 'ReportOrigin':
        packet_id, revision_id, mark, sheet, line = row
        return cls(packet_id, revision_id, mark, sheet, int(line, 16))


def snapshot_origins(packets: Iterable[Packet]) -> tuple[ReportOrigin, ...]:
    return tuple(
        ReportOrigin(packet.packet_id, packet.revision_id, origin.mark, origin.sheet, origin.line)
        for packet in packets
        for origin in packet.origins
    )
