"""Resolve user-owned config paths relative to the config file, when known."""
from pathlib import Path


def resolve_path(value, base_dir=None):
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    return path.resolve()
