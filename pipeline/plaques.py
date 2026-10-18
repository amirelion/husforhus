"""Samfundet S:t Erik's blue plaques (kulturhusskyltar): the list, the plaque texts, and the building each is on.

parse_list(): the rows of the society's plaque list (skyltförteckning, a PDF; s00_fetch_plaques) as the text pypdf
gives it: "1.  Börshuset Källargränd 2 (Rådstugan 1) (Skylt saknas) 27666 1995". A row is its list number, the
popular name and address, the Stockholmskällan post that holds the plaque's text (its id, stable when the list is
renumbered, so it is the plaque's id) and the year it was put up ("1993 (rev 2013)": 1993). A row may wrap over
lines. The parenthesised property designation ("(Rådstugan 1)") is dropped as it is read, so it never reaches web/
(s99's privacy check); "(Skylt saknas)" marks a plaque that is not on the wall now.
split_address(): the name and the street address in "Den Gyldene Freden Österlånggatan 51": the address is the first
"street number" after the name, the street one the city's addresses know (or, without them, one that ends like a
street). text_from_post(): the plaque's Swedish text on its Stockholmskällan post (published there by the society).
place(): the footprint a plaque is on: its address in s02_addresses' table first (the street as the list writes it or
a street_variants form of it), else its Open Plaques position (the footprint it lies in, or the nearest within
POSITION_M), else its address with letter_variants for the numbers, else the one card whose name is the plaque's name
(by_name), else none; a bridge's plaque (the list's "Broskyltar") never goes on a footprint. Never a guess: a variant or a name that fits more than one footprint places nothing, and the plaque is
listed in the review file. Only what the list and the plaque say is
kept, and cut() leaves out a sentence that says who owned a building or had it built (spec §6.3, as for Wikipedia's
excerpts): never an owner or a resident.
"""
import html
import re

import numpy as np
import pandas as pd

from .addresses import numbers
from .privacy import mentions, owner, phrases
from .textfold import fold
from .wiki import split_sentences

CREDIT = "Samfundet S:t Erik, CC BY 4.0"
POSITION_M = 25.0            # a plaque sits on a facade: its position can lie a few metres outside the footprint
ROW = re.compile(r"^(\d+)\.\s+(.*)$")
TAIL = re.compile(r"\s(\d{5})(?:,\s*\w+)?\s+(\d{4}\b.*)$")    # "27460 1993 (rev 2013)", "28044, logga 1998"
MISSING = re.compile(r"\(\s*skylt saknas\s*\)", re.I)
PAREN = re.compile(r"\([^()]*\)?")                            # a designation, or one cut off by a wrapped row
STREET_END = re.compile(r"(gatan|gata|vägen|väg|gränd|torg|torget|plan|backe|backen|brinken|bron|strand|stranden|"
                        r"hamnen|kajen|slätten|park|parken|allé|allén|liden|stigen|platsen|terrassen|passagen|kroken|"
                        r"gången|tull|tullen|slingan|svängen|lunden)$", re.I)
PREFIXES = {"Södra", "Norra", "Östra", "Västra", "Stora", "Lilla", "Sankt", "S:t", "Gamla", "Nya"}
NUMBERISH = re.compile(r"^(\d+[A-Za-z]?|[A-Z]|[–-]|\d+[A-Za-z]?[–-]\d*[A-Za-z]?),?$")   # "25–" before " 27"
RANGE_SPAN = 8               # "18–24" also holds 20 and 22; a wider range ("46–108") only its ends
RANGE = re.compile(r"^(\d+)[–-](\d+)$")
# A street renamed since its plaque went up: {the name on the plaque (folded): the name today (folded)}. Only a
# rename the City records belongs here; none of the current list's unplaced plaques needs one (checked 2026-10-18).
RENAMED: dict[str, str] = {}
ABBREV = ((re.compile(r"g\.?$"), "gatan"), (re.compile(r"gata$"), "gatan"), (re.compile(r"v\.$"), "vägen"))
SIDES = (("Stora", "St.", "Sta"), ("Lilla", "L.", "Lla"), ("Sankt", "S:t", "St.", "St"))


