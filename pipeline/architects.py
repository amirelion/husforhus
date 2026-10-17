"""Rare architects' names stay off private houses.

On a private house (KATEGORI in city.PRIVATE_HOUSE_KATEGORI, not curated: the same test as the decade rule's RAÄ link, never the
`private` flag, which only dated houses carry) an architect's name is shown only when it appears on more than
city.ARCHITECT_MAX_RARE buildings citywide. A name that rare on a villa is often the owner's, a private person.
Well-known architects appear on many buildings, so their names stay. A rare firm, office or cooperative name shows
only once a person has read it and put it on pipeline/private_firms.txt: a person whose name merely looks like a firm
("Karl & Anna Svensson", "BERG") would otherwise leak, and no pattern can tell them apart for certain.

is_firm() proposes the names to read, from the name alone: a company form (AB, HB, KB), the architects' association
(SAR, MSA), a known organisation (HSB, Riksbyggen, FFNS, VBB), an office word (arkitekt…, kontor, byrå, firma, bolag,
konsult, ingenjör, grupp, studio, förening, stiftelse, nämnd, verket…), a partnership ("Höjer & Ljungqvist") or a
whole name that is an acronym. A comma list of people ("S Ancker, B Gate, S Lindegren") is no candidate. On
2026-10-16 the rule hides 482 personal names on 565 houses, and the 55 rare names that read as firms wait in
data/review-architects.txt until a person has read them; until then they are hidden too.
"""
import re
from collections import Counter

from . import city

FIRM = re.compile(
    r"\b(AB|HB|KB|SAR|MSA|HSB|FFNS|VBB|SWECO|WSP)\b|aktiebolag|arkitekt|architect|kontor|byrå|firma|bolag|"
    r"förening|förbund|stiftelse|kooperativ|riksbyggen|bostäder|nämnd|styrelse|verket|grupp|studio|konsult|"
    r"ingenjör|samfund|konsum|husindustri|trähus|egnahem|&", re.IGNORECASE)
ACRONYM = re.compile(r"[A-ZÅÄÖ]{2,6}")


def is_firm(name: str) -> bool:
    return bool(FIRM.search(name) or ACRONYM.fullmatch(name.strip()))


def counts(lists, keys=None) -> Counter:
    """Buildings per name, citywide: a name counts once per building however often it is listed there. `keys` gives
    each entry's building (s02_attributes: its RAÄ record): LOD1 often splits one building into several footprints
    that share a record, and they count once, so an owner's name on one villa in four parts stays rare."""
    if keys is None:
        return Counter(n for names in lists for n in set(names))
    return Counter(n for _, n in {(k, n) for names, k in zip(lists, keys) for n in names})


def keep(names, n_buildings: Counter, max_rare: int | None = None, firms=frozenset()) -> list[str]:
    """A private house's architects as its card may show them: names on more than max_rare buildings, and the
    reviewed firms (pipeline/private_firms.txt)."""
    max_rare = city.ARCHITECT_MAX_RARE if max_rare is None else max_rare
    return [n for n in names if n_buildings[n] > max_rare or n in firms]


def apply_rule(lists, private_category, max_rare: int | None = None,
               firms=frozenset(), keys=None) -> tuple[list[list[str]], list[str]]:
    """(architects per building with the rule applied where private_category is True; the rare names on those houses
    that read as firms and are not on the reviewed list yet, sorted, for a person to read). `lists` holds every
    building's names: the counts are citywide. `firms`: the reviewed firm names; `keys`: each entry's building
    (counts)."""
    n_buildings = counts(lists, keys)
    max_rare = city.ARCHITECT_MAX_RARE if max_rare is None else max_rare
    out, candidates = [], set()
    for names, private in zip(lists, private_category):
        names = list(names)
        if private:
            candidates |= {n for n in names if is_firm(n) and n_buildings[n] <= max_rare and n not in firms}
            names = keep(names, n_buildings, max_rare, firms)
        out.append(names)
    return out, sorted(candidates)
