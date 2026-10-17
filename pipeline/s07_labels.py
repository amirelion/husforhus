"""Street and water names from the Stadskarta, placed for the viewer (labels.json).

Replaces upstream reference/amsterdam/pipeline/s07_labels.py (alexbarakov/amsterdam-by-building, MIT), which cut
street polygons into pieces. The output format and conventions are upstream's:
  [{name, water, tier, pts: [[x, z, angleDeg, len, width]]}]
x, z in local metres (x east, z south). angleDeg is measured from +x towards +z and kept upright in [-90, 90)
(app.js: "ang is measured towards +z, Y turns towards -z"). len is the length of the stretch the name may
cover, width the street's width; both in metres.

Sources (spec §3.2):
- TextKurvad_line, GRUPP 'Gatunamn' only (its few water names are garbled): the curved text baseline.
  Centre = midpoint lifted BASELINE_UP × size off the baseline; angle = tangent at the midpoint; len = chord.
- NamnText_point, GRUPP 'Gatunamn', 'Sjö', 'Vattendrag': a straight text anchor. TEXT_ANGLE is degrees
  counter-clockwise from east on the map (checked against Vaegutbredning_area road polygons: median
  difference 0.2°, 88% within 10°). TEXTJUST is MicroStation's code (j // 6: left/centre/right,
  j % 6: top/centre/bottom); the anchor is moved to the text centre. len = K_TEXT × TEXT_SIZE × characters.
- Width: 2 × area / perimeter of the Vaegutbredning_area polygon under the centre, else a per-tier default.
- Saltsjön appears in neither file, so it is hand-placed from city.SALTSJON.
Every name in city.TIER1 must end up with a placement, or the step fails.
"""
import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

from . import city, io
from .s03_tiles import out_dir
from .s04_base import boundary

RAW = Path("data/raw/city/stadskarta")
STREET_GROUPS = ("Gatunamn",)
WATER_GROUPS = ("Sjö", "Vattendrag")
K_TEXT = 1.2          # m of label per character per m of TEXT_SIZE: median arc / (size × characters) of TextKurvad
BASELINE_UP = 0.3     # the text centre sits this many text sizes above its baseline
SIZE_BY_KOMPONENT = {"tSGenomfart": 11.0, "tSGata": 9.28, "tSGränd": 7.95}  # median NamnText TEXT_SIZE
DEFAULT_SIZE = 7.95
WATER_SIZE = 23.0     # TEXT_SIZE of the large water names (Riddarfjärden, Strömmen, Årstaviken …)
WIDTH = {1: 24.0, 2: 12.0}
WATER_WIDTH = 80.0
MIN_SEP = 350.0       # m between placements of one name
SALTSJON = "Saltsjön"


def upright(deg: float) -> float:
    """Fold an angle into [-90, 90) so the text never reads upside down."""
    return (deg + 90.0) % 180.0 - 90.0


def map_angle_to_local(deg_ccw_from_east: float) -> float:
    """Map angles count counter-clockwise from east with north up; local z points south."""
    return upright(-deg_ccw_from_east)


def line_placement(line, size: float) -> tuple[float, float, float, float]:
    """(E, N, local angle, chord) for a curved text baseline."""
    length = line.length
    a = line.interpolate(max(length / 2 - 2.0, 0.0))
    b = line.interpolate(min(length / 2 + 2.0, length))
    dx, dy = b.x - a.x, b.y - a.y
    norm = math.hypot(dx, dy) or 1.0
    m = line.interpolate(0.5, normalized=True)
    e = m.x - dy / norm * size * BASELINE_UP
    n = m.y + dx / norm * size * BASELINE_UP
    chord = shapely.distance(shapely.get_point(line, 0), shapely.get_point(line, -1))
    return e, n, map_angle_to_local(math.degrees(math.atan2(dy, dx))), float(chord)


