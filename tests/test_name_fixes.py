"""pipeline/name_fixes.csv: card names moved or dropped by hand, applied by s03_tiles."""
import pandas as pd
import pytest

from pipeline import name_fixes


def table(*rows):
    return pd.DataFrame(rows, columns=name_fixes.COLUMNS, dtype=str)


def cards():
    return pd.DataFrame({"gid": [27404, 71157, 5], "qid": ["", "Q32926", "Q9"],
                         "name": ["Globen", "Avicii Arena", ""], "wname": ["", "Globen", "Stationen"],
                         "wname_en": ["", "Avicii Arena", "The station"]})


def test_the_committed_table_reads_and_holds_globen():
    t = name_fixes.read()
    assert list(t.key) == ["27404", "18487"]
    assert (t.action[0], t.target[0]) == ("drop", "")


def test_move_puts_the_name_on_the_target_and_takes_it_off_the_source():
    out = name_fixes.apply(cards(), table(["27404", "move", "71157", "Globen is the dome"])).set_index("gid")
    assert out.at[71157, "name"] == "Globen"
    assert (out.at[27404, "name"], out.at[27404, "wname"]) == ("", "")
    assert out.at[71157, "qid"] == "Q32926"                                   # the dome keeps its own item


def test_drop_by_wikidata_id_clears_every_name():
    out = name_fixes.apply(cards(), table(["Q9", "drop", "", "the item is the station, not this hall"]))
    assert out.set_index("gid").loc[5, ["name", "wname", "wname_en"]].tolist() == ["", "", ""]


def test_a_fix_for_a_footprint_not_in_the_build_is_skipped(capsys):
    df = cards()[lambda d: d.gid == 5]                                        # a fixture build: no Globen
    out = name_fixes.apply(df, table(["27404", "move", "71157", "x"]))
    assert out.equals(df) and "skipped" in capsys.readouterr().err


@pytest.mark.parametrize("row", [["27404", "rename", "71157", "x"], ["27404", "move", "", "x"],
                                 ["27404", "drop", "71157", "x"], ["Globen", "drop", "", "x"],
                                 ["27404", "move", "71157", ""]])
def test_a_malformed_row_is_refused(tmp_path, row):
    path = tmp_path / "f.csv"
    table(row).to_csv(path, index=False)
    with pytest.raises(ValueError):
        name_fixes.read(path)
