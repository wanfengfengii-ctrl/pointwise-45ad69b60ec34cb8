import json
import sqlite3
from dataclasses import replace

import range_cases
from intake.origins import ReadingOrigin
from intake.readings import record_ranges
from intake.revisions import RangeReading, RangeRevision
from intake.station import freeze
from issue.catalog import open_packet_catalog
from issue.codec import decode_packet, encode_packet
from issue.publish import issue
from issue.shape import IntervalShape, ScaleShape
from registry.catalog import register
from report.readback import read
from review.decisions import review, review_ranges
from tests import WorkspaceCase, issue_frozen, record_for

SPECIMEN = range_cases.SPECIMEN


def ranges_for(station, scale, values, sheet, *, base_revision=None, specimen=SPECIMEN):
    origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(values, 1)}
    return record_ranges(station, specimen, scale, values, origins, base_revision=base_revision)


def issue_ranges(station, catalog, revision):
    number = freeze(station, revision.specimen, revision.scale, revision.revision_id)
    return issue(station, catalog, revision.specimen, revision.scale, number)


class RangeIntakeTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        register(self.source.registry, SPECIMEN, range_cases.SCALES, range_cases.MARKS)

    def range_count(self):
        return self.source.connection.execute('SELECT COUNT(*) FROM range_revisions').fetchone()[0]

    def test_record_ranges_revision_fields_and_freeze(self):
        revision = ranges_for(self.source, 'A', {'P': (0, 2), 'Q': 1}, 'sheet-1')
        self.assertIsInstance(revision, RangeRevision)
        self.assertEqual(
            (revision.specimen, revision.scale, revision.base_revision, revision.frozen),
            (SPECIMEN, 'A', None, False),
        )
        self.assertEqual(
            revision.readings,
            (
                RangeReading('P', 0, 2, ReadingOrigin('sheet-1', 1)),
                RangeReading('Q', 1, 1, ReadingOrigin('sheet-1', 2)),
            ),
        )
        self.assertEqual(freeze(self.source, SPECIMEN, 'A', revision.revision_id), revision.revision_id)
        self.assertEqual(freeze(self.source, SPECIMEN, 'A', revision.revision_id), revision.revision_id)
        self.source.close()
        reopened = self.station()
        loaded = reopened.load_range_revision(SPECIMEN, 'A', revision.revision_id)
        self.assertTrue(loaded.is_frozen())
        self.assertEqual(loaded.readings, revision.readings)
        self.assertEqual(loaded.base_revision, revision.base_revision)

    def test_record_ranges_rejects_invalid_values_without_appending(self):
        good = ReadingOrigin('sheet', 1)
        invalid = [
            ({'P': True}, {'P': good}),
            ({'P': 1.5}, {'P': good}),
            ({'P': '1'}, {'P': good}),
            ({'P': None}, {'P': good}),
            ({'P': (2, 1)}, {'P': good}),
            ({'P': (1, '2')}, {'P': good}),
            ({'P': (True, 1)}, {'P': good}),
            ({'P': (1, True)}, {'P': good}),
            ({'P': [1, 2, 3]}, {'P': good}),
            ({'P': (1,)}, {'P': good}),
            ({'P': {'lower': 1}}, {'P': good}),
            ({'P': 1}, {}),
            ({'P': 1}, {'P': None}),
            ({'P': 1}, {'P': ReadingOrigin(' ', 1)}),
            ({'P': 1}, {'P': ReadingOrigin('sheet', 0)}),
            ({'P': 1}, {'P': ReadingOrigin('sheet', True)}),
            ({'P': 1, 'Q': 2}, {'P': good}),
            ({}, {}),
        ]
        for positions, origins in invalid:
            with self.subTest(positions=positions, origins=origins), self.assertRaises(ValueError):
                record_ranges(self.source, SPECIMEN, 'A', positions, origins)
        with self.assertRaisesRegex(ValueError, 'unknown mark'):
            ranges_for(self.source, 'A', {'P': 1, 'Z': 2}, 'mixed-row')
        self.assertEqual(self.range_count(), 0)

    def test_record_ranges_unknown_specimen_scale_and_freeze_errors(self):
        with self.assertRaises(LookupError):
            ranges_for(self.source, 'A', {'P': 1}, 'sheet', specimen='missing')
        with self.assertRaisesRegex(ValueError, 'unknown scale'):
            ranges_for(self.source, 'Z', {'P': 1}, 'sheet')
        revision = ranges_for(self.source, 'A', {'P': 1}, 'sheet')
        with self.assertRaises(LookupError):
            freeze(self.source, SPECIMEN, 'A', 'missing')
        with self.assertRaisesRegex(ValueError, 'belongs'):
            freeze(self.source, SPECIMEN, 'B', revision.revision_id)
        with self.assertRaisesRegex(ValueError, 'belongs'):
            self.source.load_range_revision(SPECIMEN, 'B', revision.revision_id)
        with self.assertRaises(LookupError):
            self.source.load_range_revision(SPECIMEN, 'A', 'missing')

    def test_correction_replaces_only_submitted_marks_and_origins(self):
        base = ranges_for(self.source, 'A', {'P': (0, 1), 'Q': 0, 'R': 1}, 'base-sheet')
        correction = ranges_for(self.source, 'A', {'Q': (2, 3)}, 'fix-sheet', base_revision=base.revision_id)
        self.assertEqual(correction.base_revision, base.revision_id)
        self.assertEqual(
            {row.mark: (row.lower, row.upper) for row in correction.readings},
            {'P': (0, 1), 'Q': (2, 3), 'R': (1, 1)},
        )
        self.assertEqual(
            {row.mark: (row.origin.sheet, row.origin.line) for row in correction.readings},
            {'P': ('base-sheet', 1), 'Q': ('fix-sheet', 1), 'R': ('base-sheet', 3)},
        )
        self.assertEqual(self.source.load_range_revision(SPECIMEN, 'A', base.revision_id).readings, base.readings)

    def test_correction_on_exact_base_and_range_base(self):
        exact = record_for(self.source, SPECIMEN, 'B', {'Q': 0, 'R': 1}, 'exact-sheet')
        from_exact = ranges_for(self.source, 'B', {'R': (1, 2)}, 'fix-1', base_revision=exact.revision_id)
        self.assertEqual(
            {row.mark: (row.lower, row.upper) for row in from_exact.readings},
            {'Q': (0, 0), 'R': (1, 2)},
        )
        self.assertEqual(from_exact.readings[0].origin, ReadingOrigin('exact-sheet', 1))
        from_range = ranges_for(self.source, 'B', {'Q': (-1, 0)}, 'fix-2', base_revision=from_exact.revision_id)
        self.assertEqual(
            {row.mark: (row.lower, row.upper) for row in from_range.readings},
            {'Q': (-1, 0), 'R': (1, 2)},
        )

    def test_correction_rejects_wrong_owner_and_missing_base(self):
        base = ranges_for(self.source, 'A', {'P': 0}, 'sheet')
        with self.assertRaisesRegex(ValueError, 'belongs'):
            ranges_for(self.source, 'B', {'Q': 1}, 'fix', base_revision=base.revision_id)
        with self.assertRaises(LookupError):
            ranges_for(self.source, 'A', {'P': 1}, 'fix', base_revision='missing')
        self.assertEqual(self.range_count(), 1)


class RangePacketTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        self.issued = self.catalog()
        register(self.source.registry, SPECIMEN, range_cases.SCALES, range_cases.MARKS)

    def receiving(self):
        return self.enterContext(open_packet_catalog(self.root / 'receive.sqlite'))

    def test_issue_from_ranges_is_v2_with_anchor_relative_spans(self):
        revision = ranges_for(self.source, 'A', {'P': (0, 1), 'Q': 0, 'R': 1}, 'sheet-a')
        with self.assertRaisesRegex(ValueError, 'must be frozen'):
            issue(self.source, self.issued, SPECIMEN, 'A', revision.revision_id)
        packet = issue_ranges(self.source, self.issued, revision)
        self.assertEqual(packet.version, 2)
        self.assertIsInstance(packet.shape, IntervalShape)
        self.assertEqual(packet.shape.anchor, 'P')
        self.assertEqual(packet.shape.spans, (('P', 0, 1), ('Q', 0, 0), ('R', 1, 1)))
        self.assertEqual(
            [(row.mark, row.sheet, row.line) for row in packet.origins],
            [('P', 'sheet-a', 1), ('Q', 'sheet-a', 2), ('R', 'sheet-a', 3)],
        )
        exact = issue_frozen(self.source, self.issued, record_for(self.source, SPECIMEN, 'B', {'Q': 0}, 'sheet-b'))
        self.assertEqual(exact.version, 1)
        self.assertIsInstance(exact.shape, ScaleShape)

    def test_shift_invariant_spans(self):
        first = issue_ranges(self.source, self.issued, ranges_for(self.source, 'A', {'P': (0, 1), 'Q': 0, 'R': 1}, 's1'))
        shifted = issue_ranges(
            self.source, self.issued, ranges_for(self.source, 'A', {'P': (10, 11), 'Q': 10, 'R': 11}, 's2')
        )
        self.assertEqual(first.shape, shifted.shape)

    def test_v2_codec_round_trip_preserves_exact_integers_and_identity(self):
        huge = 1 << 16000
        revision = ranges_for(self.source, 'A', {'P': (-huge, 0), 'Q': (0, huge)}, 'sheet')
        packet = issue_ranges(self.source, self.issued, revision)
        text = encode_packet(packet)
        wire = json.loads(text)
        self.assertEqual(set(wire), {'version', 'packet_id', 'specimen', 'scale', 'revision_id', 'body'})
        self.assertEqual(wire['version'], 2)
        self.assertEqual(set(wire['body']), {'anchor', 'spans', 'origins'})
        self.assertEqual(
            wire['body']['spans'],
            [['P', '0x0', hex(huge)], ['Q', hex(huge), hex(2 * huge)]],
        )
        decoded = decode_packet(text)
        self.assertEqual(decoded, packet)
        received = self.receiving()
        received.save(decoded)
        received.save(decode_packet(encode_packet(packet)))
        self.assertEqual(received.get(packet.packet_id), packet)
        self.assertEqual(received.count(), 1)
        with self.assertRaisesRegex(ValueError, 'conflicting fixed packet'):
            received.save(replace(packet, revision_id='another-revision'))
        self.assertEqual(received.count(), 1)

    def test_v2_decode_rejects_invalid_packets(self):
        revision = ranges_for(self.source, 'A', {'P': (0, 1), 'Q': 0}, 'sheet')
        packet = issue_ranges(self.source, self.issued, revision)
        payload = json.loads(encode_packet(packet))
        bad = []
        swapped = json.loads(json.dumps(payload))
        swapped['body']['spans'][0] = ['P', '0x1', '0x0']
        bad.append(swapped)
        missing_origin = json.loads(json.dumps(payload))
        missing_origin['body']['origins'].pop()
        bad.append(missing_origin)
        bad_version = json.loads(json.dumps(payload))
        bad_version['version'] = 3
        bad.append(bad_version)
        bad_width = json.loads(json.dumps(payload))
        bad_width['body']['spans'][0] = ['P', '0x0']
        bad.append(bad_width)
        bad_hex = json.loads(json.dumps(payload))
        bad_hex['body']['spans'][0][1] = '1'
        bad.append(bad_hex)
        bad_anchor = json.loads(json.dumps(payload))
        bad_anchor['body']['anchor'] = 'Z'
        bad.append(bad_anchor)
        for index, candidate in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                decode_packet(json.dumps(candidate))
        with self.assertRaisesRegex(ValueError, 'duplicate packet field'):
            decode_packet('{"version":2,' + encode_packet(packet)[1:])
        self.assertEqual(self.issued.count(), 1)


class RangeReviewTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        self.issued = self.catalog()
        self.received = self.enterContext(open_packet_catalog(self.root / 'receive.sqlite'))
        self.reports = self.ledger()
        register(self.source.registry, SPECIMEN, range_cases.SCALES, range_cases.MARKS)

    def ranges_packet(self, scale, values, sheet, *, base_revision=None):
        revision = ranges_for(self.source, scale, values, sheet, base_revision=base_revision)
        packet = issue_ranges(self.source, self.issued, revision)
        self.received.save(decode_packet(encode_packet(packet)))
        return packet, revision

    def exact_packet(self, scale, values, sheet):
        revision = record_for(self.source, SPECIMEN, scale, values, sheet)
        packet = issue_frozen(self.source, self.issued, revision)
        self.received.save(decode_packet(encode_packet(packet)))
        return packet, revision

    def disconnect(self):
        self.source.close()
        self.issued.close()

    def use(self, packets, reference, pairs):
        return review_ranges(
            self.received,
            self.reports,
            [packet.packet_id for packet in packets],
            reference.packet_id,
            [tuple(pair) for pair in pairs],
        )

    @staticmethod
    def bounds(outcome):
        return [(row.start, row.end, row.minimum, row.maximum) for row in outcome.report.results]

    def test_coupled_coincidence_conflicts_even_for_empty_request(self):
        coupled, _ = self.ranges_packet('A', range_cases.COUPLED, 'PM-AC')
        coincident, _ = self.exact_packet('B', range_cases.COINCIDENT, 'PM-BC')
        self.disconnect()
        before = self.reports.counts()
        for pairs in (range_cases.COINCIDENCE_PAIRS, ()):
            with self.subTest(pairs=pairs):
                outcome = self.use([coupled, coincident], coupled, pairs)
                self.assertEqual(outcome.status, 'conflict')
                self.assertIsNone(outcome.report)
                self.assertIsNone(outcome.receipt)
                self.assertEqual(self.reports.counts(), before)

    def test_independent_coincidence_signs_point_result(self):
        independent, _ = self.ranges_packet('A', range_cases.INDEPENDENT, 'PM-AI')
        coincident, _ = self.exact_packet('B', range_cases.COINCIDENT, 'PM-BC')
        self.disconnect()
        outcome = self.use([independent, coincident], independent, range_cases.COINCIDENCE_PAIRS)
        self.assertEqual(outcome.status, 'signed')
        self.assertEqual(self.bounds(outcome), [('P', 'R', 0, 0)])
        self.assertEqual(outcome.receipt.report_id, outcome.report.report_id)
        self.assertEqual(self.reports.counts(), (1, 1))

    def test_triple_cycle_correction_and_reopen_readback(self):
        a, a_revision = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        b, _ = self.exact_packet('B', range_cases.TRIPLE_B, 'PM-B')
        c, _ = self.exact_packet('C', range_cases.TRIPLE_C, 'PM-C')
        self.disconnect()
        first = self.use([a, b, c], a, range_cases.TRIPLE_PAIRS)
        self.assertEqual(first.status, 'signed')
        self.assertEqual(
            self.bounds(first),
            [
                ('Q', 'R', -2, -2),
                ('R', 'Q', 2, 2),
                ('P', 'R', -1, 1),
                ('R', 'R', 0, 0),
                ('Q', 'R', -2, -2),
            ],
        )
        self.assertEqual(
            [binding.packet_id for binding in first.report.bindings],
            [packet.packet_id for packet in (a, b, c)],
        )
        self.assertEqual(
            {(row.packet_id, row.mark, row.sheet, row.line) for row in first.report.origins},
            {
                (a.packet_id, 'P', 'PM-A1', 1), (a.packet_id, 'Q', 'PM-A1', 2),
                (b.packet_id, 'Q', 'PM-B', 1), (b.packet_id, 'R', 'PM-B', 2),
                (c.packet_id, 'P', 'PM-C', 1), (c.packet_id, 'R', 'PM-C', 2),
            },
        )
        # Correct A from its first revision, submitting only Q with a new origin.
        self.source = self.station()
        self.issued = self.catalog()
        corrected, corrected_revision = self.ranges_packet(
            'A', range_cases.CORRECTION_A, 'PM-A2', base_revision=a_revision.revision_id
        )
        self.assertEqual(corrected_revision.base_revision, a_revision.revision_id)
        self.assertEqual(
            [(row.mark, row.sheet, row.line) for row in corrected.origins],
            [('P', 'PM-A1', 1), ('Q', 'PM-A2', 1)],
        )
        self.disconnect()
        second = self.use([corrected, b, c], corrected, range_cases.TRIPLE_PAIRS)
        self.assertEqual(second.status, 'signed')
        self.assertEqual(
            self.bounds(second),
            [
                ('Q', 'R', -2, -2),
                ('R', 'Q', 2, 2),
                ('P', 'R', 1, 1),
                ('R', 'R', 0, 0),
                ('Q', 'R', -2, -2),
            ],
        )
        self.assertEqual(self.reports.counts(), (2, 2))
        # Close the receiving catalog and the ledger; reopen only the ledger.
        self.received.close()
        self.reports.close()
        self.reports = self.ledger()
        self.assertEqual(read(self.reports, first.report.report_id), (first.report, first.receipt))
        self.assertEqual(read(self.reports, second.report.report_id), (second.report, second.receipt))
        self.assertIsNone(read(self.reports, 'unknown-report'))
        self.assertEqual(self.reports.counts(), (2, 2))

    def test_isolated_component_unbounded_self_zero_and_bounded_together(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        b, _ = self.exact_packet('B', range_cases.TRIPLE_B, 'PM-B')
        d, _ = self.exact_packet('D', range_cases.ISOLATED_D, 'PM-D')
        self.disconnect()
        outcome = self.use([a, b, d], a, range_cases.ISOLATED_PAIRS)
        self.assertEqual(outcome.status, 'signed')
        self.assertEqual(
            self.bounds(outcome),
            [('Q', 'S', None, None), ('S', 'S', 0, 0), ('P', 'Q', 1, 3)],
        )

    def test_empty_request_signs_zero_item_report(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        self.disconnect()
        outcome = self.use([a], a, [])
        self.assertEqual(outcome.status, 'signed')
        self.assertEqual(outcome.report.results, ())
        self.assertEqual(outcome.receipt.report_id, outcome.report.report_id)
        self.assertEqual(self.reports.counts(), (1, 1))

    def test_single_range_packet_bounds_and_duplicates(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        self.disconnect()
        outcome = self.use([a], a, [('P', 'Q'), ('Q', 'P'), ('P', 'Q')])
        self.assertEqual(
            self.bounds(outcome),
            [('P', 'Q', 1, 3), ('Q', 'P', -3, -1), ('P', 'Q', 1, 3)],
        )

    def test_review_rejects_range_packets_but_still_serves_exact_packets(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        b, _ = self.exact_packet('B', range_cases.TRIPLE_B, 'PM-B')
        self.disconnect()
        with self.assertRaises(ValueError):
            review(self.received, self.reports, [a.packet_id], a.packet_id, [])
        with self.assertRaises(ValueError):
            review(self.received, self.reports, [b.packet_id, a.packet_id], b.packet_id, [('Q', 'R')])
        exact = review(self.received, self.reports, [b.packet_id], b.packet_id, [('Q', 'R')])
        self.assertEqual(exact.status, 'signed')
        self.assertEqual(exact.report.results[0].millimeters, 2)
        self.assertEqual(self.reports.counts(), (1, 1))

    def test_selection_and_request_errors_leave_ledger_unchanged(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        b, _ = self.exact_packet('B', range_cases.TRIPLE_B, 'PM-B')
        register(self.source.registry, 'Y', ['A'], ['P'])
        foreign = issue_frozen(self.source, self.issued, record_for(self.source, 'Y', 'A', {'P': 0}, 'y'))
        self.received.save(decode_packet(encode_packet(foreign)))
        self.disconnect()
        catalog, ledger = self.received, self.reports
        with self.assertRaises(LookupError):
            review_ranges(catalog, ledger, [a.packet_id, 'missing'], a.packet_id, [])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id, b.packet_id], 'missing', [])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id, a.packet_id], a.packet_id, [])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id, b.packet_id, a.packet_id, b.packet_id], a.packet_id, [])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id, foreign.packet_id], a.packet_id, [])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id], a.packet_id, [('P', 'Z')])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id], a.packet_id, ['PQ'])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id], a.packet_id, [('P',)])
        with self.assertRaises(ValueError):
            review_ranges(catalog, ledger, [a.packet_id], a.packet_id, 'PQ')
        self.assertEqual(ledger.counts(), (0, 0))

    def test_commit_failure_rolls_back_both_rows_and_allows_retry(self):
        a, _ = self.ranges_packet('A', range_cases.TRIPLE_A, 'PM-A1')
        b, _ = self.exact_packet('B', range_cases.TRIPLE_B, 'PM-B')
        c, _ = self.exact_packet('C', range_cases.TRIPLE_C, 'PM-C')
        self.disconnect()
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
            self.use([a, b, c], a, range_cases.TRIPLE_PAIRS)
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.reports.counts(), (0, 0))
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM deferred_check').fetchone(), (0,))
        self.reports.close()
        self.reports = self.ledger()
        retry = self.use([a, b, c], a, range_cases.TRIPLE_PAIRS)
        self.assertEqual(retry.status, 'signed')
        self.assertEqual(
            [(row.minimum, row.maximum) for row in retry.report.results],
            [(-2, -2), (2, 2), (-1, 1), (0, 0), (-2, -2)],
        )
        self.assertEqual(self.reports.counts(), (1, 1))
