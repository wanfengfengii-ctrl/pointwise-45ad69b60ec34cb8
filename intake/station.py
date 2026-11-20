import sqlite3
from uuid import uuid4

from registry.catalog import RegistryCatalog, initialize_registry
from registry.specimens import validate_specimen_number

from .origins import ReadingOrigin
from .revisions import Reading, Revision


def initialize_station(connection: sqlite3.Connection) -> None:
    connection.execute('PRAGMA foreign_keys = ON')
    initialize_registry(connection)
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS reading_revisions (
                revision_id TEXT PRIMARY KEY NOT NULL,
                specimen TEXT NOT NULL REFERENCES specimens(number),
                scale TEXT NOT NULL,
                base_revision TEXT REFERENCES reading_revisions(revision_id),
                frozen INTEGER NOT NULL DEFAULT 0 CHECK (frozen IN (0, 1))
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS reading_rows (
                revision_id TEXT NOT NULL REFERENCES reading_revisions(revision_id),
                mark TEXT NOT NULL,
                position_hex TEXT NOT NULL,
                sheet TEXT NOT NULL,
                line_hex TEXT NOT NULL,
                PRIMARY KEY (revision_id, mark)
            )
        ''')


class IntakeStation:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.registry = RegistryCatalog(connection)

    def __enter__(self) -> 'IntakeStation':
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def load_revision(self, specimen: str, scale: str, revision_id: str) -> Revision:
        if type(revision_id) is not str or not revision_id:
            raise ValueError('invalid revision number')
        header = self.connection.execute(
            '''SELECT specimen, scale, base_revision, frozen
               FROM reading_revisions WHERE revision_id = ?''',
            (revision_id,),
        ).fetchone()
        if header is None:
            raise LookupError(f'revision not found: {revision_id}')
        owner, ruler, base, frozen = header
        if (owner, ruler) != (specimen, scale):
            raise ValueError('revision belongs to another specimen or scale')
        rows = self.connection.execute(
            '''SELECT mark, position_hex, sheet, line_hex FROM reading_rows
               WHERE revision_id = ? ORDER BY mark''',
            (revision_id,),
        )
        readings = tuple(
            Reading(mark, int(position, 16), ReadingOrigin(sheet, int(line, 16)))
            for mark, position, sheet, line in rows
        )
        if not readings:
            raise sqlite3.DatabaseError('revision is missing its readings')
        return Revision(revision_id, owner, ruler, base, readings, bool(frozen))

    def append_revision(
        self, specimen: str, scale: str, readings: tuple[Reading, ...], base_revision: str | None = None
    ) -> Revision:
        owner = self.registry.load_specimen(specimen)
        owner.scales.require_scale(scale)
        if base_revision is not None:
            self.load_revision(specimen, scale, base_revision)
        rows = tuple(readings)
        if not rows or any(not isinstance(reading, Reading) for reading in rows):
            raise ValueError('revision requires validated readings')
        for reading in rows:
            owner.marks.require_mark(reading.mark)
        rows = tuple(sorted(rows, key=lambda reading: reading.mark))
        if len({row.mark for row in rows}) != len(rows):
            raise ValueError('duplicate reading mark')
        revision_id = uuid4().hex
        with self.connection:
            self.connection.execute(
                '''INSERT INTO reading_revisions (revision_id, specimen, scale, base_revision)
                   VALUES (?, ?, ?, ?)''',
                (revision_id, specimen, scale, base_revision),
            )
            self.connection.executemany(
                '''INSERT INTO reading_rows (revision_id, mark, position_hex, sheet, line_hex)
                   VALUES (?, ?, ?, ?, ?)''',
                ((revision_id, row.mark, hex(row.millimeters), row.origin.sheet, hex(row.origin.line))
                 for row in rows),
            )
        return Revision(revision_id, specimen, scale, base_revision, rows, False)

    def revision_count(self, specimen: str) -> int:
        validate_specimen_number(specimen)
        return self.connection.execute(
            'SELECT COUNT(*) FROM reading_revisions WHERE specimen = ?', (specimen,)
        ).fetchone()[0]


def open_station(path) -> IntakeStation:
    connection = sqlite3.connect(path)
    try:
        initialize_station(connection)
    except BaseException:
        connection.close()
        raise
    return IntakeStation(connection)


def freeze(station: IntakeStation, specimen: str, scale: str, revision_id: str) -> str:
    with station.connection:
        station.load_revision(specimen, scale, revision_id)
        station.connection.execute(
            'UPDATE reading_revisions SET frozen = 1 WHERE revision_id = ? AND frozen = 0',
            (revision_id,),
        )
    return revision_id
