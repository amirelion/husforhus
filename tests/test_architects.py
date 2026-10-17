"""Rare architects' names on private houses."""
import pytest

from pipeline import architects as arch


@pytest.mark.parametrize(("name", "firm"), [
    ("Stockholms Stads Byggnadskontor", True), ("HSB", True), ("Riksbyggen", True), ("FFNS", True),
    ("Höjer & Ljungqvist", True), ("J Höjer S Ljungquist Arkitekter SAR", True), ("AB Svenska Bostäder", True),
    ("Nils Rasing Arkitektkontor AB", True), ("Statens byggnadsbyrå", True), ("Byggnadsfirman Anders Diös", True),
    ("Brunnberggruppen Arkitekter AB", True), ("Sergler Konsult AB", True), ("Småstugebyrån", True),
    ("Stockholms stads Lantegendomsnämnd", True), ("Åtvidabergs Husindustri AB", True), ("KÅHK Arkitekter", True),
    ("Edvin Engström", False), ("Björn Hedvall", False), ("Erik F. Dahl", False), ("N. W. Larsson", False),
    ("S Ancker, B Gate, S Lindegren", False),       # a list of people, not a firm: a person wrongly read as a firm leaks
    ("Carl-Eddie Lund", False), ("ERIK LUNDBERG", False), ("L U Kjaersgaard Rasmussen", False),
])
def test_is_firm(name, firm):
    # is_firm only proposes names for a person to read; a rare name shows on a villa only from the reviewed list
    assert arch.is_firm(name) is firm


def test_counts_are_buildings_per_name():
    c = arch.counts([["A", "A", "B"], ["A"], []])
    assert (c["A"], c["B"], c["C"]) == (2, 1, 0)


def test_apply_rule_hides_rare_names_on_private_houses_unless_a_person_listed_the_firm():
    lists = [["Rare Person", "Firma AB"], ["Rare Person"], ["Common One"], ["Common One"], ["Common One"],
             ["Common One"], ["Rare Person", "Common One"], ["Karl & Anna Svensson"]]
    private = [True, False, False, False, False, True, False, True]
    out, candidates = arch.apply_rule(lists, private, max_rare=3)
    # "Rare Person" is on 3 buildings: hidden on the private ones; "Common One" is on 5: shown everywhere; the rare
    # names that read as firms are hidden too until a person has read them (a couple's names read as a firm)
    assert out == [[], ["Rare Person"], ["Common One"], ["Common One"], ["Common One"], ["Common One"],
                   ["Rare Person", "Common One"], []]
    assert candidates == ["Firma AB", "Karl & Anna Svensson"]                    # for the hand check
    out, candidates = arch.apply_rule(lists, private, max_rare=3, firms={"Firma AB"})
    assert out[0] == ["Firma AB"] and out[7] == [] and candidates == ["Karl & Anna Svensson"]
    assert arch.apply_rule(lists, private, max_rare=2)[0][0] == ["Rare Person"]   # 3 > 2: shown; the firm still waits
    assert arch.keep(["Rare Person"], arch.counts(lists), 3) == []


def test_a_name_counts_once_per_record_however_many_footprints_share_it():
    # LOD1 splits one building into several footprints, all linked to one RAÄ record. Counted per
    # footprint, an owner's name on one villa in four parts would pass "more than 3" and ship.
    lists = [["Olle Owner"]] * 4
    assert arch.apply_rule(lists, [True] * 4, max_rare=3, keys=["a"] * 4)[0] == [[], [], [], []]
    assert arch.counts(lists, keys=["a", "a", "b", "c"])["Olle Owner"] == 3
    assert arch.apply_rule(lists, [True] * 4, max_rare=3)[0] == lists       # without keys: one per entry, as before
