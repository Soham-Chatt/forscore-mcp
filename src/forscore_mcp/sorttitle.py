"""Sort-title normalisation, mirroring what forScore stores in ZSORTTITLE."""

import re

_LEADING_ARTICLE = re.compile(r"^(The|A|An)\s+", re.IGNORECASE)
_PUNCTUATION = re.compile("[.,()'\u2019\\-:]")


def sort_title(title: str) -> str:
    return _PUNCTUATION.sub("", _LEADING_ARTICLE.sub("", title.strip()))
