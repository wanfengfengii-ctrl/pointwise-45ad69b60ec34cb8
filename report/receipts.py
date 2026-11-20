from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SuccessReceipt:
    receipt_id: str
    report_id: str

    def to_record(self) -> dict[str, str]:
        return {'receipt_id': self.receipt_id, 'report_id': self.report_id}

    @classmethod
    def from_record(cls, row: dict[str, str]) -> 'SuccessReceipt':
        return cls(row['receipt_id'], row['report_id'])


def make_success_receipt(report_id: str) -> SuccessReceipt:
    return SuccessReceipt(uuid4().hex, report_id)
