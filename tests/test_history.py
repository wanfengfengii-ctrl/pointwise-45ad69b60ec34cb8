import sqlite3

from registry.catalog import register
from report.ledger import initialize_report_ledger
from report.readback import read
from review.decisions import review
from tests import WorkspaceCase, issue_frozen, record_for


class HistoryTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        self.packets = self.catalog()
        self.reports = self.ledger()
        register(self.source.registry, 'X', ['A'], ['P', 'Q'])
        self.original = record_for(self.source, 'X', 'A', {'P': 0, 'Q': 1}, 'initial')
        self.original_packet = issue_frozen(self.source, self.packets, self.original)

    def sign(self, packet):
        return review(self.packets, self.reports, [packet.packet_id], packet.packet_id, [('P', 'Q')])

    def corrected_packet(self, values, sheet):
        correction = record_for(self.source, 'X', 'A', values, sheet, base_revision=self.original.revision_id)
        self.assertEqual(correction.base_revision, self.original.revision_id)
        return issue_frozen(self.source, self.packets, correction)

    def assert_history(self, ledger, decision, packet, value, expected_origins):
        report, receipt = read(ledger, decision.report.report_id)
        self.assertEqual((report, receipt), (decision.report, decision.receipt))
        self.assertEqual(receipt.report_id, report.report_id)
        self.assertEqual(report.reference_packet_id, packet.packet_id)
        self.assertEqual(
            [(binding.packet_id, binding.scale, binding.revision_id) for binding in report.bindings],
            [(packet.packet_id, 'A', packet.revision_id)],
        )
        self.assertEqual([(row.start, row.end, row.millimeters) for row in report.results], [('P', 'Q', value)])
        self.assertEqual(
            [(row.mark, row.sheet, row.line, row.packet_id, row.revision_id) for row in report.origins],
            [(mark, sheet, line, packet.packet_id, packet.revision_id) for mark, sheet, line in expected_origins],
        )

    def test_explicit_base_keeps_unedited_reading_and_origin(self):
        self.source.close()
        old = self.sign(self.original_packet)
        self.assertEqual(old.status, 'signed')
        self.assertEqual(old.report.results[0].millimeters, 1)
        self.source = self.station()
        newer = record_for(self.source, 'X', 'A', {'Q': 3}, 'newer', base_revision=self.original.revision_id)
        self.assertEqual({row.mark: row.millimeters for row in newer.readings}, {'P': 0, 'Q': 3})
        revised = self.corrected_packet({'P': -1}, 'explicit-base')
        self.source.close()
        result = self.sign(revised)
        self.assertEqual(result.status, 'signed')
        self.assert_history(self.reports, result, revised, 2, [('P', 'explicit-base', 1), ('Q', 'initial', 2)])
        self.assertEqual(self.reports.counts(), (2, 2))

    def test_original_binding_and_receipt_after_reopen(self):
        self.source.close()
        old = self.sign(self.original_packet)
        self.assertEqual(old.status, 'signed')
        self.source = self.station()
        revised = self.corrected_packet({'Q': 3}, 'correction')
        self.source.close()
        new = self.sign(revised)
        self.assertEqual(new.status, 'signed')
        self.assertNotEqual(new.receipt.receipt_id, old.receipt.receipt_id)
        self.packets.close()
        self.reports.close()
        reopened = self.ledger()
        initialize_report_ledger(reopened.connection)
        self.assert_history(reopened, old, self.original_packet, 1, [('P', 'initial', 1), ('Q', 'initial', 2)])
        self.assert_history(reopened, new, revised, 3, [('P', 'initial', 1), ('Q', 'correction', 1)])
        self.assertEqual(reopened.counts(), (2, 2))

    def test_receipt_failure_rolls_back_tentative_report(self):
        revised = self.corrected_packet({'Q': 3}, 'correction')
        self.source.close()
        old = self.sign(self.original_packet)
        self.assertEqual(old.status, 'signed')
        self.reports.connection.execute('''
            CREATE TEMP TRIGGER fail_receipt BEFORE INSERT ON success_receipts
            WHEN EXISTS (SELECT 1 FROM signed_reports WHERE report_id = NEW.report_id)
            BEGIN SELECT RAISE(ABORT, 'receipt write rejected'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write rejected'):
            self.sign(revised)
        self.assertEqual(self.reports.counts(), (1, 1))
        self.reports.close()
        reopened = self.ledger()
        self.assertEqual(reopened.counts(), (1, 1))
        self.assert_history(reopened, old, self.original_packet, 1, [('P', 'initial', 1), ('Q', 'initial', 2)])

    def test_commit_failure_rolls_back_both_rows_and_allows_retry(self):
        revised = self.corrected_packet({'Q': 3}, 'correction')
        self.source.close()
        old = self.sign(self.original_packet)
        self.assertEqual(old.status, 'signed')
        connection = self.reports.connection
        connection.execute('CREATE TEMP TABLE allowed_keys (value INTEGER PRIMARY KEY)')
        connection.execute('''
            CREATE TEMP TABLE deferred_check (
                value INTEGER REFERENCES allowed_keys(value) DEFERRABLE INITIALLY DEFERRED
            )
        ''')
        connection.execute('''
            CREATE TEMP TRIGGER fail_commit AFTER INSERT ON success_receipts
            BEGIN INSERT INTO deferred_check VALUES (1); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            self.sign(revised)
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.reports.counts(), (1, 1))
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM deferred_check').fetchone(), (0,))
        self.reports.close()
        self.reports = self.ledger()
        self.assertEqual(self.reports.counts(), (1, 1))
        self.assert_history(self.reports, old, self.original_packet, 1, [('P', 'initial', 1), ('Q', 'initial', 2)])
        retry = self.sign(revised)
        self.assertEqual(retry.status, 'signed')
        self.assert_history(self.reports, retry, revised, 3, [('P', 'initial', 1), ('Q', 'correction', 1)])
        self.assertEqual(self.reports.counts(), (2, 2))

    def test_missing_report_returns_none_without_writes(self):
        old = self.sign(self.original_packet)
        self.assertEqual(old.status, 'signed')
        self.assertIsNone(read(self.reports, 'unknown-report'))
        self.assertEqual(self.reports.counts(), (1, 1))
