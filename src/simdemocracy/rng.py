"""Independent random streams.

Unrelated subsystems do not share a stream, so a change in rumour noise does
not reshuffle elections or party names. Seeds are derived with SHA-256 because
Python's built-in hash() is salted per process.
"""

from __future__ import annotations

import hashlib
import random

STREAM_NAMES = (
    "gen",
    "social",
    "names",
    "decision",
    "info",
    "rumor",
    "election",
    "internal",
    "coalition",
)


def _stream_seed(seed: int, name: str) -> int:
    digest = hashlib.sha256(f"{seed}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


class Streams:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams = {
            name: random.Random(_stream_seed(seed, name)) for name in STREAM_NAMES
        }

    def __getattr__(self, name: str) -> random.Random:
        try:
            return self._streams[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
