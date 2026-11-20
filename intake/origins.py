from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadingOrigin:
    sheet: str
    line: int


def validate_origin(origin: ReadingOrigin) -> ReadingOrigin:
    if not isinstance(origin, ReadingOrigin):
        raise ValueError('each reading needs a ReadingOrigin')
    if type(origin.sheet) is not str or not origin.sheet.strip() or '\x00' in origin.sheet:
        raise ValueError('origin sheet must be a nonempty reference')
    if type(origin.line) is not int or origin.line < 1:
        raise ValueError('origin line must be a positive integer')
    return origin
