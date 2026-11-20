from dataclasses import dataclass
from uuid import uuid4

from review.displacements import DisplacementResult, RangeResult
from review.requests import ReviewRequest

from .ledger import ReportLedger
from .origins import ReportOrigin, snapshot_origins
from .receipts import SuccessReceipt, make_success_receipt


@dataclass(frozen=True, slots=True)
class PacketBinding:
    packet_id: str
    scale: str
    revision_id: str


@dataclass(frozen=True, slots=True)
class SignedReport:
    report_id: str
    specimen: str
    reference_packet_id: str
    bindings: tuple[PacketBinding, ...]
    results: tuple[DisplacementResult, ...]
    origins: tuple[ReportOrigin, ...]

    def to_record(self) -> dict:
        return {
            'report_id': self.report_id,
            'specimen': self.specimen,
            'reference_packet_id': self.reference_packet_id,
            'bindings': [[row.packet_id, row.scale, row.revision_id] for row in self.bindings],
            'results': [
                [row.start, row.end, None if row.millimeters is None else hex(row.millimeters)]
                for row in self.results
            ],
            'origins': [row.to_record() for row in self.origins],
        }

    @classmethod
    def from_record(cls, row: dict) -> 'SignedReport':
        bindings = tuple(PacketBinding(*binding) for binding in row['bindings'])
        results = tuple(
            DisplacementResult(start, end, None if value is None else int(value, 16))
            for start, end, value in row['results']
        )
        origins = tuple(ReportOrigin.from_record(origin) for origin in row['origins'])
        return cls(row['report_id'], row['specimen'], row['reference_packet_id'], bindings, results, origins)


def publish_report(
    ledger: ReportLedger, request: ReviewRequest, results: tuple[DisplacementResult, ...]
) -> tuple[SignedReport, SuccessReceipt]:
    rows = tuple(results)
    if tuple((row.start, row.end) for row in rows) != request.pairs:
        raise ValueError('report results do not match the ordered request')
    selection = request.selection
    packets = selection.packets
    report = SignedReport(
        uuid4().hex,
        selection.specimen,
        selection.reference.packet_id,
        tuple(PacketBinding(packet.packet_id, packet.scale, packet.revision_id) for packet in packets),
        rows,
        snapshot_origins(packets),
    )
    receipt = make_success_receipt(report.report_id)
    ledger.commit_bundle(report.to_record(), receipt.to_record())
    return report, receipt


@dataclass(frozen=True, slots=True)
class SignedRangeReport:
    report_id: str
    specimen: str
    reference_packet_id: str
    bindings: tuple[PacketBinding, ...]
    results: tuple[RangeResult, ...]
    origins: tuple[ReportOrigin, ...]

    def to_record(self) -> dict:
        return {
            'kind': 'ranges',
            'report_id': self.report_id,
            'specimen': self.specimen,
            'reference_packet_id': self.reference_packet_id,
            'bindings': [[row.packet_id, row.scale, row.revision_id] for row in self.bindings],
            'results': [
                [
                    row.start,
                    row.end,
                    None if row.minimum is None else hex(row.minimum),
                    None if row.maximum is None else hex(row.maximum),
                ]
                for row in self.results
            ],
            'origins': [row.to_record() for row in self.origins],
        }

    @classmethod
    def from_record(cls, row: dict) -> 'SignedRangeReport':
        bindings = tuple(PacketBinding(*binding) for binding in row['bindings'])
        results = tuple(
            RangeResult(
                start,
                end,
                None if minimum is None else int(minimum, 16),
                None if maximum is None else int(maximum, 16),
            )
            for start, end, minimum, maximum in row['results']
        )
        origins = tuple(ReportOrigin.from_record(origin) for origin in row['origins'])
        return cls(row['report_id'], row['specimen'], row['reference_packet_id'], bindings, results, origins)


def publish_range_report(
    ledger: ReportLedger, request: ReviewRequest, results: tuple[RangeResult, ...]
) -> tuple[SignedRangeReport, SuccessReceipt]:
    rows = tuple(results)
    if tuple((row.start, row.end) for row in rows) != request.pairs:
        raise ValueError('report results do not match the ordered request')
    selection = request.selection
    packets = selection.packets
    report = SignedRangeReport(
        uuid4().hex,
        selection.specimen,
        selection.reference.packet_id,
        tuple(PacketBinding(packet.packet_id, packet.scale, packet.revision_id) for packet in packets),
        rows,
        snapshot_origins(packets),
    )
    receipt = make_success_receipt(report.report_id)
    ledger.commit_bundle(report.to_record(), receipt.to_record())
    return report, receipt
