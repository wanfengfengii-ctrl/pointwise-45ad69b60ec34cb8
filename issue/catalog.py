import sqlite3

from .codec import decode_packet, encode_packet
from .envelope import Packet


def initialize_packet_catalog(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS fixed_packets (
                packet_id TEXT PRIMARY KEY NOT NULL,
                payload TEXT NOT NULL
            )
        ''')


class PacketCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def __enter__(self) -> 'PacketCatalog':
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def save(self, packet: Packet) -> None:
        payload = encode_packet(packet)
        with self.connection:
            inserted = self.connection.execute(
                '''INSERT INTO fixed_packets (packet_id, payload) VALUES (?, ?)
                   ON CONFLICT(packet_id) DO NOTHING''',
                (packet.packet_id, payload),
            )
            if inserted.rowcount == 0 and self.get(packet.packet_id) != packet:
                raise ValueError(f'conflicting fixed packet: {packet.packet_id}')

    def get(self, packet_id: str) -> Packet:
        if type(packet_id) is not str or not packet_id:
            raise ValueError('invalid fixed packet number')
        row = self.connection.execute(
            'SELECT payload FROM fixed_packets WHERE packet_id = ?', (packet_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f'fixed packet not found: {packet_id}')
        packet = decode_packet(row[0])
        if packet.packet_id != packet_id:
            raise ValueError('stored packet identity does not match catalog key')
        return packet

    def count(self) -> int:
        return self.connection.execute('SELECT COUNT(*) FROM fixed_packets').fetchone()[0]


def open_packet_catalog(path) -> PacketCatalog:
    connection = sqlite3.connect(path)
    try:
        initialize_packet_catalog(connection)
    except BaseException:
        connection.close()
        raise
    return PacketCatalog(connection)
