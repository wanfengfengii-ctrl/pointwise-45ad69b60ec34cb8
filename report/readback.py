from .ledger import ReportLedger
from .publish import SignedReport
from .receipts import SuccessReceipt


def read(ledger: ReportLedger, report_id: str) -> tuple[SignedReport, SuccessReceipt] | None:
    bundle = ledger.load_bundle(report_id)
    if bundle is None:
        return None
    report, receipt = bundle
    return SignedReport.from_record(report), SuccessReceipt.from_record(receipt)
