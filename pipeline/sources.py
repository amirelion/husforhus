"""The dataset register, pipeline/sources.yml, and its checks.

    uv run python -m pipeline.sources [--release] [--sources PATH]   # prints problems; exit code 1 if any
"""
import argparse
from pathlib import Path

import yaml

REQUIRED = ["id", "url", "publisher", "product", "dataset", "licence", "licence_url", "attribution", "status"]
LICENCES = {"CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "ODbL-1.0"}
# Licences that oblige an attribution line. For these, check_sources requires:
#   - `modified` is a real true/false;
#   - `attribution` contains the entry's `product` string;
#   - `attribution` contains the licence's marker (LICENCE_MARKERS);
#   - when `modified` is true, `attribution` contains "modified" or "bearbetad" (case-insensitive).
NEEDS_MODIFIED = {"CC-BY-4.0", "CC-BY-SA-4.0", "ODbL-1.0"}
LICENCE_MARKERS = {"CC-BY-4.0": "CC BY 4.0", "CC-BY-SA-4.0": "CC BY-SA 4.0", "ODbL-1.0": "ODbL"}
MODIFIED_WORDS = ("modified", "bearbetad")
STATUSES = ("confirmed", "pending-O1")
# The standard credit line: "Dataset: publisher, licence", plus PROCESSED when `modified` is true. The licence
# reads as CREDIT_LICENCES says, or as the source's own `licence_as`, which may only drop the version ("CC BY").
CREDIT_LICENCES = {"CC-BY-4.0": "CC BY 4.0", "CC-BY-SA-4.0": "CC BY-SA 4.0", "CC0-1.0": "CC0", "ODbL-1.0": "ODbL"}
PROCESSED = {"en": "processed", "sv": "bearbetad"}


def licence_names(licence: str) -> tuple[str, ...]:
    """The words a credit may name a licence by: its full name, or its name without the version ("CC BY")."""
    full = CREDIT_LICENCES.get(licence)
    if not full:
        return ()
    name, _, version = full.rpartition(" ")
    return (full, name) if name and version[:1].isdigit() else (full,)


def credit(s: dict) -> dict[str, str]:
    """The standard credit line for a source in each language: "Dataset: publisher, licence", the source's own words (credit_as) in
    the publisher's place, and ", processed" / ", bearbetad" when the map changes the data."""
    licence = s.get("licence_as") or CREDIT_LICENCES[s["licence"]]
    return {lang: f"{s['dataset']}: {(s.get('credit_as') or {}).get(lang) or s['publisher']}, {licence}"
                  + (f", {PROCESSED[lang]}" if s.get("modified") is True else "") for lang in ("en", "sv")}


def load_sources(path: Path | None = None) -> list[dict]:
    """Read the register; by default the sources.yml beside this module, whatever the working directory."""
    path = Path(__file__).with_name("sources.yml") if path is None else Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(s, dict) for s in data):
        raise ValueError(f"{path}: expected a list of sources (mappings)")
    return data


def _attribution_errors(sid: str, s: dict, licence: str) -> list[str]:
    """The attribution rules for a licence in NEEDS_MODIFIED; each failure is its own message.

    A blank or missing attribution (or product) is already reported as a missing field, so it is skipped here.
    """
    attribution = str(s.get("attribution") or "").strip()
    if not attribution:
        return []
    errors = []
    product = str(s.get("product") or "").strip()
    if product and product not in attribution:
        errors.append(f"{sid}: attribution must contain the product name '{product}'")
    marker = LICENCE_MARKERS[licence]
    if marker not in attribution:
        errors.append(f"{sid}: attribution must contain the licence marker '{marker}'")
    if s.get("modified") is True and not any(w in attribution.lower() for w in MODIFIED_WORDS):
        errors.append(f"{sid}: attribution must say 'modified' or 'bearbetad' because modified is true")
    return errors


def check_sources(sources: list[dict], *, release: bool) -> list[str]:
    """Return one error string per problem; an empty list means the register is fine."""
    errors, seen = [], set()
    for i, s in enumerate(sources):
        sid = str(s.get("id") or f"#{i}")
        if sid in seen:
            errors.append(f"{sid}: duplicate id")
        seen.add(sid)
        for field in REQUIRED:
            value = s.get(field)
            if value is None or not str(value).strip():
                errors.append(f"{sid}: missing field '{field}'")
        licence = s.get("licence")
        if licence and licence not in LICENCES:
            errors.append(f"{sid}: licence '{licence}' is not one of {', '.join(sorted(LICENCES))}")
        url = s.get("licence_url")
        if url and not str(url).startswith(("http://", "https://")):
            errors.append(f"{sid}: licence_url must start with http:// or https://")
        if licence in NEEDS_MODIFIED:
            if not isinstance(s.get("modified"), bool):
                errors.append(f"{sid}: licence {licence} needs 'modified: true' or 'modified: false'")
            errors.extend(_attribution_errors(sid, s, licence))
        status = s.get("status")
        if status and status not in STATUSES:
            errors.append(f"{sid}: status '{status}' is not one of {', '.join(STATUSES)}")
        if release and status == "pending-O1":
            errors.append(f"{sid}: status pending-O1 is not allowed in a release")
        errors.extend(_words_errors(sid, "corner", s.get("corner"), url=True))
        errors.extend(_words_errors(sid, "credit_as", s.get("credit_as"), url=False))
        if "licence_as" in s and s["licence_as"] not in licence_names(licence):
            errors.append(f"{sid}: licence_as must be one of {list(licence_names(licence))} for {licence}")
    return errors


def _words_errors(sid: str, field: str, words, *, url: bool) -> list[str]:
    """An optional {en, sv} mapping, both non-empty: the corner credit, with an optional http(s) url, and
    credit_as, the source's own words in the publisher's place."""
    if words is None:
        return []
    if not isinstance(words, dict):
        return [f"{sid}: {field} must be a mapping with en and sv"]
    errors = [f"{sid}: {field} needs its {lang} words" for lang in ("en", "sv")
              if not isinstance(words.get(lang), str) or not words[lang].strip()]
    link = words.get("url")
    if url and link is not None and not str(link).startswith(("http://", "https://")):
        errors.append(f"{sid}: {field} url must start with http:// or https://")
    extra = set(words) - ({"en", "sv", "url"} if url else {"en", "sv"})
    if extra:
        errors.append(f"{sid}: {field} has fields other than {'en, sv and url' if url else 'en and sv'}: {sorted(extra)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.sources", description=__doc__.splitlines()[0])
    ap.add_argument("--release", action="store_true", help="also fail on sources still pending the City's reply")
    ap.add_argument("--sources", type=Path, default=None, metavar="PATH",
                    help="register to check (default: the sources.yml beside this module)")
    args = ap.parse_args(argv)
    sources = load_sources(args.sources)
    errors = check_sources(sources, release=args.release)
    for e in errors:
        print(e)
    print(f"{len(sources)} sources, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
