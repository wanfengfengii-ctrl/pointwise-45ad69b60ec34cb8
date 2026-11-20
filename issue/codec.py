import json

from .envelope import Packet, PacketOrigin, validate_packet
from .shape import ScaleShape


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f'duplicate packet field: {name}')
        result[name] = value
    return result


def _integer(value: str) -> int:
    if type(value) is not str:
        raise ValueError('packet integer must be hex text')
    number = int(value, 16)
    if hex(number) != value:
        raise ValueError('packet integer must use canonical hex text')
    return number


def _rows(value: object, width: int) -> list:
    if type(value) is not list or any(type(row) is not list or len(row) != width for row in value):
        raise ValueError('invalid packet body rows')
    return value


def encode_packet(packet: Packet) -> str:
    validate_packet(packet)
    payload = {
        'version': packet.version,
        'packet_id': packet.packet_id,
        'specimen': packet.specimen,
        'scale': packet.scale,
        'revision_id': packet.revision_id,
        'body': {
            'anchor': packet.shape.anchor,
            'offsets': [[mark, hex(offset)] for mark, offset in packet.shape.offsets],
            'origins': [[row.mark, row.sheet, hex(row.line)] for row in packet.origins],
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def decode_packet(text: str) -> Packet:
    try:
        payload = json.loads(text, object_pairs_hook=_object)
        if type(payload) is not dict or payload.keys() != {
            'version', 'packet_id', 'specimen', 'scale', 'revision_id', 'body'
        }:
            raise ValueError('invalid packet envelope')
        body = payload['body']
        if type(body) is not dict or body.keys() != {'anchor', 'offsets', 'origins'}:
            raise ValueError('invalid packet body')
        offsets = tuple((mark, _integer(offset)) for mark, offset in _rows(body['offsets'], 2))
        origins = tuple(PacketOrigin(mark, sheet, _integer(line)) for mark, sheet, line in _rows(body['origins'], 3))
        packet = Packet(
            payload['packet_id'], payload['specimen'], payload['scale'], payload['revision_id'],
            ScaleShape(body['anchor'], offsets), origins, payload['version'],
        )
        return validate_packet(packet)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'invalid fixed packet: {exc}') from exc
