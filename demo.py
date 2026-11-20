import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import range_cases
from intake.origins import ReadingOrigin
from intake.readings import record, record_ranges
from intake.station import freeze, open_station
from issue.catalog import open_packet_catalog
from issue.codec import decode_packet, encode_packet
from issue.publish import issue
from registry.catalog import register
from report.ledger import open_report_ledger
from report.readback import read
from review.decisions import review, review_ranges


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


def _range_capture(station, scale, values, sheet, *, base_revision=None):
    origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(values, 1)}
    return record_ranges(station, range_cases.SPECIMEN, scale, values, origins, base_revision=base_revision)


def _range_exact(station, scale, values, sheet):
    origins = {mark: ReadingOrigin(sheet, line) for line, mark in enumerate(values, 1)}
    return record(station, range_cases.SPECIMEN, scale, values, origins)


def _range_summary(outcome):
    report = outcome.report
    return {
        'status': outcome.status,
        'bounds_mm': None if report is None else [[item.minimum, item.maximum] for item in report.results],
        'receipt': outcome.receipt is not None,
    }


def _original_case():
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


def _range_case():
    pairs = [tuple(pair) for pair in range_cases.TRIPLE_PAIRS]
    coincidence_pairs = [tuple(pair) for pair in range_cases.COINCIDENCE_PAIRS]
    isolated_pairs = [tuple(pair) for pair in range_cases.ISOLATED_PAIRS]
    with TemporaryDirectory() as directory:
        root = Path(directory)
        station_path = root / 'range-station.sqlite'
        issued_path = root / 'range-issued.sqlite'
        received_path = root / 'range-received.sqlite'
        ledger_path = root / 'range-ledger.sqlite'
        # 白班：区间与精确录入，冻结发行。
        with open_station(station_path) as station, open_packet_catalog(issued_path) as issued:
            register(station.registry, range_cases.SPECIMEN, range_cases.SCALES, range_cases.MARKS)
            triple_a = _range_capture(station, 'A', range_cases.TRIPLE_A, 'PM-A1')
            packets = {
                'A': _issue(station, issued, triple_a),
                'B': _issue(station, issued, _range_exact(station, 'B', range_cases.TRIPLE_B, 'PM-B')),
                'C': _issue(station, issued, _range_exact(station, 'C', range_cases.TRIPLE_C, 'PM-C')),
                'coupled': _issue(station, issued, _range_capture(station, 'A', range_cases.COUPLED, 'PM-AC')),
                'independent': _issue(station, issued, _range_capture(station, 'A', range_cases.INDEPENDENT, 'PM-AI')),
                'coincident': _issue(station, issued, _range_exact(station, 'B', range_cases.COINCIDENT, 'PM-BC')),
                'isolated': _issue(station, issued, _range_exact(station, 'D', range_cases.ISOLATED_D, 'PM-D')),
            }
        # 交换编码传到独立接收目录，随后关闭站库和发行目录。
        with open_packet_catalog(received_path) as received:
            for packet in packets.values():
                received.save(decode_packet(encode_packet(packet)))
        a, b, c = packets['A'], packets['B'], packets['C']
        # 夜班断源复核：只开接收目录和签报账。
        with open_packet_catalog(received_path) as received, open_report_ledger(ledger_path) as ledger:
            triple_first = review_ranges(received, ledger, [a.packet_id, b.packet_id, c.packet_id], a.packet_id, pairs)
            coupled = review_ranges(
                received, ledger, [packets['coupled'].packet_id, packets['coincident'].packet_id],
                packets['coupled'].packet_id, coincidence_pairs,
            )
            coupled_empty = review_ranges(
                received, ledger, [packets['coupled'].packet_id, packets['coincident'].packet_id],
                packets['coupled'].packet_id, [],
            )
            independent = review_ranges(
                received, ledger, [packets['independent'].packet_id, packets['coincident'].packet_id],
                packets['independent'].packet_id, coincidence_pairs,
            )
            isolated = review_ranges(
                received, ledger, [a.packet_id, b.packet_id, packets['isolated'].packet_id], a.packet_id, isolated_pairs,
            )
            counts_before = ledger.counts()
        # 次日按初版底稿勘误 A，只提交 Q 及新出处，另冻结发行并交接。
        with open_station(station_path) as station, open_packet_catalog(issued_path) as issued:
            corrected_revision = _range_capture(
                station, 'A', range_cases.CORRECTION_A, 'PM-A2', base_revision=triple_a.revision_id
            )
            corrected = _issue(station, issued, corrected_revision)
        with open_packet_catalog(received_path) as received:
            received.save(decode_packet(encode_packet(corrected)))
        with open_packet_catalog(received_path) as received, open_report_ledger(ledger_path) as ledger:
            triple_corrected = review_ranges(
                received, ledger, [corrected.packet_id, b.packet_id, c.packet_id], corrected.packet_id, pairs,
            )
            counts_after = ledger.counts()
        # 关闭接收目录和签报账后，只重开签报账按号领取。
        with open_report_ledger(ledger_path) as ledger:
            first_bundle = read(ledger, triple_first.report.report_id)
            corrected_bundle = read(ledger, triple_corrected.report.report_id)
            reopened_counts = ledger.counts()

        history = None
        if first_bundle is not None and corrected_bundle is not None:
            history = {
                'first_bundle': first_bundle == (triple_first.report, triple_first.receipt),
                'corrected_bundle': corrected_bundle == (triple_corrected.report, triple_corrected.receipt),
                'corrected_p_origin_kept': [
                    [row.sheet, row.line]
                    for row in triple_corrected.report.origins
                    if row.packet_id == corrected.packet_id and row.mark == 'P'
                ],
                'corrected_q_origin': [
                    [row.sheet, row.line]
                    for row in triple_corrected.report.origins
                    if row.packet_id == corrected.packet_id and row.mark == 'Q'
                ],
            }

        case = {
            'case_id': 'R5.range_cycle',
            'input': {
                'specimen': range_cases.SPECIMEN,
                'triple_a_mm': range_cases.TRIPLE_A,
                'correction_a_mm': range_cases.CORRECTION_A,
                'reference': 'A',
                'pairs': pairs,
            },
            'packet_versions': {name: packet.version for name, packet in sorted(packets.items())},
            'expected': {
                'triple_first': {'status': 'signed', 'bounds_mm': [list(b) for b in range_cases.TRIPLE_EXPECTED], 'receipt': True},
                'triple_corrected': {'status': 'signed', 'bounds_mm': [list(b) for b in range_cases.CORRECTION_EXPECTED], 'receipt': True},
                'coupled': {'status': 'conflict', 'bounds_mm': None, 'receipt': False},
                'coupled_empty': {'status': 'conflict', 'bounds_mm': None, 'receipt': False},
                'independent': {'status': 'signed', 'bounds_mm': [[0, 0]], 'receipt': True},
                'isolated': {'status': 'signed', 'bounds_mm': [[None, None], [0, 0], [1, 3]], 'receipt': True},
            },
            'actual': {
                'triple_first': _range_summary(triple_first),
                'triple_corrected': _range_summary(triple_corrected),
                'coupled': _range_summary(coupled),
                'coupled_empty': _range_summary(coupled_empty),
                'independent': _range_summary(independent),
                'isolated': _range_summary(isolated),
            },
            'downstream_expected': {
                'counts_before': [3, 3], 'counts_after': [4, 4], 'counts_reopened': [4, 4],
                'history': {
                    'first_bundle': True, 'corrected_bundle': True,
                    'corrected_p_origin_kept': [['PM-A1', 1]], 'corrected_q_origin': [['PM-A2', 1]],
                },
            },
            'downstream_actual': {
                'counts_before': list(counts_before), 'counts_after': list(counts_after),
                'counts_reopened': list(reopened_counts), 'history': history,
            },
            'code_paths': ['intake/readings.py', 'intake/station.py', 'issue/publish.py', 'issue/shape.py',
                           'issue/codec.py', 'review/ranges.py', 'review/decisions.py',
                           'report/publish.py', 'report/ledger.py', 'report/readback.py'],
            'oracle': 'A reads P=0 and Q in [1,3]; B and C are exact. Only (Q,R)=(1,-1) or (3,1) place all three, so P->R spans [-1,1]. The correction Q in [2,3] leaves a single placement with P->R=1. COUPLED forces R-Q=1 against Q=R and conflicts even with an empty request; INDEPENDENT allows Q=R=0. D shares no marks, so Q->S is unbounded while S->S is 0.',
        }
        if case['actual'] != case['expected'] or case['downstream_actual'] != case['downstream_expected']:
            print('RANGE_HANDOFF_MISMATCH ' + json.dumps(case, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
        print('RANGE_SCENARIO ' + json.dumps(case, ensure_ascii=False, sort_keys=True))
        print('区间件断源复核：初版 P→R∈[-1,1]，勘误后 P→R=1。COUPLED 组连空请求也冲突，INDEPENDENT 组签 P→R=[0,0]。重开签报账按新旧号领取原绑定、结果、出处和首执。')
        return 0


def main():
    original = _original_case()
    if original:
        return original
    return _range_case()


if __name__ == '__main__':
    raise SystemExit(main())
