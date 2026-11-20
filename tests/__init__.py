from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from intake.origins import ReadingOrigin
from intake.readings import record
from intake.station import freeze, open_station
from issue.catalog import open_packet_catalog
from issue.publish import issue
from report.ledger import open_report_ledger


class WorkspaceCase(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def station(self):
        return self.enterContext(open_station(self.root / 'station.sqlite'))

    def catalog(self):
        return self.enterContext(open_packet_catalog(self.root / 'packets.sqlite'))

    def ledger(self):
        return self.enterContext(open_report_ledger(self.root / 'reports.sqlite'))


def record_for(station, specimen, scale, readings, sheet, *, base_revision=None):
    origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(readings, 1)}
    return record(station, specimen, scale, readings, origins, base_revision=base_revision)


def issue_frozen(station, catalog, revision):
    number = freeze(station, revision.specimen, revision.scale, revision.revision_id)
    return issue(station, catalog, revision.specimen, revision.scale, number)
