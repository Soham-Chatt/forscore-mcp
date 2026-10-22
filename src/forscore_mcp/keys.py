"""Musical key codec.

forScore stores a key as a three-digit integer:
hundreds = note (C=1 ... B=7), tens = accidental (0 flat, 1 natural, 2 sharp),
units = mode (0 major, 1 minor). Example: 611 = A minor, 300 = E-flat major.
"""

from __future__ import annotations

import re

NOTES = "CDEFGAB"
_ACCIDENTAL_SYMBOL = {0: "♭", 1: "", 2: "♯"}
_ACCIDENTAL_INPUT = {"b": 0, "♭": 0, "": 1, "#": 2, "♯": 2}
_MODES = ("major", "minor")
_PATTERN = re.compile(
    r"^\s*([A-Ga-g])\s*(b|♭|#|♯)?\s*(major|minor|maj|min|m)?\s*$",
)


def encode(name: str) -> int:
    """Turn a key name such as "A minor", "F# major", "Eb" or "Bbm" into its code."""
    match = _PATTERN.match(name)
    if not match:
        raise ValueError(f"Not a key name: {name!r} (try e.g. 'A minor' or 'E♭ major')")
    note, accidental, mode = match.groups()
    minor = mode in ("minor", "min", "m")
    return (
        (NOTES.index(note.upper()) + 1) * 100
        + _ACCIDENTAL_INPUT[accidental or ""] * 10
        + int(minor)
    )


def decode(code: int) -> str:
    """Turn a stored code such as 611 into a readable name such as "A minor"."""
    note, accidental, mode = code // 100, code // 10 % 10, code % 10
    if not (1 <= note <= 7 and accidental in _ACCIDENTAL_SYMBOL and mode in (0, 1)):
        raise ValueError(f"Not a forScore key code: {code}")
    return f"{NOTES[note - 1]}{_ACCIDENTAL_SYMBOL[accidental]} {_MODES[mode]}"
