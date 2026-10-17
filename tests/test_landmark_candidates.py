"""The landmark candidates list."""
import pandas as pd

from pipeline import landmark_candidates as lc


def test_candidates_put_unknown_and_disagreeing_first_and_gamla_stan_first_within():
    wiki = pd.DataFrame({"gid": [0, 1, 2, 3, 4, 5], "qid": ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5"],
                         "label": ["Ö", "B", "C", "A", "D", "E"], "wp_sv": ["Ö", "B", "", "A", "D", ""],
                         "wp_en": ["", "", "C", "", "", ""], "lon": [18.07] * 6, "lat": [59.32] * 6})
    years = pd.DataFrame({"gid": [0, 1, 2, 3, 4, 5], "year": [0, 1700, 1900, 0, 1754, 1800],
                          "ysrc": [0, 2, 2, 0, 1, 2], "period": [0, 2, 5, 0, 2, 3]})
    review = {"wikidata_vs_raa": [{"gid": 1}]}
    stadsdel = pd.Series(["SÖDERMALM", "GAMLA STAN", "NORRMALM", "GAMLA STAN", "GAMLA STAN", "X"], index=range(6))
    c = lc.candidates(wiki, years, review, stadsdel)
    # gid 4 is curated already; gid 5 has no article
    assert c.gid.tolist() == [3, 0, 1, 2]
    assert c.group.tolist() == ["unknown", "unknown", "disagrees", "dated"]
    assert c.article.tolist() == ["sv:A", "sv:Ö", "sv:B", "en:C"]
    assert c.source.tolist() == ["none", "none", "raa", "raa"]
    md = lc.render(c)
    assert md.startswith("# Landmark candidates") and "## unknown (2)" in md and "| p1 | A | Q3 | sv:A |" in md
