import json
import sqlite3
from dataclasses import replace

from intake.station import freeze
from issue.catalog import initialize_packet_catalog
from issue.codec import decode_packet, encode_packet
from issue.publish import issue
from registry.catalog import register
from tests import WorkspaceCase, issue_frozen, record_for


class IssueTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.source = self.station()
        self.packets = self.catalog()
        register(self.source.registry, 'X', ['A', 'B'], ['P', 'Q'])

    def test_unfrozen_unknown_and_wrong_owner_leave_catalog_unchanged(self):
        prior = issue_frozen(self.source, self.packets, record_for(self.source, 'X', 'A', {'P': 0}, 'old'))
        draft = record_for(self.source, 'X', 'A', {'P': 1}, 'draft')
        with self.assertRaisesRegex(ValueError, 'must be frozen'):
            issue(self.source, self.packets, 'X', 'A', draft.revision_id)
        with self.assertRaisesRegex(ValueError, 'belongs'):
            issue(self.source, self.packets, 'X', 'B', prior.revision_id)
        with self.assertRaises(LookupError):
            issue(self.source, self.packets, 'X', 'A', 'missing')
        self.assertEqual(self.packets.count(), 1)
        self.assertEqual(self.packets.get(prior.packet_id), prior)
        self.assertEqual(self.source.load_revision('X', 'A', draft.revision_id), draft)

    def test_publish_failure_does_not_leave_packet(self):
        prior = issue_frozen(self.source, self.packets, record_for(self.source, 'X', 'A', {'P': 0}, 'old'))
        draft = record_for(self.source, 'X', 'A', {'P': 1, 'Q': 3}, 'new')
        freeze(self.source, 'X', 'A', draft.revision_id)
        frozen = self.source.load_revision('X', 'A', draft.revision_id)
        self.packets.connection.execute('''
            CREATE TEMP TRIGGER fail_issue AFTER INSERT ON fixed_packets
            BEGIN SELECT RAISE(ABORT, 'packet write rejected'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'packet write rejected'):
            issue(self.source, self.packets, 'X', 'A', draft.revision_id)
        self.packets.close()
        reopened = self.catalog()
        self.assertEqual(reopened.count(), 1)
        self.assertEqual(reopened.get(prior.packet_id), prior)
        self.assertEqual(self.source.load_revision('X', 'A', draft.revision_id), frozen)
        successful = issue(self.source, reopened, 'X', 'A', draft.revision_id)
        self.assertEqual(successful.revision_id, draft.revision_id)
        self.assertEqual(reopened.count(), 2)

    def test_codec_round_trip_preserves_identity_and_exact_relative_values(self):
        huge = 1 << 16000
        draft = record_for(self.source, 'X', 'A', {'P': 17, 'Q': 17 - huge}, 'source-sheet')
        packet = issue_frozen(self.source, self.packets, draft)
        self.source.close()
        self.packets.close()
        reopened = self.catalog()
        initialize_packet_catalog(reopened.connection)
        text = encode_packet(packet)
        wire = json.loads(text)
        self.assertEqual(set(wire), {'version', 'packet_id', 'specimen', 'scale', 'revision_id', 'body'})
        self.assertEqual(wire['version'], 1)
        self.assertEqual(wire['body']['offsets'], [['P', '0x0'], ['Q', hex(-huge)]])
        self.assertEqual(set(wire['body']), {'anchor', 'offsets', 'origins'})
        decoded = decode_packet(text)
        self.assertEqual(decoded, packet)
        self.assertEqual(reopened.get(packet.packet_id), packet)
        reopened.save(decoded)
        with self.assertRaisesRegex(ValueError, 'conflicting fixed packet'):
            reopened.save(replace(decoded, revision_id='another-revision'))
        self.assertEqual(reopened.count(), 1)
        self.assertEqual(reopened.get(packet.packet_id), packet)

    def test_decode_rejects_missing_origin_and_duplicate_envelope_field(self):
        packet = issue_frozen(self.source, self.packets, record_for(self.source, 'X', 'A', {'P': 0}, 'sheet'))
        text = encode_packet(packet)
        payload = json.loads(text)
        payload['body']['origins'].clear()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            decode_packet(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'duplicate packet field'):
            decode_packet('{"version":1,' + text[1:])
        self.assertEqual(self.packets.count(), 1)
