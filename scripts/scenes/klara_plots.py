"""The Klara story's lost blocks (scenes/s12), drawn on today's plots.

The cleared blocks of lower Norrmalm (1952–1977) have no open traced outlines. Almost every building now standing in
the cleared area was built in the clearance's own years on the old blocks' land, so the story draws old Klara on those
plots: the buildings in the area (BOX, stadsdel Norrmalm) whose year falls in a phase, fused per phase into blocks of
the old height (OLD_HEIGHT_M, about five storeys), each phase gone from the beat in which it was cleared. The outlines
are today's plots, not the old ones; the rows say so (geometry_confidence low).

    uv run python scripts/scenes/klara_plots.py      # rewrites the plot rows (id kp…) of scenes/s12/ghosts.csv
"""
import csv
import io
import sys
from pathlib import Path

import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import s03_tiles  # noqa: E402

GHOSTS = ROOT / "scenes" / "s12" / "ghosts.csv"
BOX = (18.0555, 59.3300, 18.0685, 59.3360)          # lon/lat: Vasagatan to Malmskillnadsgatan, Klarabergsgatan to Kungsgatan
OLD_HEIGHT_M = 18.0
FUSE_M = 2.0                                         # neighbouring plots closer than this become one block
PHASES = [  # id, first and last year of the buildings that replaced the phase's blocks, the last beat it stands in
    ("kp1", 1952, 1958, 3, "Old Klara: the blocks cleared first, 1952–1957 (approximate: drawn on today's plots)"),
    ("kp2", 1959, 1966, 4, "Old Klara: the blocks cleared for Hötorgscity and Sergels torg, 1958–1966 (approximate: today's plots)"),
    ("kp3", 1967, 1980, 5, "Old Klara: the blocks cleared last, 1967–1977 (approximate: drawn on today's plots)"),
]


def plots() -> dict[str, shapely.MultiPolygon]:
    df = s03_tiles.load(s03_tiles.DATA)
    dist = s03_tiles.load_places(s03_tiles.DATA)["districts"].set_index("gid").district.reindex(df.gid).to_numpy()
    g = gpd.GeoDataFrame(df.assign(d=dist), geometry="geometry", crs="EPSG:3011")
    c = g.geometry.representative_point().to_crs(4326)
    inside = c.x.between(BOX[0], BOX[2]) & c.y.between(BOX[1], BOX[3]) & (g.d == "NORRMALM") & ~g.private.astype(bool)
    out = {}
    for pid, lo, hi, _, _ in PHASES:
        sel = g[inside & g.year.between(lo, hi)]
        fused = shapely.union_all(list(sel.geometry.buffer(FUSE_M))).buffer(-FUSE_M).simplify(1.0)
        polys = [p for p in getattr(fused, "geoms", [fused]) if p.area >= 50]
        out[pid] = gpd.GeoSeries(polys, crs="EPSG:3011").to_crs(4326)
    return out


def wkt(series) -> str:
    parts = []
    for p in series:
        ring = ", ".join(f"{x:.6f} {y:.6f}" for x, y in p.exterior.coords)
        parts.append(f"(({ring}))")
    return "MULTIPOLYGON (" + ", ".join(parts) + ")"


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(GHOSTS.read_text(encoding="utf-8"))))
    cols = list(rows[0].keys())
    for c in ("from_beat", "until_beat", "height_m", "geometry_basis", "geometry_confidence"):
        if c not in cols:
            cols.append(c)
    rows = [r for r in rows if not r["id"].startswith("kp")]
    shapes = plots()
    for pid, lo, hi, until, name in PHASES:
        s = shapes[pid]
        if not len(s):
            continue
        rows.append({**{c: "" for c in cols}, "id": pid, "phase": f"replaced {lo}–{hi}", "name": name,
                     "kind": "block group", "geometry": wkt(s), "from_beat": "1", "until_beat": str(until),
                     "height_m": ";".join([f"{OLD_HEIGHT_M:g}"] * len(s)),
                     "geometry_basis": f"today's footprints built {lo}–{hi} in the cleared area, fused per phase "
                                       "(scripts/scenes/klara_plots.py)",
                     "geometry_confidence": "low", "licence": "derived from © Stockholms stad (CC BY) footprints",
                     "sources": "sv Wikipedia: Norrmalmsregleringen; the map's own building years"})
        print(f"{pid}: {len(s)} blocks, years {lo}–{hi}, standing to beat {until}")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    GHOSTS.write_text(buf.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
