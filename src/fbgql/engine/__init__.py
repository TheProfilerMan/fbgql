"""Engine backends."""

from __future__ import annotations

from .asyncio_engine import AsyncEngine
from .base import Engine
from .threaded import ThreadedEngine

_ENGINES = {
    "threads": ThreadedEngine,
    "async": AsyncEngine,
}


def get_engine(name: str) -> Engine:
    try:
        return _ENGINES[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown engine {name!r}; choose one of {sorted(_ENGINES)}") from exc


__all__ = ["Engine", "ThreadedEngine", "AsyncEngine", "get_engine"]
