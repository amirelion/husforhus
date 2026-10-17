import json

from pipeline import city, metro, run, s03_tiles, s16_metro, s99_validate
from pipeline.sources import check_sources, load_sources


def raw():
    """metro.build's shape (EPSG:3011), three stations near Stortorget, one never opened, one renamed."""
    ox, oy = city.ORIGIN
    st = lambda name, dx, lines, opened, status="open", **kw: {  # noqa: E731
        "name": name, "xy": [ox + dx, oy], "lines": lines, "status": status, "opening_date": opened,
        "closing_date": kw.get("closed"), "renames": kw.get("renames", []), "wikidata": kw.get("qid")}
    return {"stations": [
        st("Slussen", 0, ["green", "red"], "1950-10-01", qid="Q1"),
        st("Hötorget", 1000, ["green"], "1952-10-26", qid="Q2",
           renames=[{"name": "Kungsgatan", "from": "1952-10-26", "to": "1957-11-23"},
                    {"name": "Hötorget", "from": "1957-11-24", "to": None}]),
        st("Kymlinge", 2000, ["blue"], None, status="never_opened", qid="Q3")],
        "segments": [{"id": "S01", "line": "green", "opening_date": "1950-10-01", "closing_date": None,
                      "stations": ["Slussen", "Hötorget"],
                      "track": {"coords": [[ox, oy], [ox + 500, oy + 0.5], [ox + 1000, oy]]}},
                     {"id": "S02", "line": "red", "opening_date": "1964-04-05", "closing_date": None,
                      "stations": ["Slussen", "Hötorget"]}]}


def test_layer_is_local_dated_and_simplified():
    m = s16_metro.layer(raw())
    s1, s2 = m["segments"]
    assert s1 == {"id": "S01", "line": "green", "opened": "1950-10-01", "stations": ["Slussen", "Hötorget"],
                  "track": [[0.0, -0.0], [1000.0, -0.0]]}          # local frame, the 0.5 m kink simplified away
    assert s2["track"] == [[0.0, -0.0], [1000.0, -0.0]]              # no track: station to station
    by = {s["name"]: s for s in m["stations"]}
    assert by["Hötorget"]["names"] == [{"name": "Kungsgatan", "from": "1952-10-26", "to": "1957-11-23"}]
    assert by["Hötorget"]["wikidata"] == "Q2" and by["Hötorget"]["x"] == 1000.0
    assert by["Kymlinge"]["never"] is True and by["Kymlinge"]["opened"] is None
    assert "never" not in by["Slussen"] and "closed" not in by["Slussen"]


def test_s99_checks_metro(tmp_path):
    assert s99_validate.check_metro(tmp_path) == []                   # a version without the layer
    m = s16_metro.layer(raw())
    (tmp_path / "metro.json").write_text(json.dumps(m), encoding="utf-8")
    assert s99_validate.check_metro(tmp_path) == []
    m["segments"][0]["opened"] = "1950-13-01"
    m["segments"][1]["stations"].append("Atlantis")
    m["stations"][0]["x"] = 99_000.0
    m["stations"][1]["closed"] = "soon"
    (tmp_path / "metro.json").write_text(json.dumps(m), encoding="utf-8")
    errors = s99_validate.check_metro(tmp_path)
    assert any("S01 has an opening date that does not parse" in e for e in errors)
    assert any("S02 names stations not in the list: ['Atlantis']" in e for e in errors)
    assert any("Hötorget is not inside the map" in e for e in errors)
    assert any("closing date that does not parse: 'soon'" in e for e in errors)


def test_registered_after_s03_tiles_with_its_sources():
    assert run.STEPS.index("s16_metro") == run.STEPS.index("s03_tiles") + 1
    sources = load_sources()
    assert check_sources(sources, release=True) == []
    by = {s["id"]: s for s in sources}
    assert by["metro_stations"]["licence"] == "CC0-1.0" and by["metro_track"]["licence"] == "ODbL-1.0"
    assert city.FEATURES["metro"] is True
    shown = {a["id"] for a in s03_tiles.attribution(sources)}
    assert {"metro_stations", "metro_track"} <= shown


def test_the_real_tables_build():
    m = s16_metro.layer(metro.build(None))
    assert len(m["segments"]) == 32 and len(m["stations"]) == 101
    assert [s["name"] for s in m["stations"] if s.get("never")] == ["Kymlinge"]
