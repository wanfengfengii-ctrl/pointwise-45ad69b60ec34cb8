import json
import sqlite3

from .marks import build_mark_roster
from .scales import build_scale_roster
from .specimens import Specimen, validate_specimen_number


def initialize_registry(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS specimens (
                number TEXT PRIMARY KEY NOT NULL,
                scales TEXT NOT NULL,
                marks TEXT NOT NULL
            )
        ''')


class RegistryCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def load_specimen(self, number: str) -> Specimen:
        validate_specimen_number(number)
        row = self.connection.execute(
            'SELECT scales, marks FROM specimens WHERE number = ?', (number,)
        ).fetchone()
        if row is None:
            raise LookupError(f'specimen not found: {number}')
        scales, marks = row
        return Specimen(number, build_scale_roster(json.loads(scales)), build_mark_roster(json.loads(marks)))


def register(catalog: RegistryCatalog, number: str, scales, marks) -> Specimen:
    specimen = Specimen(validate_specimen_number(number), build_scale_roster(scales), build_mark_roster(marks))
    with catalog.connection:
        inserted = catalog.connection.execute(
            '''INSERT INTO specimens (number, scales, marks) VALUES (?, ?, ?)
               ON CONFLICT(number) DO NOTHING''',
            (number, json.dumps(specimen.scales.names), json.dumps(specimen.marks.names)),
        )
        if inserted.rowcount == 1:
            return specimen
        existing = catalog.load_specimen(number)
        if not existing.same_rosters(specimen):
            raise ValueError(f'conflicting roster for specimen: {number}')
        return existing
