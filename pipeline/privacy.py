"""Property designations in free text (Plan 4a, Task 6): one rule for the steps that keep them out and for s99 that checks.

A property designation (fastighetsbeteckning, LOD1 FASTIGHET) is never shipped (spec §2.2, §6.3). Plans 1–2 caught a
designation that is a whole value ("Storken 12" as a name). Wikipedia text and Commons titles quote them inside
sentences: Stockholm's articles about buildings are often named after their property ("Styckjunkaren 7 är en
kontorsfastighet …": 177 of 1,103 article titles on 2026-10-16, and 227 excerpts mention one). phrases() finds every
candidate inside a text (one to three words, the first capitalised, then a number or number:number, an optional
"kv"/"kvarteret" before), and mentions() says whether one of them, normalised as s99 compares them, is a designation
of the city's buildings.

Owners and byggherrar (spec §6.3: "no owner names … or byggherre names in web data"): Wikipedia's intros say who owns
a building or had it built ("ägs av AB Stadsholmen", "Byggherre var ingenjör Hellstrand", "built for the merchant …"):
78 of the 1,103 intros of 2026-10-16 did, once cut to an excerpt. owner() finds such a sentence by its wording, in
Swedish and English, whoever it names (a person, a firm or the state: no pattern tells a person from a firm reliably,
and the sentence is rarely what the card needs), so wiki.cut leaves it out and s99 refuses an excerpt that has one.
"""
import re

KV_RE = re.compile(r"^kv(arteret)?(\.\s*|\s+)")     # "kv ", "kv.", "kvarteret ", never the start of "kvarnen"
PHRASE = re.compile(r"(?:\b[Kk]v(?:arteret)?\.?\s*)?\b[A-ZÅÄÖÉ][\w-]*(?:\s+[\w-]+){0,2}?\s*[-–]?\s*"
                    r"\d+(?::\d+)?[a-zA-Z]?\b")
OWNER = re.compile(
    r"\b(?:byggherre\w*|beställare\w*|(?:sam|del)?äger\b(?!\s+rum)|"
    # the final review of Plan 4a: "ägare" and its forms inside a compound or in the plural ("fastighetsägarna",
    # "aktieägare", "klubbägaren", "ägarbyten"), never "vägar", "jägare" or "bägare"; the verb in any form and with a
    # prefix ("samägs", "har ägts av", "ägas av", "helägt av"), never "sägs", "motsägs", "vägde" or "ägde rum"; "i X:s
    # ägo". A compound adjective without "av" names no one ("en privatägd utställning", "ett stiftelseägt museum")
    r"\w*(?<![jv])(?<!\bb)(?:ägar\w*|ägand\w*)|"
    r"\w*(?<![jsv])(?<!\bb)(?:äg(?:s|de|des|ts|as)\b(?!\s+rum)|äg(?:d|da|t)\s+av\b)|ägt\b(?!\s+rum)|ägo\b|"
    # a family that has the use of a house; a hotel, an embassy or a shop that "disponerar" one is a tenant
    r"(?:familjen|släkten)\b[^.;!?]{0,60}?\bdisponer\w*|disponer\w*\b[^.;!?]{0,40}?\b(?:familjen|släkten)\b|"
    r"lät\s+(?:uppföra|bygga|anlägga|rita|resa)|"
    r"(?:uppförd(?:es)?|uppfört|byggd(?:es)?|byggt|ritad(?:es)?|ritat)\b[^.;!?]{0,80}?\bför\s+(?!att\b)|"
    r"såld(?:es)?\b[^.;!?]{0,40}?\btill\b|köptes\s+av|förvärvades\s+av|"
    r"built\s+for|commissioned\s+by|(?:co-?)?owned\s+by|owners?\b|bought\s+by|sold\s+to|purchased\s+by|"
    r"acquired\s+by|"
    # Task 6's review: wordings the first list missed (initials, "åt", active and past forms, words in between)
    r"(?:uppförd(?:es)?|uppfört|byggd(?:es)?|byggt|ritad(?:es)?|ritat)\b[^.;!?]{0,80}?\båt\b|"
    r"beställ(?:de|des|t|d)\b[^.;!?]{0,40}?\bav\b|på\s+uppdrag\s+av|köpte\b|"
    r"köpt(?:es)?\b[^.;!?]{0,40}?\bav\b|förvärvade\b|förvärvad(?:es)?\b[^.;!?]{0,40}?\bav\b|tillhör(?:de|t)?\b|"
    r"lät\b[^.;!?]{0,40}?\b(?:uppföra|bygga|anlägga|rita|resa)\b|"
    r"owned\b[^.;!?]{0,40}?\bby\b|owns\b|bought\b|had\b[^.;!?]{0,40}?\bbuilt\b|commissioned\b|"
    r"built\b[^.;!?]{0,60}?\bfor\b|belong(?:s|ed)?\s+to|home\s+of)", re.IGNORECASE)
# Numbers that follow a block name's first one: "Styckjunkaren 6 och 7", "5–7", "6, 7" (Task 6's review)
MORE = re.compile(r"\s*(,|och|and|&|[-–])\s*(\d+(?::\d+)?)[a-zA-Z]?\b")   # "6-8b" too (Task 13 review)
RANGE_MAX = 20                                        # "5–7" is 5, 6, 7; a longer span is read as its two ends
# Task 13 and its review: Commons titles join the number to the block name ("Bryggaren16", "Bryggaren16-18",
# "Styckjunkaren_7") or add a photo's letter after it ("Glaucus5b"); each is read as its designation
JOINED = re.compile(r"(?<=[^\W\d_])[-_]?(?=\d)")
SUFFIX = re.compile(r"(?<=\d)[a-z]$")


def normalise(s: str) -> str:
    """A property designation as compared: casefolded, without a 'kv ' prefix, single spaces."""
    s = " ".join(str(s).casefold().split())
    return KV_RE.sub("", s)


def phrases(text: str) -> list[str]:
    """Every candidate designation inside a text, normalised; each also with its first word dropped, so "Huset
    Styckjunkaren 7" still yields "styckjunkaren 7"."""
    text = " ".join(str(text or "").split())          # single spaces: PHRASE stays linear on long runs
    text = JOINED.sub(" ", text)
    out = []
    for m in PHRASE.finditer(text):
        p = SUFFIX.sub("", normalise(m.group(0)))
        found = [p]
        base, _, last = p.rpartition(" ")
        prev, pos = last, m.end()
        while base and (more := MORE.match(text, pos)):  # every number after the block name, ranges spelt out
            n = more.group(2)
            if more.group(1) in "-–" and prev.isdigit() and n.isdigit() and 0 < int(n) - int(prev) <= RANGE_MAX:
                found += [f"{base} {k}" for k in range(int(prev) + 1, int(n))]
            found.append(f"{base} {n}")
            prev, pos = n, more.end()
        for q in found:
            out.append(q)
            words = q.split(" ")
            for i in range(1, len(words) - 1):
                out.append(" ".join(words[i:]))
    return out


def mentions(text: str, designations: set[str]) -> bool:
    """True when the text names one of `designations` (normalised, as normalise() gives them)."""
    return bool(designations) and any(p in designations for p in phrases(text))


def owner(text: str) -> bool:
    """True when the text says who owns a building or had it built (OWNER's wording, any language it covers)."""
    return bool(OWNER.search(str(text or "")))
