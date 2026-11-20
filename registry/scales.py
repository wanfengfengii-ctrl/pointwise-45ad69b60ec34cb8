from dataclasses import dataclass


def _validate_scale(name: str) -> None:
    if type(name) is not str or not name or name.strip() != name or '\x00' in name:
        raise ValueError('invalid scale name')


@dataclass(frozen=True, slots=True)
class ScaleRoster:
    names: tuple[str, ...]

    def require_scale(self, name: str) -> str:
        _validate_scale(name)
        if name not in self.names:
            raise ValueError(f'unknown scale: {name}')
        return name


def build_scale_roster(names) -> ScaleRoster:
    if isinstance(names, (str, bytes, dict)):
        raise ValueError('provide a collection of scale names')
    try:
        items = tuple(names)
    except TypeError as exc:
        raise ValueError('provide a collection of scale names') from exc
    for name in items:
        _validate_scale(name)
    if not items or len(set(items)) != len(items):
        raise ValueError('scale roster must be nonempty and unique')
    return ScaleRoster(tuple(sorted(items)))
