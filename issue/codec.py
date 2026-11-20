import json

from .envelope import Packet, PacketOrigin, validate_packet
from .shape import IntervalShape, ScaleShape


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
    if packet.version == 1:
        body = {
            'anchor': packet.shape.anchor,
            'offsets': [[mark, hex(offset)] for mark, offset in packet.shape.offsets],
            'origins': [[row.mark, row.sheet, hex(row.line)] for row in packet.origins],
        }
    else:
        body = {
            'anchor': packet.shape.anchor,
            'spans': [[mark, hex(lower), hex(upper)] for mark, lower, upper in packet.shape.spans],
            'origins': [[row.mark, row.sheet, hex(row.line)] for row in packet.origins],
        }
    payload = {
        'version': packet.version,
        'packet_id': packet.packet_id,
        'specimen': packet.specimen,
        'scale': packet.scale,
        'revision_id': packet.revision_id,
        'body': body,
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def decode_packet(text: str) -> Packet:
    try:
        payload = json.loads(text, object_pairs_hook=_object)
        if type(payload) is not dict or payload.keys() != {
            'version', 'packet_id', 'specimen', 'scale', 'revision_id', 'body'
        }:
            raise ValueError('invalid packet envelope')
        version = payload['version']
        body = payload['body']
        if type(body) is not dict:
            raise ValueError('invalid packet body')
        if version == 1:
            if body.keys() != {'anchor', 'offsets', 'origins'}:
                raise ValueError('invalid packet body')
            shape = ScaleShape(
                body['anchor'],
                tuple((mark, _integer(offset)) for mark, offset in _rows(body['offsets'], 2)),
            )
        elif version == 2:
            if body.keys() != {'anchor', 'spans', 'origins'}:
                raise ValueError('invalid packet body')
            shape = IntervalShape(
                body['anchor'],
                tuple(
                    (mark, _integer(lower), _integer(upper))
                    for mark, lower, upper in _rows(body['spans'], 3)
                ),
            )
        else:
            raise ValueError('unsupported fixed packet version')
        origins = tuple(PacketOrigin(mark, sheet, _integer(line)) for mark, sheet, line in _rows(body['origins'], 3))
        packet = Packet(
            payload['packet_id'], payload['specimen'], payload['scale'], payload['revision_id'],
            shape, origins, version,
        )
        return validate_packet(packet)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'invalid fixed packet: {exc}') from exc
