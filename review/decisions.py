from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from issue.catalog import PacketCatalog
from report.ledger import ReportLedger
from report.publish import SignedReport, publish_report
from report.receipts import SuccessReceipt

from .alignment import common_placements
from .displacements import evaluate_displacements
from .requests import bind_request
from .selection import select_packets


@dataclass(frozen=True, slots=True)
class Assessment:
    status: Literal['signed', 'conflict']
    report: SignedReport | None = None
    receipt: SuccessReceipt | None = None


def review(
    catalog: PacketCatalog,
    ledger: ReportLedger,
    packet_ids: Sequence[str],
    reference_packet_id: str,
    pairs: Sequence[Sequence[str]],
) -> Assessment:
    selection = select_packets(catalog, packet_ids, reference_packet_id)
    request = bind_request(selection, pairs)
    placements = common_placements(selection)
    if not placements:
        return Assessment('conflict')
    results = evaluate_displacements(request, placements)
    report, receipt = publish_report(ledger, request, results)
    return Assessment('signed', report, receipt)
