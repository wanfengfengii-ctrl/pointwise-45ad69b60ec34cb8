from intake.origins import ReadingOrigin
from intake.readings import record
from intake.revisions import Reading
from intake.station import freeze, initialize_station
from registry.catalog import register
from tests import WorkspaceCase, record_for


class IntakeTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        self.specimen = register(self.source.registry, 'X', ['B', 'A'], ['Q', 'P'])

    def test_reopen_catalog_and_frozen_integer_readings(self):
        original = record_for(self.source, 'X', 'A', {'P': 0, 'Q': -4}, 'sheet-1')
        self.assertEqual(freeze(self.source, 'X', 'A', original.revision_id), original.revision_id)
        self.source.close()
        reopened = self.station()
        initialize_station(reopened.connection)
        reused = register(reopened.registry, 'X', ['A', 'B'], ['P', 'Q'])
        self.assertEqual(reused, self.specimen)
        self.assertEqual(freeze(reopened, 'X', 'A', original.revision_id), original.revision_id)
        saved = reopened.load_revision('X', 'A', original.revision_id)
        self.assertTrue(saved.is_frozen())
        self.assertEqual(saved.readings, (
            Reading('P', 0, ReadingOrigin('sheet-1', 1)),
            Reading('Q', -4, ReadingOrigin('sheet-1', 2)),
        ))
        self.assertEqual(reopened.revision_count('X'), 1)

    def test_catalog_conflict_and_invalid_rosters_preserve_original(self):
        for scales, marks in ((['A'], ['P', 'Q']), (['A', 'B'], ['P']), (['A', 'A'], ['P']), (['A'], [])):
            with self.subTest(scales=scales, marks=marks), self.assertRaises(ValueError):
                register(self.source.registry, 'X', scales, marks)
        with self.assertRaises(ValueError):
            register(self.source.registry, 'Y', 'A', ['P'])
        self.assertEqual(self.source.registry.load_specimen('X'), self.specimen)
        with self.assertRaises(LookupError):
            self.source.registry.load_specimen('Y')

    def test_freeze_owner_and_missing_revision(self):
        original = record_for(self.source, 'X', 'A', {'P': 0}, 'source')
        register(self.source.registry, 'Y', ['A'], ['P'])
        for specimen, scale in (('X', 'B'), ('Y', 'A')):
            with self.subTest(specimen=specimen, scale=scale), self.assertRaisesRegex(ValueError, 'belongs'):
                freeze(self.source, specimen, scale, original.revision_id)
        with self.assertRaises(LookupError):
            freeze(self.source, 'X', 'A', 'missing')
        self.assertEqual(self.source.load_revision('X', 'A', original.revision_id), original)
        self.assertFalse(original.is_frozen())

    def test_invalid_readings_and_origins_do_not_append(self):
        original = record_for(self.source, 'X', 'A', {'P': 0}, 'original')
        good = ReadingOrigin('sheet', 1)
        invalid = [
            ({'P': None}, {'P': good}),
            ({'P': 1.5}, {'P': good}),
            ({'P': False}, {'P': good}),
            ({'P': '1'}, {'P': good}),
            ({'P': 1}, {}),
            ({'P': 1}, {'P': None}),
            ({'P': 1}, {'P': ReadingOrigin(' ', 1)}),
            ({'P': 1}, {'P': ReadingOrigin('sheet', 0)}),
            ({'P': 1}, {'P': ReadingOrigin('sheet', True)}),
            ({}, {}),
        ]
        for positions, origins in invalid:
            with self.subTest(positions=positions, origins=origins), self.assertRaises(ValueError):
                record(self.source, 'X', 'A', positions, origins)
        self.assertEqual(self.source.revision_count('X'), 1)
        self.assertEqual(self.source.load_revision('X', 'A', original.revision_id), original)

    def test_foreign_mark_preserves_frozen_revision(self):
        register(self.source.registry, 'Y', ['A'], ['P', 'R'])
        record_for(self.source, 'Y', 'A', {'R': 3}, 'foreign')
        original = record_for(self.source, 'X', 'A', {'P': -1}, 'local')
        freeze(self.source, 'X', 'A', original.revision_id)
        frozen = self.source.load_revision('X', 'A', original.revision_id)
        with self.assertRaisesRegex(ValueError, 'unknown mark'):
            record_for(self.source, 'X', 'A', {'P': 1, 'R': 3}, 'mixed-row')
        self.assertEqual(self.source.revision_count('X'), 1)
        self.assertEqual(self.source.load_revision('X', 'A', original.revision_id), frozen)
        self.assertEqual(frozen.readings, (Reading('P', -1, ReadingOrigin('local', 1)),))

    def test_correction_rejects_wrong_owner_and_missing_base(self):
        base = record_for(self.source, 'X', 'A', {'P': 0}, 'original')
        with self.assertRaisesRegex(ValueError, 'belongs'):
            record_for(self.source, 'X', 'B', {'P': 4}, 'correction', base_revision=base.revision_id)
        with self.assertRaises(LookupError):
            record_for(self.source, 'X', 'A', {'P': 4}, 'correction', base_revision='missing')
        self.assertEqual(self.source.revision_count('X'), 1)
