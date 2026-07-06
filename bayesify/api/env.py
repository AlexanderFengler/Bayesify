"""API startup env-file loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvLoad:
    path: Path
    keys: tuple[str, ...]


def load_env_file() -> EnvLoad:
    """Load ``bayesify.env`` without overriding variables already set by the process/host."""
    path = Path(os.environ.get("BAYESIFY_ENV_FILE", "bayesify.env"))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return EnvLoad(path=path, keys=())
    
    loaded = []
    for raw in text.splitlines():
        line = raw.strip().removeprefix("export ").lstrip()

        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()

        if not sep or not key or key in os.environ:
            continue
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value
        loaded.append(key)

    return EnvLoad(path=path, keys=tuple(sorted(loaded)))
