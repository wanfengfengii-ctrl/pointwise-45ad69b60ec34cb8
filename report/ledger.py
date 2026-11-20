import json
import sqlite3


def initialize_report_ledger(connection: sqlite3.Connection) -> None:
    connection.execute('PRAGMA foreign_keys = ON')
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS signed_reports (
                report_id TEXT PRIMARY KEY NOT NULL,
                payload TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS success_receipts (
                report_id TEXT PRIMARY KEY NOT NULL REFERENCES signed_reports(report_id),
                receipt_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
        ''')


class ReportLedger:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def __enter__(self) -> 'ReportLedger':
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def commit_bundle(self, report: dict, receipt: dict) -> None:
        report_id = report['report_id']
        if receipt['report_id'] != report_id:
            raise ValueError('receipt belongs to another report')
        report_payload = json.dumps(report, sort_keys=True)
        receipt_payload = json.dumps(receipt, sort_keys=True)
        with self.connection:
            self.connection.execute(
                'INSERT INTO signed_reports (report_id, payload) VALUES (?, ?)',
                (report_id, report_payload),
            )
            self.connection.execute(
                'INSERT INTO success_receipts (report_id, receipt_id, payload) VALUES (?, ?, ?)',
                (report_id, receipt['receipt_id'], receipt_payload),
            )

    def load_bundle(self, report_id: str) -> tuple[dict, dict] | None:
        if type(report_id) is not str or not report_id:
            raise ValueError('invalid report number')
        row = self.connection.execute(
            '''SELECT report.payload, receipt.payload, receipt.receipt_id
               FROM signed_reports AS report
               LEFT JOIN success_receipts AS receipt ON receipt.report_id = report.report_id
               WHERE report.report_id = ?''',
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        if row[1] is None:
            raise sqlite3.DatabaseError('report is missing its success receipt')
        report = json.loads(row[0])
        receipt = json.loads(row[1])
        if (report['report_id'], receipt['report_id'], receipt['receipt_id']) != (report_id, report_id, row[2]):
            raise sqlite3.DatabaseError('stored report and receipt identities do not match ledger keys')
        return report, receipt

    def counts(self) -> tuple[int, int]:
        return self.connection.execute('''
            SELECT (SELECT COUNT(*) FROM signed_reports), (SELECT COUNT(*) FROM success_receipts)
        ''').fetchone()


def open_report_ledger(path) -> ReportLedger:
    connection = sqlite3.connect(path)
    try:
        initialize_report_ledger(connection)
    except BaseException:
        connection.close()
        raise
    return ReportLedger(connection)
