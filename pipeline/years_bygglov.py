"""Stockholm City Archives' building-permit cards as a year source (the `bygglov` tier): one year per property, on
the property's one main building, and only in the kinds of building where it measured right.

The cards come from s00_fetch_bygglov's harvest of the search app "Bygglov 1875–1980" (data/raw/bygglov/pages/).
Nothing here sends a request. The settings are city.BYGGLOV.

- cards(): the harvest as one table, data/bygglov/cards.parquet (git-ignored with the rest of data/): id, kvarter,
  nr, dnr, year, akt and page, as the archive wrote them. It is built from the saved pages once the harvest is
  complete (s00_fetch_bygglov has written its MANIFEST.json), and built again when that manifest's fingerprint of the
  cards changes. None while there is no complete harvest.
- keys(): one row per card and property it names, with the designation key (the kvarter folded by bygglov.fold, its
  parish parenthesis dropped, then a number from bygglov.numbers, so "1,3" names two properties), the closing year,
  the opening year and the case number's office. A card names no property, and says why (reason), when it is an old
  stadsäga card ("Stg" as a word of its own), has no kvarter, its number names no whole property, or its kvarter
  name is one the index writes for two blocks: two parishes' "Provgården (He)" and "Provgården (Kf)", or "Testbacken"
  beside "Testbacken (Kf)". Matching is exact equality of the keys; the app's substring search never enters.
- properties(): one row per designation, with the year by year_rule "earliest_close": the earliest closing year
  among its cards that have one in min_year..max_year (the others count as undated; with undated "skip" a property
  that has an undated card gets nothing). year_from is the first card's opening year when it is at most max_lag
  years earlier, else the closing year. episodes is 1, or 2 when a card closes more than episode_years after the
  first (a later alteration, or a house that replaced the first one); gap is the years from the first card to the
  second episode's first.
- footprints(): the footprint rules, with a reason for every building that cannot get a year, the first that applies
  of: a takedown, no designation, a joint property (our "S:51"), not a main building (not_main: outbuildings,
  garages, sheds, substations; an allotment cottage is a main building), a property with two or more main
  buildings, an estate (more than max_footprints footprints), Gamla stan and Riddarholmen (skip_stadsdelar), first
  digitised in late_prod_year or later, a property unit formed late (fnr above late_unit_fnr). Size never picks a
  footprint.
- match(): the property's year on each eligible footprint, and a reason for every other one: no_card, the
  property's own reason (undated_only, undated_card), or the block check. The block check (blocks()) compares the
  property with the rest of its block (its kvarter, or a trakt and its first number): its first card more than
  block_years from the median of the block's other properties' first cards is an old plot among newer houses (whose
  card is likely a predecessor's) or an alteration's card (block_disagrees); a block where more than block_uncarded
  of our register's properties have no card at all was rebuilt or renumbered after the index (block_uncarded).
- score(), cells(), cell_status(): the gate. A cell (CELL_KEYS: KATEGORI group, inner or outer city, the era of the
  permit year, episodes) writes years only with min_cell test buildings, min_right of them in the right period and
  min_decade in the same decade, measured against unrounded building-level record years, and only for a group in
  `groups` (houses: as for the estimate tier, the test buildings of the other groups are not like the ones the tier
  would date).
- tier(): what s02_years calls, after every building-level record: the footprint rules, the match and the gate in
  one pass, the cells measured on the footprints with an unrounded record year, and the blind spot (the footprints
  from 1981 or later by their record year that pass the footprint rules: any permit year they get is a predecessor's).
  skipped() counts why each footprint the tier may fill got none; settings(), not_run() and estimate_check() make
  accuracy.json's bygglov block (pipeline/validate_bygglov.py checks it in s99).

Tested by tests/test_years_bygglov.py (the matcher and the gate) and tests/test_s02_bygglov.py (the tier in
s02_years). The designations, case numbers, akt numbers and card ids are a join key only: they stay in data/ and in
memory, never in the web data or accuracy.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import bygglov, city
from . import estimate as est
from . import s00_fetch_bygglov as harvest

CARDS = Path("data/bygglov/cards.parquet")
CARD_COLUMNS = ["id", "kvarter", "nr", "dnr", "year", "akt", "page"]
FINGERPRINT = b"cards_sha256"          # the parquet's metadata key: the harvest manifest's fingerprint of the cards
CELL_KEYS = ("group", "inner", "era", "episodes")
# Why a footprint gets no year, in the order footprints() and match() test them.
FOOTPRINT_REASONS = ("takedown", "no_designation", "joint_property", "not_main", "several_main", "estate",
                     "skip_stadsdel", "late_prod", "late_unit")
MATCH_REASONS = ("no_card", "undated_only", "undated_card", "block_disagrees", "block_uncarded")
CARD_REASONS = ("stg", "no_kvarter", "no_number", "parish")


# ---------- the cards ----------

def cards_from_pages(folder: Path | None = None) -> pd.DataFrame:
    """Every card of the saved list pages, in id order: CARD_COLUMNS, the fields as the archive wrote them."""
    rows = []
    for p in sorted(harvest.saved_pages(folder)):
        doc = json.loads(harvest.page_path(p, folder).read_text(encoding="utf-8"))
        rows.extend((c["id"], c["kvarter"], c["nr"], c["dnr"], c["year"], c["akt"], doc["page"]) for c in doc["cards"])
    out = pd.DataFrame(rows, columns=CARD_COLUMNS)
    return out.astype({"id": "int32", "page": "int16"}).sort_values("id").reset_index(drop=True)


def cards(path: Path = CARDS, folder: Path | None = None, manifest: Path | None = None) -> pd.DataFrame | None:
    """The harvest's cards (CARD_COLUMNS); None while the harvest is not complete (no MANIFEST.json with a
    fingerprint). path is read when its stored fingerprint is the manifest's, else built from the pages and
    written."""
    manifest = harvest.MANIFEST if manifest is None else manifest
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sha = m.get("cards_sha256")
    if not sha:
        return None
    if path.exists() and (pq.read_schema(path).metadata or {}).get(FINGERPRINT) == sha.encode():
        return pd.read_parquet(path)
    out = cards_from_pages(folder)
    if len(out) != m.get("cards"):
        raise ValueError(f"the saved pages hold {len(out):,} cards and the manifest {manifest} says {m.get('cards')}: "
                         "run s00_fetch_bygglov --check")
    table = pa.Table.from_pandas(out, preserve_index=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    pq.write_table(table.replace_schema_metadata({**(table.schema.metadata or {}), FINGERPRINT: sha.encode()}), tmp)
    tmp.replace(path)
    return out


# ---------- cards to properties ----------

def keys(c: pd.DataFrame) -> pd.DataFrame:
    """One row per card and property it names: id, key (the folded designation, "" when the card names none),
    kvarter (folded, parish dropped), close (the earliest closing year the card gives, 0 for none), opened (0 for
    none), authority, akt (as a number, -1 for none) and reason ("" or one of CARD_REASONS)."""
    names = [bygglov.kvarter_name(k) for k in c.kvarter]
    kv = np.array([n for n, _ in names], dtype=object)
    parish = np.array([s for _, s in names], dtype=object)
    spellings = pd.DataFrame({"kv": kv, "parish": parish}).drop_duplicates().groupby("kv").size()
    ambiguous = set(spellings.index[spellings > 1])
    rows = []
    for i, k, nr, dnr, year, akt, kq in zip(c.id, c.kvarter, c.nr, c.dnr, c.year, c.akt, kv):
        ys = bygglov.closing_years(year)
        close = min(ys) if ys else 0
        base = (int(i), kq, close, bygglov.opened(dnr, close or None) or 0, bygglov.authority(dnr),
                int(akt) if akt.isdigit() else -1)
        nums = bygglov.numbers(nr)
        reason = ("stg" if bygglov.is_stg(k) else "no_kvarter" if not kq else "no_number" if nums is None
                  else "parish" if kq in ambiguous else "")
        if reason:
            rows.append((base[0], "", *base[1:], reason))
        else:
            rows.extend((base[0], f"{kq} {n}", *base[1:], "") for n in nums)
    return pd.DataFrame(rows, columns=["id", "key", "kvarter", "close", "opened", "authority", "akt", "reason"])


def properties(k: pd.DataFrame, p: dict | None = None) -> pd.DataFrame:
    """One row per designation key that keys() gave a card (index key): n_cards, n_dated, n_undated, year, year_from,
    close_last, episodes, gap, first_id, authority (the first card's office) and reason ("", undated_only or
    undated_card): the year rule of the module docstring."""
    p = city.BYGGLOV if p is None else p
    if p["year_rule"] != "earliest_close":
        raise ValueError(f"year_rule {p['year_rule']!r}: only 'earliest_close' is built")
    k = k[k.reason == ""]
    dated = k.close.between(p["min_year"], p["max_year"])
    lag = k.close - k.opened
    first_from = np.where(dated & (k.opened > 0) & (lag >= 0) & (lag <= p["max_lag"]), k.opened, k.close)
    d = k.assign(dated=dated, year_from=first_from)
    counts = d.groupby("key").agg(n_cards=("id", "size"), n_dated=("dated", "sum"))
    counts["n_undated"] = counts.n_cards - counts.n_dated
    dd = d[d.dated].sort_values(["key", "close", "year_from", "akt", "id"])
    first = dd.groupby("key").head(1).set_index("key")
    out = counts.join(first[["close", "year_from", "id", "authority"]].rename(
        columns={"close": "year", "id": "first_id"}))
    out["close_last"] = dd.groupby("key").close.max()
    later = dd[dd.close > dd.key.map(first.close) + p["episode_years"]]
    second = later.groupby("key").close.min()
    out["gap"] = (second - out.year).reindex(out.index)
    out["episodes"] = np.where(out.gap.notna(), 2, 1)
    out = out.fillna({"year": 0, "year_from": 0, "close_last": 0, "gap": 0, "first_id": 0, "authority": ""})
    out = out.astype({"n_cards": "int64", "n_dated": "int64", "n_undated": "int64", "year": "int64",
                      "year_from": "int64", "close_last": "int64", "gap": "int64", "first_id": "int64",
                      "episodes": "int64"})
    reason = np.where(out.n_dated == 0, "undated_only",
                      np.where((out.n_undated > 0) & (p["undated"] == "skip"), "undated_card", ""))
    out["reason"] = reason
    out.loc[out.reason != "", ["year", "year_from", "episodes", "gap"]] = 0
    return out[["n_cards", "n_dated", "n_undated", "year", "year_from", "close_last", "episodes", "gap", "first_id",
                "authority", "reason"]].sort_index()


# ---------- footprints ----------

def footprints(b: pd.DataFrame, stadsdel, exclude=frozenset(), p: dict | None = None) -> pd.DataFrame:
    """One row per building (index gid, in b's order): key ("" without one), group (city.KATEGORI_GROUPS), main,
    n_fp and n_main (footprints and main footprints on its property) and reason ("" when it may get the property's
    year, else the first of FOOTPRINT_REASONS that applies). stadsdel: the stadsdel name per building."""
    p = city.BYGGLOV if p is None else p
    folded = np.array([bygglov.fold(f) if isinstance(f, str) else "" for f in b.fastighet], dtype=object)
    key = np.array([bygglov.designation(f) or "" for f in folded], dtype=object)
    main = ~b.kategori.isin(p["not_main"]).to_numpy()
    has = key != ""
    s = pd.DataFrame({"key": key[has], "main": main[has]})
    n_fp = s.groupby("key").size()
    n_main = s.groupby("key").main.sum()
    out = pd.DataFrame({"key": key, "group": [city.KATEGORI_GROUPS.get(x, "unspecified") for x in b.kategori],
                        "main": main}, index=pd.Index(b.gid.to_numpy(), name="gid"))
    out["n_fp"] = pd.Series(key).map(n_fp).fillna(0).astype(int).to_numpy()
    out["n_main"] = pd.Series(key).map(n_main).fillna(0).astype(int).to_numpy()
    prod = b.prod_year.to_numpy() if "prod_year" in b else np.zeros(len(b), np.int64)
    fnr = b.fnr.to_numpy() if "fnr" in b else np.zeros(len(b), np.int64)
    tests = [
        ("takedown", np.isin(b.gid.to_numpy(), list(exclude))),
        ("no_designation", folded == ""),
        ("joint_property", (folded != "") & ~has),
        ("not_main", ~main),
        ("several_main", out.n_main.to_numpy() > 1),
        ("estate", out.n_fp.to_numpy() > p["max_footprints"]),
        ("skip_stadsdel", np.isin(np.asarray(stadsdel, dtype=object), list(p["skip_stadsdelar"]))),
        ("late_prod", (prod > 0) & (prod >= p["late_prod_year"])),
        ("late_unit", fnr > p["late_unit_fnr"]),
    ]
    reason = np.full(len(b), "", dtype=object)
    for name, hit in reversed(tests):           # the first test that applies wins
        reason[hit] = name
    out["reason"] = reason
    return out


def block(key: str) -> str:
    """The block a designation lies in: its kvarter ("TESTGÅRDEN 12" is in "TESTGÅRDEN"), or for a trakt number the
    trakt and its first number ("PROVBY 5:6" is in "PROVBY 5"), as estimate.kvarter_codes groups them; "" for none."""
    s = bygglov.split_designation(key) if key else None
    if not s:
        return ""
    kv, n = s
    return f"{kv} {n.split(':')[0]}" if ":" in n else kv


def blocks(fp: pd.DataFrame, props: pd.DataFrame) -> pd.DataFrame:
    """Per property with a year (index key): block_median, the median year of the other properties with a year in its
    block (NaN without one), and block_uncarded, the share of the block's properties in our register (designations
    with a main building) that no card names."""
    dated = props[(props.reason == "") & (props.year > 0)]
    b = pd.Series([block(k) for k in dated.index], index=dated.index, dtype=object)
    med = pd.Series(np.nan, index=dated.index)
    for _, keys in b.groupby(b).groups.items():
        if len(keys) > 1:
            y = dated.year[keys].to_numpy(dtype=float)
            med[keys] = [np.median(np.delete(y, i)) for i in range(len(y))]
    ours = pd.Index(fp.key[(fp.key != "") & fp.main].unique())
    carded = pd.Series(ours.isin(props.index), index=ours)
    uncarded = 1.0 - carded.groupby([block(k) for k in ours]).mean()
    return pd.DataFrame({"block_median": med, "block_uncarded": b.map(uncarded).fillna(0.0)})


def match(fp: pd.DataFrame, props: pd.DataFrame, p: dict | None = None) -> pd.DataFrame:
    """fp (footprints()) with the property's year on every eligible footprint: year, year_from, episodes, gap,
    n_cards, authority, block_median and block_uncarded (blocks()); reason "" only where a year was given, else the
    footprint's reason, no_card, the property's reason (undated_only, undated_card), or the block check's:
    block_disagrees (more than block_years from block_median) or block_uncarded (a block_uncarded share above the
    lever). A lever set to None turns its check off. The year columns are 0 (authority "") where no year was given."""
    p = city.BYGGLOV if p is None else p
    out = fp.copy()
    eligible = out.reason.to_numpy() == ""
    got = props.reindex(out.key.where(eligible, ""))
    bl = blocks(fp, props).reindex(out.key.where(eligible, ""))
    for col in ("year", "year_from", "episodes", "gap", "n_cards"):
        out[col] = got[col].fillna(0).astype(np.int64).to_numpy()
    out["authority"] = got.authority.fillna("").to_numpy()
    out["block_median"] = bl.block_median.to_numpy()
    out["block_uncarded"] = bl.block_uncarded.fillna(0.0).to_numpy()
    reason = out.reason.to_numpy().copy()
    no_card = eligible & got.n_cards.isna().to_numpy()
    prop_reason = got.reason.fillna("").to_numpy()
    reason[no_card] = "no_card"
    later = eligible & ~no_card & (prop_reason != "")
    reason[later] = prop_reason[later]
    free = reason == ""
    if p.get("block_years") is not None:
        far = free & (np.abs(out.block_median.to_numpy() - out.year.to_numpy()) > p["block_years"])
        reason[far] = "block_disagrees"
    if p.get("block_uncarded") is not None:
        reason[(reason == "") & (out.block_uncarded.to_numpy() > p["block_uncarded"])] = "block_uncarded"
    out["reason"] = reason
    off = reason != ""
    out.loc[off, ["year", "year_from", "episodes", "gap", "n_cards"]] = 0
    out.loc[off, "authority"] = ""
    return out


# ---------- the gate ----------

def era(years) -> np.ndarray:
    """The era (city.ERAS) of each year, by name."""
    return np.array([city.ERAS[i][0] for i in est.era_of(years)], dtype=object)


def score(pred, truth) -> dict:
    """est.score's numbers (median_error, right_period), and the shares in the same decade, within 1 and 3 years,
    exactly right, and more than 10 years too late or too early (the signs tell a later alteration from an earlier
    house); every share to 3 decimals."""
    pred, truth = np.asarray(pred, dtype=np.int64), np.asarray(truth, dtype=np.int64)
    d = pred - truth

    def share(m) -> float:
        return round(float(np.mean(m)), 3)

    return {**est.score(pred, truth), "same_decade": share(pred // 10 == truth // 10), "within_1": share(abs(d) <= 1),
            "within_3": share(abs(d) <= 3), "exact": share(d == 0), "late_10": share(d > 10),
            "early_10": share(d < -10)}


def cell_status(n: int, right: float, decade: float, p: dict | None = None, group: str | None = None) -> str:
    """'dated' when a cell may write years (min_cell test buildings, min_right right period, min_decade same
    decade, and a KATEGORI group in the lever `groups`), 'measured only' for a cell that passes in a group the tier
    does not date, 'not measurable' with fewer test buildings, else 'fails'."""
    p = city.BYGGLOV if p is None else p
    if n < p["min_cell"]:
        return "not measurable"
    if right < p["min_right"] or decade < p["min_decade"]:
        return "fails"
    return "dated" if group is None or group in p["groups"] else "measured only"


def cells(t: pd.DataFrame, by=CELL_KEYS, p: dict | None = None) -> list[dict]:
    """The cells of the test rows t (pred, truth and the columns `by`): per cell its key, n, score()'s numbers when
    measurable, and status (cell_status, with the cell's group when `by` has one)."""
    p = city.BYGGLOV if p is None else p
    out = []
    for key, grp in t.groupby(list(by), sort=True):
        key = key if isinstance(key, tuple) else (key,)
        cell = {k: (v.item() if hasattr(v, "item") else v) for k, v in zip(by, key)}
        cell["n"] = int(len(grp))
        if len(grp) >= p["min_cell"]:
            cell.update(score(grp.pred, grp.truth))
            cell["status"] = cell_status(len(grp), cell["right_period"], cell["same_decade"], p, cell.get("group"))
        else:
            cell["status"] = "not measurable"
        out.append(cell)
    return out


# ---------- the tier ----------

def tier(b: pd.DataFrame, props: pd.DataFrame, stadsdel, truth, exclude=frozenset(),
         p: dict | None = None) -> tuple[pd.DataFrame, list[dict], dict]:
    """The tier on buildings b (gid, kategori, fastighet and, for the guards, prod_year and fnr), in b's order:

    - per building (index gid): match()'s columns, plus inner, era (of the permit year, "" without one), cell (the
      status of the footprint's cell, "" without a year, "no test building" for a cell no test row falls in) and ok
      (a year in a cell that writes);
    - the cells (cells()), measured on the test rows: the footprints with an unrounded building-level record year
      (`truth`, 0 where none) that the rules give a permit year;
    - the checks: test (the test rows, and the shares in the cells that write) and blind_spot (the footprints from
      1981 or later by their record year that pass the footprint rules: every card predates them, so any year one
      gets is a predecessor's).

    stadsdel: the stadsdel per building, or None (all outer city, none skipped). Pure: no file is read."""
    p = city.BYGGLOV if p is None else p
    n = len(b)
    sd = np.full(n, "", dtype=object) if stadsdel is None else np.asarray(stadsdel, dtype=object)
    fp = footprints(b, sd, exclude, p)
    rules = fp.reason.to_numpy() == ""
    m = match(fp, props, p)
    year = m.year.to_numpy()
    has = m.reason.to_numpy() == ""
    m["inner"] = np.isin(sd, list(city.INNER_STADSDELAR))
    m["era"] = np.where(has, era(np.where(year > 0, year, 1000)), "")
    truth = np.asarray(truth, dtype=np.int64)
    test = has & (truth > 0)
    t = pd.DataFrame({"group": m.group.to_numpy()[test], "inner": m.inner.to_numpy()[test],
                      "era": m.era.to_numpy()[test], "episodes": m.episodes.to_numpy()[test], "pred": year[test],
                      "truth": truth[test]})
    measured = cells(t, p=p)
    status = {tuple(c[k] for k in CELL_KEYS): c["status"] for c in measured}
    m["cell"] = [status.get(key, "no test building") if h else ""
                 for key, h in zip(zip(m.group, m.inner, m.era, m.episodes), has)]
    ok = m.cell.to_numpy() == "dated"
    m["ok"] = ok
    used = test & ok
    checks = {"test": {"n": int(test.sum()), "used": int(used.sum()),
                       **(score(year[used], truth[used]) if used.any() else {})}}
    late = rules & (truth >= 1981)
    checks["blind_spot"] = {"n": int(late.sum()), "dated": int((late & ok).sum()),
                            "share": round(float((late & ok).sum() / late.sum()), 3) if late.any() else None}
    return m, measured, checks


def skipped(m: pd.DataFrame, target, written) -> dict:
    """Why a footprint the tier may fill (target) got no year, counted once each in the order the rules test them:
    the footprint's and the match's reasons, then "cell" for a year in a cell that writes nothing. With `written`
    they add up to the target footprints."""
    target, written = np.asarray(target, dtype=bool), np.asarray(written, dtype=bool)
    reason = np.where(m.reason.to_numpy() != "", m.reason.to_numpy(), "cell")[target & ~written]
    got = pd.Series(reason).value_counts()
    return {r: int(got.get(r, 0)) for r in (*FOOTPRINT_REASONS, *MATCH_REASONS, "cell")}


def settings(p: dict | None = None) -> dict:
    """The levers the accuracy page and About explain the tier with, as accuracy.json's bygglov block carries them."""
    p = city.BYGGLOV if p is None else p
    return {"min_cell": int(p["min_cell"]), "min_right": float(p["min_right"]), "min_decade": float(p["min_decade"]),
            "groups": sorted(p["groups"]), "fill_area": bool(p["fill_area"]), "trains": bool(p.get("trains", False)),
            "max_footprints": int(p["max_footprints"]), "max_year": int(p["max_year"])}


def not_run(status: str, p: dict | None = None) -> dict:
    """accuracy.json's bygglov block for a build without the tier: status "off" (city.FEATURES bygglov is off) or
    "absent" (no complete harvest in data/raw/bygglov), with the settings."""
    return {"status": status, **settings(p)}


def estimate_check(yhat, permit, min_cell: int) -> dict:
    """The estimate tier against the permit years, on the permit-dated footprints it would have estimated (s02_years
    runs it there as if they had no year, and writes nothing): n, and with min_cell or more, status "measured" and
    score()'s numbers, the rounded estimate scored against the permit year; else "not measurable"."""
    yhat, permit = np.asarray(yhat, dtype=float), np.asarray(permit, dtype=np.int64)
    out = {"n": int(len(permit)), "status": "not measurable"}
    if len(permit) >= min_cell:
        out.update(status="measured", **score(np.round(yhat).astype(np.int64), permit))
    return out
