from itertools import combinations

from issue.envelope import PacketOrigin, make_packet
from issue.shape import ScaleShape
from registry.catalog import register
from report.readback import read
from review.decisions import review
from tests import WorkspaceCase, issue_frozen, record_for


def fixed_packet(specimen, scale, offsets):
    # Offsets are given directly in the fixed-piece coordinate system.
    anchor = next(iter(offsets))
    shape = ScaleShape(anchor, tuple(offsets.items()))
    origins = tuple(PacketOrigin(mark, f'fixture-{scale}', index) for index, mark in enumerate(offsets, 1))
    return make_packet(specimen, scale, f'revision-{scale}', shape, origins, packet_id=f'{specimen}-{scale}')


class HandoffTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.packets = self.catalog()
        self.reports = self.ledger()

    def stock_station(self):
        source = self.station()
        register(source.registry, 'X', ['A', 'B', 'C'], ['P', 'Q', 'R', 'U'])
        return source

    def issued(self, source, scale, values, sheet):
        return issue_frozen(source, self.packets, record_for(source, 'X', scale, values, sheet))

    def use(self, packets, reference, pairs):
        return review(self.packets, self.reports, [piece.packet_id for piece in packets], reference.packet_id, pairs)

    def assert_results(self, decision, expected):
        self.assertEqual(decision.status, 'signed')
        self.assertEqual(
            [(row.start, row.end, row.millimeters) for row in decision.report.results], expected
        )
        self.assertEqual(decision.receipt.report_id, decision.report.report_id)

    def test_original_three_scale_handoff(self):
        source = self.stock_station()
        a = self.issued(source, 'A', {'P': 0, 'Q': 1}, 'sheet-a')
        b = self.issued(source, 'B', {'Q': 0, 'R': 1}, 'sheet-b')
        c = self.issued(source, 'C', {'R': -1, 'P': 1}, 'sheet-c')
        source.close()
        self.packets.close()
        self.packets = self.catalog()
        result = self.use([c, a, b], a, [('P', 'R')])
        self.assert_results(result, [('P', 'R', 2)])
        self.assertEqual(result.report.reference_packet_id, a.packet_id)
        self.assertEqual(
            [(item.packet_id, item.scale, item.revision_id) for item in result.report.bindings],
            [(p.packet_id, p.scale, p.revision_id) for p in (c, a, b)],
        )
        self.assertEqual(
            {(entry.packet_id, entry.revision_id, entry.mark, entry.sheet, entry.line)
             for entry in result.report.origins},
            {(c.packet_id, c.revision_id, 'P', 'sheet-c', 2), (c.packet_id, c.revision_id, 'R', 'sheet-c', 1),
             (a.packet_id, a.revision_id, 'P', 'sheet-a', 1), (a.packet_id, a.revision_id, 'Q', 'sheet-a', 2),
             (b.packet_id, b.revision_id, 'Q', 'sheet-b', 1), (b.packet_id, b.revision_id, 'R', 'sheet-b', 2)},
        )
        self.assertEqual(read(self.reports, result.report.report_id), (result.report, result.receipt))

    def test_cross_zero_distinguishes_true_colocation(self):
        source = self.stock_station()
        crossing = self.issued(source, 'C', {'R': -1, 'P': 1}, 'crossing')
        colocated = self.issued(source, 'C', {'R': 1, 'P': 1}, 'colocated')
        source.close()
        for packet, value, sheet in ((crossing, 2, 'crossing'), (colocated, 0, 'colocated')):
            with self.subTest(sheet=sheet):
                stored = self.packets.get(packet.packet_id)
                self.assertEqual(stored.shape.offset_of('P') - stored.shape.offset_of('R'), value)
                outcome = self.use([packet], packet, [('R', 'P')])
                self.assert_results(outcome, [('R', 'P', value)])
                self.assertEqual(
                    [(row.mark, row.sheet, row.line) for row in outcome.report.origins],
                    [('P', sheet, 2), ('R', sheet, 1)],
                )

    def test_directed_colocation_and_empty_compatible_request(self):
        source = self.stock_station()
        a = self.issued(source, 'A', {'P': -2, 'Q': 0, 'U': 0}, 'directed')
        source.close()
        outcome = self.use([a], a, [('P', 'Q'), ('Q', 'P'), ('Q', 'U')])
        self.assert_results(outcome, [('P', 'Q', 2), ('Q', 'P', -2), ('Q', 'U', 0)])
        empty = self.use([a], a, [])
        self.assert_results(empty, [])
        self.assertEqual(self.reports.counts(), (2, 2))

    def test_independent_unit_packets_every_pair_fits_but_triple_conflicts(self):
        a = fixed_packet('X', 'A', {'P': 0, 'Q': 1})
        b = fixed_packet('X', 'B', {'Q': 0, 'R': 1})
        c = fixed_packet('X', 'C', {'R': 0, 'P': 1})
        for packet in a, b, c:
            self.packets.save(packet)
        for pair in combinations((a, b, c), 2):
            with self.subTest(scales=[piece.scale for piece in pair]):
                self.assert_results(self.use(pair, pair[0], []), [])
        before = self.reports.counts()
        self.assertEqual(before, (3, 3))
        for pairs in ([('P', 'R')], []):
            with self.subTest(pairs=pairs):
                outcome = self.use([a, b, c], a, pairs)
                self.assertEqual(outcome.status, 'conflict')
                self.assertIsNone(outcome.report)
                self.assertIsNone(outcome.receipt)
                self.assertEqual(self.reports.counts(), before)

    def test_corrected_cycle_refuses_new_signature_and_preserves_old(self):
        source = self.stock_station()
        a = self.issued(source, 'A', {'P': 0, 'Q': 1}, 'sheet-a')
        b = self.issued(source, 'B', {'Q': 0, 'R': 1}, 'sheet-b')
        base = record_for(source, 'X', 'C', {'R': -1, 'P': 1}, 'sheet-c')
        c = issue_frozen(source, self.packets, base)
        source.close()
        old = self.use([a, b, c], a, [('P', 'R')])
        self.assert_results(old, [('P', 'R', 2)])
        source = self.station()
        corrected = record_for(source, 'X', 'C', {'P': 0}, 'correction', base_revision=base.revision_id)
        new_c = issue_frozen(source, self.packets, corrected)
        source.close()
        before = self.reports.counts()
        self.assertEqual(before, (1, 1))
        outcome = self.use([a, b, new_c], a, [('P', 'R')])
        self.assertEqual(outcome.status, 'conflict')
        self.assertIsNone(outcome.report)
        self.assertIsNone(outcome.receipt)
        self.assertEqual(self.reports.counts(), before)
        self.reports.close()
        self.assertEqual(read(self.ledger(), old.report.report_id), (old.report, old.receipt))

    def test_repeated_shared_marks_must_fit_same_placement(self):
        reference = fixed_packet('X', 'A', {'P': 0, 'Q': 1, 'R': 2})
        reflected = fixed_packet('X', 'B', {'Q': 0, 'P': 1, 'R': -1, 'U': -2})
        incompatible = fixed_packet('X', 'C', {'Q': 0, 'P': 1, 'R': 1})
        for packet in reference, reflected, incompatible:
            self.packets.save(packet)
        result = self.use([reflected, reference], reference, [('P', 'U')])
        self.assert_results(result, [('P', 'U', 3)])
        self.assertEqual(self.use([reference, incompatible], reference, []).status, 'conflict')
        self.assertEqual(self.reports.counts(), (1, 1))

    def test_mixed_specimens_rejected_even_with_common_mark_name(self):
        source = self.stock_station()
        register(source.registry, 'Y', ['A'], ['P'])
        a = self.issued(source, 'A', {'P': 0}, 'sheet-x')
        other = issue_frozen(source, self.packets, record_for(source, 'Y', 'A', {'P': 0}, 'sheet-y'))
        source.close()
        with self.assertRaisesRegex(ValueError, 'different specimens'):
            self.use([a, other], a, [('P', 'P')])
        self.assertEqual(self.reports.counts(), (0, 0))

    def test_missing_packet_and_reference_and_invalid_selection(self):
        a = fixed_packet('X', 'A', {'P': 0})
        self.packets.save(a)
        with self.assertRaisesRegex(LookupError, 'fixed packet not found'):
            review(self.packets, self.reports, [a.packet_id, 'missing'], a.packet_id, [])
        with self.assertRaisesRegex(ValueError, 'reference packet is not selected'):
            review(self.packets, self.reports, [a.packet_id], 'missing', [])
        for ids in ([], [a.packet_id] * 2, ['a', 'b', 'c', 'd']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                review(self.packets, self.reports, ids, a.packet_id, [])
        self.assertEqual(self.reports.counts(), (0, 0))

    def test_ambiguous_zero_and_repeated_items_round_trip_in_order(self):
        a = fixed_packet('X', 'A', {'P': 0, 'Q': 1})
        b = fixed_packet('X', 'B', {'Q': 0, 'R': 1})
        for packet in a, b:
            self.packets.save(packet)
        outcome = self.use([a, b], a, [('P', 'R'), ('Q', 'Q'), ('P', 'R')])
        self.assert_results(outcome, [('P', 'R', None), ('Q', 'Q', 0), ('P', 'R', None)])
        self.reports.close()
        self.assertEqual(read(self.ledger(), outcome.report.report_id), (outcome.report, outcome.receipt))

    def test_free_translation_separates_components(self):
        a = fixed_packet('X', 'A', {'P': 0, 'Q': 1})
        d = fixed_packet('X', 'D', {'U': 0, 'V': 1})
        for packet in a, d:
            self.packets.save(packet)
        outcome = self.use([a, d], a, [('P', 'U'), ('P', 'Q'), ('U', 'U'), ('U', 'V')])
        self.assert_results(outcome, [('P', 'U', None), ('P', 'Q', 1), ('U', 'U', 0), ('U', 'V', None)])

    def test_unknown_endpoint_and_malformed_pair_leave_report_ledger_empty(self):
        a = fixed_packet('X', 'A', {'P': 0, 'Q': 1})
        self.packets.save(a)
        with self.assertRaisesRegex(ValueError, 'unknown request mark'):
            self.use([a], a, [('P', 'U')])
        for pairs in (['PQ'], [('P',)], [('P', 'Q', 'P')]):
            with self.subTest(pairs=pairs), self.assertRaisesRegex(ValueError, 'two marks'):
                self.use([a], a, pairs)
        self.assertEqual(self.reports.counts(), (0, 0))
