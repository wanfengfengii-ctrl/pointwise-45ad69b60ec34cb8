from .ledger import ReportLedger
from .publish import SignedRangeReport, SignedReport
from .receipts import SuccessReceipt


def read(ledger: ReportLedger, report_id: str):
    bundle = ledger.load_bundle(report_id)
    if bundle is None:
        return None
    report, receipt = bundle
    if report.get('kind') == 'ranges':
        return SignedRangeReport.from_record(report), SuccessReceipt.from_record(receipt)
    return SignedReport.from_record(report), SuccessReceipt.from_record(receipt)
