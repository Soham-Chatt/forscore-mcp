import pytest

from forscore_mcp import keys


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("C major", 110),
        ("A minor", 611),
        ("G minor", 511),
        ("E♭ major", 300),
        ("Eb", 300),
        ("F# major", 420),
        ("f♯ minor", 421),
        ("Bbm", 701),
        ("D", 210),
    ],
)
def test_encode(name: str, code: int) -> None:
    assert keys.encode(name) == code


@pytest.mark.parametrize(("code", "name"), [(110, "C major"), (611, "A minor"), (300, "E♭ major")])
def test_decode(code: int, name: str) -> None:
    assert keys.decode(code) == name


def test_round_trip_all_codes() -> None:
    for note in range(1, 8):
        for accidental in range(3):
            for mode in range(2):
                code = note * 100 + accidental * 10 + mode
                assert keys.encode(keys.decode(code)) == code


@pytest.mark.parametrize("bad", ["H major", "", "C dorian"])
def test_encode_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        keys.encode(bad)


@pytest.mark.parametrize("bad", [0, 810, 131, 112])
def test_decode_rejects(bad: int) -> None:
    with pytest.raises(ValueError):
        keys.decode(bad)
