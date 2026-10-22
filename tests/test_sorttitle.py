import pytest

from forscore_mcp.sorttitle import sort_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("The Legend of Korra", "Legend of Korra"),
        ("Grandpa's Theme", "Grandpas Theme"),
        ("La cloche sonne, S. 238", "La cloche sonne S 238"),
        ("An Unwavering Heart", "Unwavering Heart"),
        ("Theme", "Theme"),
    ],
)
def test_sort_title(title: str, expected: str) -> None:
    assert sort_title(title) == expected
