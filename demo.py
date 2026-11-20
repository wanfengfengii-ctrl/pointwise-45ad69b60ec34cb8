import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.origins import ReadingOrigin
from intake.readings import record
from intake.station import freeze, open_station
from issue.catalog import open_packet_catalog
from issue.publish import issue
from registry.catalog import register
from report.ledger import open_report_ledger
from report.readback import read
from review.decisions import review


def _capture(station, scale, values, sheet, *, base_revision=None):
    origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(values, 1)}
    return record(station, 'CC-17', scale, values, origins, base_revision=base_revision)


def _issue(station, catalog, revision):
    number = freeze(station, revision.specimen, revision.scale, revision.revision_id)
    return issue(station, catalog, revision.specimen, revision.scale, number)


def _summary(outcome):
    report = outcome.report
    return {
        'status': outcome.status,
        'results_mm': None if report is None else [item.millimeters for item in report.results],
        'receipt': outcome.receipt is not None,
    }


def main():
    readings = {'A': {'P': 0, 'Q': 1}, 'B': {'Q': 0, 'R': 1}, 'C': {'R': -1, 'P': 1}}
    correction = {'P': 0}
    pairs = [('P', 'R')]
    with TemporaryDirectory() as directory:
        root = Path(directory)
        station_path = root / 'station.sqlite'
        packet_path = root / 'packets.sqlite'
        ledger_path = root / 'reports.sqlite'
        with open_station(station_path) as station, open_packet_catalog(packet_path) as catalog:
            register(station.registry, 'CC-17', ['A', 'B', 'C'], ['P', 'Q', 'R'])
            originals = {scale: _capture(station, scale, values, f'AM-{scale}') for scale, values in readings.items()}
            a, b, c = (_issue(station, catalog, originals[scale]) for scale in ('A', 'B', 'C'))
        with open_packet_catalog(packet_path) as catalog, open_report_ledger(ledger_path) as ledger:
            first = review(catalog, ledger, [a.packet_id, b.packet_id, c.packet_id], a.packet_id, pairs)
            before = ledger.counts()
        with open_station(station_path) as station, open_packet_catalog(packet_path) as catalog:
            updated = _capture(station, 'C', correction, 'ERR-C', base_revision=originals['C'].revision_id)
            corrected = _issue(station, catalog, updated)
        with open_packet_catalog(packet_path) as catalog, open_report_ledger(ledger_path) as ledger:
            second = review(catalog, ledger, [a.packet_id, b.packet_id, corrected.packet_id], a.packet_id, pairs)
            after = ledger.counts()
        with open_report_ledger(ledger_path) as ledger:
            original_bundle = None if first.report is None else read(ledger, first.report.report_id)
            reopened_counts = ledger.counts()

        history = None
        if original_bundle is not None:
            report, receipt = original_bundle
            history = {
                'results_mm': [row.millimeters for row in report.results],
                'original_bundle': original_bundle == (first.report, first.receipt),
                'original_bindings': [item.packet_id for item in report.bindings] == [a.packet_id, b.packet_id, c.packet_id],
                'receipt_bound': receipt.report_id == report.report_id,
                'c_origins': {row.mark: [row.sheet, row.line] for row in report.origins if row.packet_id == c.packet_id},
            }

        case = {
            'case_id': 'V5.corrected_cycle',
            'input': {'readings_mm': readings, 'correction_mm': {'C': correction}, 'reference': 'A', 'pairs': pairs},
            'expected': {
                'initial': {'status': 'signed', 'results_mm': [2], 'receipt': True},
                'corrected': {'status': 'conflict', 'results_mm': None, 'receipt': False},
            },
            'actual': {'initial': _summary(first), 'corrected': _summary(second)},
            'downstream_expected': {
                'counts_before': [1, 1], 'counts_after': [1, 1], 'counts_reopened': [1, 1],
                'history': {'results_mm': [2], 'original_bundle': True, 'original_bindings': True,
                            'receipt_bound': True, 'c_origins': {'P': ['AM-C', 2], 'R': ['AM-C', 1]}},
            },
            'downstream_actual': {
                'counts_before': list(before), 'counts_after': list(after),
                'counts_reopened': list(reopened_counts), 'history': history,
            },
            'code_paths': ['intake/readings.py', 'issue/publish.py', 'issue/shape.py', 'review/alignment.py',
                           'review/decisions.py', 'report/ledger.py', 'report/readback.py'],
            'oracle': 'A fixes P=0 and Q=1. B allows R in {0,2}. Initial C allows R in {-2,2}; corrected C allows R in {-1,1}. The first intersection is {2}; the second is empty. Only the first request adds a report and its original receipt.',
        }
        if case['actual'] != case['expected'] or case['downstream_actual'] != case['downstream_expected']:
            print('SCALE_HANDOFF_MISMATCH ' + json.dumps(case, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
        print('POINTWISE_SCENARIO ' + json.dumps(case, ensure_ascii=False, sort_keys=True))
        print('初版 P→R 确认 +2 mm。勘误后冲突。重开后原签报、出处和回执可领取。')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