def parse_list(text: str) -> list[dict]:
    """{n, id, head, missing, year, bridge} per plaque row, in list order. Headings, column titles and page titles
    are skipped; a row under the "Broskyltar" heading is a bridge's plaque (bridge: True)."""
    rows, cur, bridge = [], None, False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line.casefold() == "broskyltar":
            bridge, cur = True, None
            continue
        if not line or "Populärnamn" in line:
            continue
        m = ROW.match(line)
        if m:
            cur = {"n": int(m.group(1)), "parts": [m.group(2)]}
        elif cur is not None:
            cur["parts"].append(line)
        else:
            continue
        whole = " ".join(cur["parts"])
        t = TAIL.search(whole)
        if t:
            head = whole[:t.start()]
            missing = bool(MISSING.search(head))
            head = " ".join(PAREN.sub(" ", MISSING.sub(" ", head)).split()).rstrip(" ,/")
            rows.append({"n": cur["n"], "id": int(t.group(1)), "head": head, "missing": missing,
                         "year": int(t.group(2)[:4]), "bridge": bridge})
            cur = None
    return rows


def house_numbers(tokens: list[str]) -> list[str]:
    """The numbers in "30 , 33", "18–20", "26 A", "40 A, B" (40A, 40B), "46–108, 35–201" (each end)."""
    out, base = [], ""
    for t in (t.rstrip(",").rstrip("–-") if len(t) > 1 else t for t in tokens):
        if t in ("–", "-") or not t:
            continue
        m = RANGE.match(t)
        if m and 0 < int(m.group(2)) - int(m.group(1)) <= RANGE_SPAN and (int(m.group(2)) - int(m.group(1))) % 2 == 0:
            out += [str(k) for k in range(int(m.group(1)), int(m.group(2)) + 1, 2)]
            base = m.group(2)
            continue
        if len(t) == 1 and t.isalpha():
            if out and out[-1] == base:
                out[-1] = base + t.upper()
            elif base:
                out.append(base + t.upper())
            continue
        for n in numbers(t):
            out.append(n)
            base = re.match(r"\d+", n).group(0)
    return list(dict.fromkeys(out))


def street_variants(street: str) -> list[str]:
    """The folded ways the City may write a street the list writes `street`: as written, renamed (RENAMED), with
    "g."/"gata" as "gatan" and "v." as "vägen", with "St."/"L." as "Stora"/"Lilla", or with "Stora"/"Lilla" in
    front of a name written without it."""
    words = street.split()
    out = [fold(street)]
    last = words[-1]
    for pat, full in ABBREV:
        if pat.search(last) and not last.endswith("gatan"):
            out.append(fold(" ".join(words[:-1] + [pat.sub(full, last)])))
    for side in SIDES:
        if words[0] in side[1:] and len(words) > 1:
            out.append(fold(" ".join([side[0]] + words[1:])))
    if words[0] not in PREFIXES and words[0] not in {a for s in SIDES for a in s}:
        out += [fold(f"{side[0]} {v}") for side in SIDES for v in list(out)]
    out += [RENAMED[v] for v in list(out) if v in RENAMED]
    return list(dict.fromkeys(out))


def known_street(street: str, streets: set[str]) -> str | None:
    """The one folded street the City knows that `street` is (street_variants); None when none is, or more than one
    variant is (Stora and Lilla Nygatan both, for a plaque that says "Nygatan")."""
    if fold(street) in streets:
        return fold(street)
    hits = [v for v in street_variants(street) if v in streets]
    return hits[0] if len(hits) == 1 else None


