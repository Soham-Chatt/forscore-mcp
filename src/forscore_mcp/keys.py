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


# forScore's CSV import/export uses a MIDI-style key signature instead of the code above:
# keysf = number of sharps (negative: flats), keymi = 0 major / 1 minor.
_FIFTHS = "FCGDAEB"  # position + 7 * accidental = sharps of the major key (F = -1 ... B = 5)
_ACCIDENTAL_STEP = {"♭": -1, "": 0, "♯": 1}


def to_signature(name: str) -> tuple[int, int] | None:
    """ "A minor" -> (0, 1). None if the key needs more than 7 sharps or flats (e.g. D♯ major)."""
    code = encode(name)
    letter, accidental, minor = NOTES[code // 100 - 1], code // 10 % 10 - 1, code % 10
    sharps = _FIFTHS.index(letter) - 1 + 7 * accidental - 3 * minor
    return (sharps, minor) if -7 <= sharps <= 7 else None


def from_signature(sharps: int, minor: int) -> str:
    """(0, 1) -> "A minor"; (-3, 0) -> "E♭ major". The inverse of to_signature."""
    if not (-7 <= sharps <= 7 and minor in (0, 1)):
        raise ValueError(f"Not a key signature: {sharps}, {minor}")
    position = sharps + 3 * minor + 1
    accidental = {-1: "♭", 0: "", 1: "♯"}[position // 7]
    return f"{_FIFTHS[position % 7]}{accidental} {_MODES[minor]}"
