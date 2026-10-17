"""fold(): the one text normalisation search uses, in the pipeline (s14_search) and in the browser (web/fold.js).

Lower case; accents off (å ä → a, ö → o, é → e, ü → u); "S:ta " before a name becomes "sankta ", and "S:t", "St." and
"St" before a name "sankt"; every run of characters that are neither letters nor digits becomes one space; a trailing
"Stockholm" and a postcode after a house number go ("Hornsgatan 30 A, 118 20 Stockholm" → "hornsgatan 30 a"). The
same vectors pin both versions (web/test/fixtures/fold.json, read by tests/test_textfold.py and web/test/fold.test.mjs).
"""
import re
import unicodedata

SANKTA = re.compile(r"(?<![^\W_])s:ta\s+(?=[^\W\d_])")
SANKT = re.compile(r"(?<![^\W_])(?:s:t\s*|st\.\s*|st\s+)(?=[^\W\d_])")
NOT_ALNUM = re.compile(r"[\W_]+")
CITY_TAIL = re.compile(r"^(.+) stockholm$")
POSTCODE = re.compile(r"( \d+(?: ?[a-z])?) \d{3} ?\d{2}$")


def fold(text: str) -> str:
    s = unicodedata.normalize("NFD", str(text).lower())
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    s = SANKT.sub("sankt ", SANKTA.sub("sankta ", s))
    s = NOT_ALNUM.sub(" ", s).strip()
    s = CITY_TAIL.sub(r"\1", s)
    return POSTCODE.sub(r"\1", s)