def split_address(head: str, streets: set[str] | None = None) -> tuple[str, list[tuple[str, list[str]]]]:
    """(name, [(street, [numbers]), ...]): the addresses from the first "street number" that follows the name.
    `streets`: the folded street names known (s02_addresses); without them a street is a word that ends like one."""
    words = head.replace("/", " ").split()
    found, start, i = [], 0, 1          # the name takes at least one word
    while i < len(words):
        hit = None
        for k in (4, 3, 2, 1):
            if i + k >= len(words) or not words[i + k][0].isdigit() or not NUMBERISH.match(words[i + k]):
                continue
            street = " ".join(words[i:i + k]).rstrip(",")
            if (known_street(street, streets) is not None) if streets is not None else (
                    STREET_END.search(street) and (k == 1 or k == 2 and words[i] in PREFIXES)):
                hit = (k, street)
                break
        if not hit:
            i += 1
            continue
        k, street = hit
        j = i + k
        while j < len(words) and NUMBERISH.match(words[j]):
            j += 1
        start = start or i
        known = known_street(street, streets) if streets is not None else None
        found.append((street if known in (None, fold(street)) else known, house_numbers(words[i + k:j])))
        i = j
    if not found:
        return head, []
    return " ".join(words[:start]).rstrip(" ,"), found


