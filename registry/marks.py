from dataclasses import dataclass


def _validate_mark(name: str) -> None:
    if type(name) is not str or not name or name.strip() != name or '\x00' in name:
        raise ValueError('invalid mark name')


@dataclass(frozen=True, slots=True)
class MarkRoster:
    names: tuple[str, ...]

    def require_mark(self, name: str) -> str:
        _validate_mark(name)
        if name not in self.names:
            raise ValueError(f'unknown mark: {name}')
        return name


def build_mark_roster(names) -> MarkRoster:
    if isinstance(names, (str, bytes, dict)):
        raise ValueError('provide a collection of mark names')
    try:
        items = tuple(names)
    except TypeError as exc:
        raise ValueError('provide a collection of mark names') from exc
    for name in items:
        _validate_mark(name)
    if not items or len(set(items)) != len(items):
        raise ValueError('mark roster must be nonempty and unique')
    return MarkRoster(tuple(sorted(items)))
