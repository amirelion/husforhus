"""pipeline.s13_quests and pipeline/quests.py: steps resolve to landmark gids and are dropped on a failed check."""
import pandas as pd

from pipeline import s08_landmarks
from pipeline.landmarks import LANDMARKS
from pipeline.quests import QUESTS
from pipeline.s13_quests import build, source_url

YEARS = pd.DataFrame({"gid": [3, 7, 8], "year": [1306, 1754, 1754], "landmark": ["Storkyrkan", "Stockholms slott",
                                                                                 "Stockholms slott"]})
TEXT = {"sv:A": "Den invigdes 1306 – mellan torget och slottet.", "sv:B": "Slottet togs i bruk 1754."}


def q(*steps):
    return [{"id": "t", "level": 1, "title": {"en": "T", "sv": "T"}, "intro": {"en": "", "sv": ""}, "steps": list(steps)}]


def find(at="lm:Storkyrkan", checks=(("sv:A", ["invigdes 1306 — mellan"]),)):
    return {"kind": "find", "at": at, "riddle": {"en": "r", "sv": "r"}, "hints": [], "reveal": {"en": "", "sv": ""},
            "checks": list(checks), "mode": None}


def test_a_step_gets_its_landmarks_gids_and_source_urls():
    out, problems = build(q(find()), YEARS, text=TEXT.get)
    assert problems == []
    step = out[0]["steps"][0]
    assert step["gids"] == [3] and step["sources"] == ["https://sv.wikipedia.org/wiki/A"]
    assert "checks" not in step and "at" not in step and "mode" not in step


def test_a_failed_check_or_missing_landmark_drops_the_quest():
    assert build(q(find(checks=[("sv:A", ["1307"])])), YEARS, text=TEXT.get)[0] == []
    out, problems = build(q(find(at="lm:Nowhere")), YEARS, text=TEXT.get)
    assert out == [] and any("Nowhere" in p for p in problems)


def test_a_year_step_must_be_the_maps_year():
    y = {"kind": "year", "at": "lm:Stockholms slott", "ask": {}, "year": 1754, "reveal": {},
         "checks": [("sv:B", ["1754"])]}
    assert build(q(y), YEARS, text=TEXT.get)[0][0]["steps"][0]["gids"] == [7, 8]
    assert build(q({**y, "year": 1760}), YEARS, text=TEXT.get)[0] == []


def test_source_url_escapes_the_title():
    assert source_url("sv:Tyska kyrkan, Stockholm") == "https://sv.wikipedia.org/wiki/Tyska_kyrkan%2C_Stockholm"


def test_the_quests_are_well_formed_and_point_at_curated_landmarks():
    names = {L["name"]: L for L in LANDMARKS}
    ids = [x["id"] for x in QUESTS]
    assert len(ids) == len(set(ids))
    for quest in QUESTS:
        assert quest["level"] in (1, 2, 3) and set(quest["title"]) == {"en", "sv"}
        for s in quest["steps"]:
            name = s["at"].removeprefix("lm:")
            assert s["at"].startswith("lm:") and name in names, s["at"]
            assert s["checks"] and all(src.partition(":")[0] in s08_landmarks.LANGS for src, _ in s["checks"])
            texts = [s.get(k) for k in ("riddle", "ask", "reveal")] + s.get("hints", []) + s.get("options", [])
            assert all(set(t) == {"en", "sv"} for t in texts if t)
            if s["kind"] == "year":
                assert s["year"] == names[name]["year"]
            if s["kind"] == "choice":
                assert len(s["options"]) == 3