def text_from_post(page: str) -> tuple[str, str]:
    """(title, Swedish text) on a Stockholmskällan post: the paragraphs of its post content that are neither the
    italic English summary nor a bold note (where the text comes from, the society's boilerplate)."""
    t = re.search(r'<h1 class="post-content">(.*?)</h1>', page, re.S)
    body = re.search(r'<div class="post-content section">(.*?)</div>', page, re.S)
    title = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else ""
    paras = []
    for p in re.findall(r"<p>(.*?)</p>", body.group(1) if body else "", re.S):
        s = p.strip()
        if s.startswith(("<em>", "<strong>", "<b>", "<i>")):
            continue
        s = " ".join(html.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", s))).split())
        if s:
            paras.append(s)
    return title, "\n\n".join(paras)


def clean_name(name: str, designations: set[str] = frozenset()) -> str:
    """The plaque's name without a property designation ("Elefanthuset Stamtavlan 5" -> "Elefanthuset"), with a
    leading "Kvarteret"/"kv." dropped along with it; "" when the name was only the designation."""
    out = str(name or "")
    for ph in sorted({q for q in phrases(out) if q in designations}, key=len, reverse=True):
        words = r"\s+".join(re.escape(w) for w in ph.split(" "))
        out = re.sub(rf"(?:\b(?:kvarteret|kv\.?)\s+)?\b{words}\b", " ", out, flags=re.IGNORECASE)
    return re.sub(r"^[\s,;/–-]+|[\s,;/–-]+$", "", " ".join(out.split()))


def cut(text: str, designations: set[str] = frozenset()) -> tuple[str, bool]:
    """(the text without its sentences that say who owned the building or had it built, or name a property
    designation, as wiki.cut leaves them out of an excerpt (spec §6.3); whether any was left out)."""
    paras, dropped = [], False
    for para in text.split("\n\n"):
        keep = [s.strip() for s in split_sentences(para) if s.strip()]
        ok = [s for s in keep if not owner(s) and not mentions(s, designations)]
        dropped |= len(ok) < len(keep)
        if ok:
            paras.append(" ".join(ok))
    return "\n\n".join(paras), dropped


def match_openplaques(name: str, addrs: list, op: list[dict], head: str = "") -> dict | None:
    """The Open Plaques record of a plaque: its inscription starts with the plaque's name, its address with the
    plaque's first address, or its address is in the list's row (`head`). Only geolocated ones count."""
    n, h = fold(name), f" {fold(head)} "
    first = fold(f"{addrs[0][0]} {addrs[0][1][0]}") if addrs and addrs[0][1] else None
    for p in op:
        if p.get("latitude") is None or p.get("longitude") is None:
            continue
        a = fold(p.get("address") or "")
        if ((n and fold(p.get("inscription") or "").startswith(n)) or (first and a.startswith(first))
                or (a and f" {a} " in h)):
            return p
    return None


def letter_variants(nums: list[str], have: set[str]) -> list[str]:
    """The numbers the City writes for a plaque's `nums` when it writes none of them: "50" as its "50A", "50B";
    "3A" as "3"."""
    out = []
    for n in nums:
        base = re.match(r"\d+", n).group(0)
        out += [h for h in have if re.match(r"\d+", h) and re.match(r"\d+", h).group(0) == base
                and (n == base or h == base)]
    return out


def by_address(addrs: list, table: pd.DataFrame, variants: bool = False) -> int:
    """The footprint most of a plaque's addresses sit on in s02_addresses' table (gid, street, number), ties to the
    first address; -1 when none does. With `variants`, the letter variants of the numbers instead (letter_variants),
    an address's variants counting only when they all sit on one footprint."""
    if table.empty:
        return -1
    street = table.street.map(fold)

    def vote(variants: bool) -> dict[int, int]:
        votes: dict[int, int] = {}
        for s, nums in addrs:
            on = table[street == fold(s)]
            want = letter_variants(nums, set(on.number)) if variants else nums
            gids = on[on.number.isin(want)].gid.drop_duplicates()
            if variants and len(gids) > 1:
                continue
            for g in gids:
                votes[int(g)] = votes.get(int(g), 0) + 1
        return votes

    votes = vote(variants)
    return max(votes, key=lambda g: (votes[g], -list(votes).index(g))) if votes else -1


def by_name(name: str, cards: dict[str, list[int]], streets: set[str] | None = None) -> int:
    """The footprint whose card name is the plaque's name (folded, dashes alike; "ABF–huset Sveavägen" also as
    "ABF–huset", a known street dropped off its end); -1 when no card or more than one has it."""
    words = name.replace("–", "-").split()
    tries = [" ".join(words)]
    for k in (1, 2, 3):
        if streets is not None and len(words) > k and known_street(" ".join(words[-k:]), streets):
            tries.append(" ".join(words[:-k]))
    for t in tries:
        gids = cards.get(fold(t), [])
        if gids:
            return gids[0] if len(gids) == 1 else -1
    return -1


def place(plaques: list[dict], table: pd.DataFrame, b, op: list[dict], *, streets: set[str] | None = None,
          to_xy=None, assign=None, cards: dict[str, list[int]] | None = None) -> list[dict]:
    """Each plaque with name, addresses, gid (-1 when unplaced) and how ("address", "name", "position" or ""). `b`:
    the footprints (gid, geometry); to_xy(lon, lat) -> (x, y) in EPSG:3011; assign(points, b, max_m) -> gids;
    cards: {folded card name: [gid, ...]} of the non-private buildings with a name."""
    out = []
    for p in plaques:
        name, addrs = split_address(p["head"], streets)
        if p.get("bridge"):                     # a bridge is no footprint: never the nearest house to its plaque
            out.append({**p, "name": name or p["head"], "addrs": addrs, "gid": -1, "how": ""})
            continue
        gid, how = by_address(addrs, table), "address"
        if gid < 0:
            how = ""
            hit = match_openplaques(name or p["head"], addrs, op, p["head"])
            if hit is not None:
                x, y = to_xy(np.array([hit["longitude"]]), np.array([hit["latitude"]]))
                g = int(assign(pd.DataFrame({"x": x, "y": y}), b, POSITION_M)[0])
                if g >= 0:
                    gid, how = g, "position"
        if gid < 0:                             # the variants only where the plaque's own address and position fail
            gid, how = by_address(addrs, table, variants=True), "address"
        if gid < 0 and cards:
            gid, how = by_name(name or p["head"], cards, streets), "name"
        if gid < 0:
            how = ""
        out.append({**p, "name": name or p["head"], "addrs": addrs, "gid": gid, "how": how})
    return out