def point_placement(e, n, angle, size, text, just) -> tuple[float, float, float, float]:
    """(E, N, local angle, len) for a straight text anchor, moved from its justification point to the centre."""
    length = K_TEXT * size * len(text)
    th = math.radians(angle)
    fx, fy = 0.0, 0.0  # unknown justification: treat the anchor as the centre
    if just is not None and not math.isnan(just):
        fx = (0.5, 0.0, -0.5)[min(int(just) // 6, 2)]
        fy = {0: -0.5, 1: 0.0, 2: BASELINE_UP}.get(int(just) % 6, 0.0)
    ce = e + math.cos(th) * length * fx - math.sin(th) * size * fy
    cn = n + math.sin(th) * length * fx + math.cos(th) * size * fy
    return ce, cn, map_angle_to_local(angle), length


def road_width(e: np.ndarray, n: np.ndarray, roads) -> np.ndarray:
    """2 × area / perimeter of the road polygon under each point; NaN where there is none."""
    w = np.full(len(e), np.nan)
    if len(e) == 0 or len(roads) == 0:
        return w
    roads = np.asarray(roads)
    tree = shapely.STRtree(roads)
    pi, ri = tree.query(shapely.points(e, n), predicate="within")
    w[pi] = 2.0 * shapely.area(roads[ri]) / shapely.length(roads[ri])
    return w


def placements(kurvad: gpd.GeoDataFrame, namn: gpd.GeoDataFrame, roads, area) -> list[dict]:
    """One dict per candidate placement: name, water, e, n, ang, len, width (NaN if unknown)."""
    out = []
    k = kurvad[kurvad.GRUPP.isin(STREET_GROUPS) & kurvad.NAMN.notna()]
    for r in k.itertuples():
        size = SIZE_BY_KOMPONENT.get(r.KOMPONENT, DEFAULT_SIZE)
        e, n, ang, length = line_placement(r.geometry, size)
        out.append({"name": r.NAMN, "water": False, "e": e, "n": n, "ang": ang, "len": length})
    p = namn[namn.GRUPP.isin(STREET_GROUPS + WATER_GROUPS) & namn.NAMN.notna()]
    for r in p.itertuples():
        text = r.TEXT if isinstance(r.TEXT, str) and r.TEXT else r.NAMN
        e, n, ang, length = point_placement(r.geometry.x, r.geometry.y, r.TEXT_ANGLE, r.TEXT_SIZE, text,
                                            r.TEXTJUST)
        out.append({"name": r.NAMN, "water": r.GRUPP in WATER_GROUPS, "e": e, "n": n, "ang": ang, "len": length})
    if area is not None:
        inside = shapely.contains_xy(area, [o["e"] for o in out], [o["n"] for o in out])
        out = [o for o, ok in zip(out, inside, strict=True) if ok]
    widths = road_width(np.array([o["e"] for o in out]), np.array([o["n"] for o in out]), roads)
    for o, w in zip(out, widths, strict=True):
        o["width"] = float("nan") if o["water"] else float(w)
    return out


def hand_placed() -> dict:
    x, z, ang = city.SALTSJON
    e, n = city.ORIGIN[0] + x, city.ORIGIN[1] - z
    return {"name": SALTSJON, "water": True, "e": e, "n": n, "ang": upright(ang),
            "len": K_TEXT * WATER_SIZE * len(SALTSJON), "width": WATER_WIDTH}


def merge(cands: list[dict], tier1) -> list[dict]:
    """One entry per name (water wins over a street of the same name); placements at least MIN_SEP apart,
    longest first. Sorted by name for stable output."""
    tier1 = set(tier1)
    by_name: dict[str, dict] = {}
    for c in sorted(cands, key=lambda c: (not c["water"], c["name"])):
        entry = by_name.setdefault(c["name"], {"name": c["name"], "water": c["water"],
                                               "tier": 1 if c["name"] in tier1 else 2, "cands": []})
        entry["cands"].append(c)
    labels = []
    for name in sorted(by_name):
        entry = by_name[name]
        kept = []
        for c in sorted(entry["cands"], key=lambda c: (-c["len"], c["e"], c["n"])):
            if all((c["e"] - q["e"]) ** 2 + (c["n"] - q["n"]) ** 2 >= MIN_SEP ** 2 for q in kept):
                kept.append(c)
        pts = []
        for c in kept:
            x, z = city.to_local(c["e"], c["n"])
            width = c["width"]
            if not np.isfinite(width):
                width = WATER_WIDTH if entry["water"] else WIDTH[entry["tier"]]
            pts.append([round(float(x), 1) + 0.0, round(float(z), 1) + 0.0, round(c["ang"], 1) + 0.0,
                        round(c["len"]), round(float(width), 1)])  # + 0.0 turns -0.0 into 0.0
        labels.append({"name": name, "water": entry["water"], "tier": entry["tier"], "pts": pts})
    return labels


def check_tier1(labels: list[dict], tier1) -> None:
    placed = {lab["name"] for lab in labels if lab["pts"]}
    missing = sorted(set(tier1) - placed)
    if missing:
        raise SystemExit(f"tier-1 names without a placement: {', '.join(missing)} "
                         f"(fix the name in city.TIER1 or hand-place it)")


def build(kurvad, namn, roads, area, tier1) -> list[dict]:
    labels = merge(placements(kurvad, namn, roads, area) + [hand_placed()], tier1)
    check_tier1(labels, tier1)
    return labels


def read(name: str, raw: Path = RAW) -> gpd.GeoDataFrame:
    d = gpd.read_file(raw / f"{name}.shp")
    return d.set_crs(city.CRS, allow_override=True) if d.crs is None else d.to_crs(city.CRS)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s07_labels", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="output version (default: the one in web/data/current.json)")
    args = ap.parse_args(argv)
    out = out_dir(args.version)
    roads = shapely.make_valid(read("Vaegutbredning_area").geometry.values)
    labels = build(read("TextKurvad_line"), read("NamnText_point"), roads, boundary(), city.TIER1)
    size = io.write_json(out / "labels.json", labels)
    print(f"{len(labels)} names, {sum(len(lab['pts']) for lab in labels)} placements, "
          f"{sum(lab['tier'] == 1 for lab in labels)} tier 1; {size / 1024:.0f} KB → {out / 'labels.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
