"""Terrain inputs (Plan 3, Task 3): the City's 2 m contour lines, and Lantmäteriet's 1 m terrain model when the owner's
login is available.

1. Contours, always (no account): members 0_line.{shp,shx,dbf,prj,cpg} of the City's Stadskarta zip (sources.yml
   city_stadskarta, the zip s00_fetch_city range-reads), 29.6 MB compressed, into data/raw/city/stadskarta/. Their
   heights are the "Höjdkurva heltäckande" labels s00_fetch_city already fetches (NamnText_point).
2. Markhöjdmodell Nedladdning (CC BY 4.0, sources.yml lm_markhojd), only when LM_USER and LM_PASSWORD are in the
   process's environment (the owner's free Geotorget account and order of the product). The step never reads a .env file
   itself: the owner hands the login to this one process with `uv run --env-file .env ...` (Plan 3, Tasks 1 and 12), so
   no other run, an agent's included, can pick it up. The STAC catalogue lists the 1 m tiles anonymously (searched
   over the municipality's box plus MARGIN_M); every tile it lists must be an https URL on lantmateriet.se or one of
   its subdomains, or the step stops before reading any, and a redirect from there is followed without the login
   (gdal_options), so the login never goes to another host. Each tile
   over the municipality is read through GDAL's /vsicurl/ with Basic auth, one request at a time (no multi-range or
   HTTP/2 multiplexing, one thread), in BLOCK_M blocks of the target grid that meet the municipality plus MARGIN_M,
   at RES metres (GDAL reads the COG's overview when it has one), and reprojected from EPSG:3006 onto a RES-metre
   EPSG:3011 grid whose pixel edges are multiples of RES in the local frame (s02_terrain's sub-samples are its
   pixels). The result, data/raw/dem/dtm5.tif (a few tens of MB), is the only copy kept; the manifest records each
   tile's id and checksum, never a credential. A run whose tiles are unchanged reads nothing.
   A tile without overviews would stream its full 1 m blocks (about 0.8 GB for the city; the step sums the COGs' own
   block sizes and prints that figure, a lower bound: the headers and any retries come on top): the step stops then,
   unless --full-res says the owner accepts it (the project's 500 MB rule).
   A refused login (401: the Geotorget order not active yet, or a wrong login), a tile that cannot be read or a
   catalogue that does not answer is a warning, never a stop: s02_terrain then builds from the cached
   data/raw/dem/dtm5.tif if there is one, else from the contours, and the later steps run. The warning never quotes
   the login.
Without credentials the step says so and succeeds: s02_terrain builds from the contours, and CI never needs a login.
Agents never run this step with credentials; the owner runs it in their own terminal (Plan 3, Task 1).
"""
import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import numpy as np
import requests

from pipeline import city
from pipeline.fetch import RAW, TIMEOUT, UA, fetch_zip_member, read_manifest, record, sha256_file
from pipeline.s00_fetch_city import STADSKARTA_URL

STADSKARTA = RAW / "city" / "stadskarta"
STADSDEL = RAW / "city" / "stadsdelar" / "Stadsdel.shp"
CONTOUR_PREFIX = "Stockholm_Utskr-Stadskarta-Standard_shp/"
CONTOUR_MEMBERS = ["0_line.shp", "0_line.shx", "0_line.dbf", "0_line.prj", "0_line.cpg"]
STAC_SEARCH = "https://api.lantmateriet.se/stac-hojd/v1/search"
COLLECTION = "dtm-cog"
DTM = RAW / "dem" / "dtm5.tif"
RES = 5.0            # metres; s02_terrain's sub-samples (city.TERRAIN cell / sub)
MARGIN_M = 500.0     # read this much beyond the municipality, for the edge cells and the shore rings
BLOCK_M = 1000.0     # the target grid is read in blocks of this size; only blocks that meet the municipality + MARGIN_M
PAD_PX = 2           # each block's source window reaches this many RES pixels further, for the bilinear at its edge


class NoOverviews(Exception):
    """Tiles without internal overviews: reading them at RES would stream their full 1 m blocks (at least `bytes`:
    the blocks' own sizes, with the headers and any retries on top)."""

    def __init__(self, ids, nbytes):
        super().__init__(", ".join(ids))
        self.ids, self.bytes = list(ids), int(nbytes)


def credentials(env: dict | None = None) -> tuple[str, str] | None:
    """(user, password) from LM_USER/LM_PASSWORD in the process's environment; None when either is missing. Never a
    file: the owner's `uv run --env-file` puts the login in this one process (Plan 3, Task 1)."""
    env = os.environ if env is None else env
    user, password = env.get("LM_USER"), env.get("LM_PASSWORD")
    return (user, password) if user and password else None


def gdal_options(user: str, password: str) -> dict:
    """GDAL settings for authenticated range reads of the COGs, one request at a time (no multi-range requests, no
    HTTP/2 multiplexing, one thread). The login goes to Lantmäteriet's host alone: GDAL would otherwise remember a 302
    to an S3-style presigned URL (X-Amz-* parameters) and send the next range reads straight there with the login
    (CPL_VSIL_CURL_USE_S3_REDIRECT=NO keeps every read on the tile's own URL, and libcurl drops the login when it
    follows a redirect to another host). It is never printed: GDAL reads an option nobody set from the environment,
    so curl's and GDAL's debug output (CPL_CURL_VERBOSE, CPL_DEBUG, which print the Basic header) are pinned off,
    and so is GDAL_HTTP_UNSAFESSL (certificates are always checked)."""
    return {"GDAL_HTTP_AUTH": "BASIC", "GDAL_HTTP_USERPWD": f"{user}:{password}",
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
            "GDAL_HTTP_MULTIRANGE": "SERIAL", "GDAL_HTTP_MULTIPLEX": "NO", "GDAL_NUM_THREADS": "1",
            "GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_RETRY_DELAY": "2", "VSI_CACHE": "TRUE",
            "GDAL_HTTP_USERAGENT": UA["User-Agent"], "CPL_VSIL_CURL_USE_S3_REDIRECT": "NO",
            "CPL_CURL_VERBOSE": "NO", "CPL_DEBUG": "OFF", "GDAL_HTTP_UNSAFESSL": "NO"}


def lantmateriet_url(href) -> bool:
    """True for an https URL on lantmateriet.se or one of its subdomains, with no login, port, whitespace or backslash
    in it: the only kind of URL the login is ever sent to."""
    if not isinstance(href, str) or any(ch.isspace() or ch == "\\" for ch in href):
        return False
    parts = urlsplit(href)
    host = parts.hostname or ""
    return (parts.scheme == "https" and parts.netloc.lower() == host
            and (host == "lantmateriet.se" or host.endswith(".lantmateriet.se")))


def fetch_contours(dest: Path = STADSKARTA) -> list[dict]:
    """The contour members, one request at a time; each is skipped when its manifest entry still matches."""
    return [fetch_zip_member(STADSKARTA_URL, CONTOUR_PREFIX + m, dest / m) for m in CONTOUR_MEMBERS]


def municipality(stadsdel: Path = STADSDEL):
    """The municipality (the union of its stadsdelar) in EPSG:3011."""
    import geopandas as gpd
    import shapely
    return shapely.union_all(gpd.read_file(stadsdel).to_crs(city.CRS).geometry.values)


def target_grid(bounds3011, res: float = RES, margin: float = MARGIN_M):
    """(transform, width, height) of the EPSG:3011 grid: the box plus margin, pixel edges on multiples of res in the
    local frame (x = E - E0, z = N0 - N)."""
    from rasterio.transform import Affine
    e0, n0 = city.ORIGIN
    minx, miny, maxx, maxy = bounds3011
    x_lo = np.floor((minx - margin - e0) / res) * res
    x_hi = np.ceil((maxx + margin - e0) / res) * res
    z_lo = np.floor((n0 - (maxy + margin)) / res) * res
    z_hi = np.ceil((n0 - (miny - margin)) / res) * res
    return Affine(res, 0, e0 + x_lo, 0, -res, n0 - z_lo), int(round((x_hi - x_lo) / res)), int(round((z_hi - z_lo) / res))


def stac_items(bounds3011, get=requests.get) -> list[dict]:
    """The dtm-cog tiles whose EPSG:3006 box meets the municipality's box plus MARGIN_M: [{id, href, checksum}],
    sorted by id. The search is anonymous, over that same box; only the tiles' data needs the login, so a listed tile
    anywhere but on Lantmäteriet's https hosts stops the step before any tile is read."""
    from pyproj import Transformer
    minx, miny, maxx, maxy = bounds3011
    ex, ey = Transformer.from_crs(city.CRS, 3006, always_xy=True).transform([minx, maxx, minx, maxx],
                                                                            [miny, miny, maxy, maxy])
    lo_x, lo_y, hi_x, hi_y = min(ex) - MARGIN_M, min(ey) - MARGIN_M, max(ex) + MARGIN_M, max(ey) + MARGIN_M
    lon0, lat0, lon1, lat1 = Transformer.from_crs(3006, 4326, always_xy=True).transform_bounds(
        lo_x, lo_y, hi_x, hi_y, densify_pts=21)
    r = get(STAC_SEARCH, params={"collections": COLLECTION, "limit": 100,
                                 "bbox": f"{lon0:.6f},{lat0:.6f},{lon1:.6f},{lat1:.6f}"},
            headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if any(link.get("rel") == "next" for link in body.get("links", [])):
        raise SystemExit("STAC search returned more than one page; raise the limit")
    items = []
    for f in body.get("features", []):
        a = f["assets"]["data"]
        if not lantmateriet_url(a["href"]):
            raise SystemExit(f"STAC item {f.get('id')} lists {a['href']!r}, outside Lantmäteriet's https hosts: the "
                             "login is never sent there, so no tile is read")
        bx0, by0, bx1, by1 = a["proj:bbox"]
        if bx0 < hi_x and bx1 > lo_x and by0 < hi_y and by1 > lo_y:
            items.append({"id": f["id"], "href": a["href"], "checksum": a.get("file:checksum")})
    return sorted(items, key=lambda i: i["id"])


def blocks(transform, width: int, height: int, area=None, res: float = RES, block_m: float = BLOCK_M) -> list:
    """(row, col, rows, cols) of the target grid's BLOCK_M blocks that meet `area` (EPSG:3011; None: every block)."""
    import shapely
    step = int(round(block_m / res))
    out = []
    for r in range(0, height, step):
        for c in range(0, width, step):
            rows, cols = min(step, height - r), min(step, width - c)
            x0, y1 = transform @ (c, r)
            box = shapely.box(x0, y1 - rows * res, x0 + cols * res, y1)
            if area is None or shapely.intersects(area, box):
                out.append((r, c, rows, cols))
    return out


def source_window(src, transform, block, res: float = RES):
    """The window of `src` (EPSG:3006) under one target block, PAD_PX pixels wider; None when they do not meet, or
    meet by less than half a source pixel (the rounded window would be empty)."""
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    r, c, rows, cols = block
    x0, y1 = transform @ (c, r)
    pad = PAD_PX * res
    want = transform_bounds(city.CRS, 3006, x0 - pad, y1 - rows * res - pad, x0 + cols * res + pad, y1 + pad,
                            densify_pts=21)
    b = src.bounds
    lo_x, lo_y, hi_x, hi_y = max(want[0], b.left), max(want[1], b.bottom), min(want[2], b.right), min(want[3], b.top)
    if lo_x >= hi_x or lo_y >= hi_y:
        return None
    win = from_bounds(lo_x, lo_y, hi_x, hi_y, src.transform).round_offsets().round_lengths()
    if win.width < 1 or win.height < 1:
        return None
    return win


def window_bytes(src, wins) -> int:
    """The bytes the full-resolution COG blocks under these windows hold (the TIFF's own block sizes), each block
    counted once: at least what a read without overviews would stream (the headers and any retries come on top)."""
    bh, bw = src.block_shapes[0]
    seen = set()
    for w in wins:
        for by in range(int(w.row_off) // bh, (int(w.row_off) + int(w.height) - 1) // bh + 1):
            for bx in range(int(w.col_off) // bw, (int(w.col_off) + int(w.width) - 1) // bw + 1):
                seen.add((bx, by))
    return sum(int(src.get_tag_item(f"BLOCK_SIZE_{bx}_{by}", "TIFF", bidx=1) or 0) for bx, by in seen)


def read_dtm(items, bounds3011, *, area=None, open_path=lambda href: "/vsicurl/" + href, options=None,
             full_res=False, res: float = RES, log=print):
    """(array float32 (h, w) with NaN outside the data, transform, overviews) on target_grid(bounds3011), read only
    in the blocks that meet `area`. Tiles without overviews raise NoOverviews (with at least the bytes they would
    stream) unless full_res; with it, that lower bound is printed before streaming."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    transform, width, height = target_grid(bounds3011, res)
    dst = np.full((height, width), np.nan, dtype=np.float32)
    todo = blocks(transform, width, height, area, res)
    with rasterio.Env(**(options or {})):
        bare, nbytes = [], 0      # first the headers: which tiles lack overviews, and what reading them would cost
        for it in items:
            with rasterio.open(open_path(it["href"])) as src:
                if not src.overviews(1):
                    bare.append(it["id"])
                    nbytes += window_bytes(src, [w for w in (source_window(src, transform, b, res) for b in todo) if w])
        if bare and not full_res:
            raise NoOverviews(bare, nbytes)
        if bare:
            log(f"terrain model: {len(bare)} tiles without overviews: streaming at least {nbytes / 1e9:.2f} GB at full "
                "resolution")
        for it in items:
            with rasterio.open(open_path(it["href"])) as src:
                for block in todo:
                    win = source_window(src, transform, block, res)
                    if win is None:
                        continue
                    r, c, rows, cols = block
                    out_h = max(1, int(round(win.height * abs(src.transform.e) / res)))
                    out_w = max(1, int(round(win.width * src.transform.a / res)))
                    data = src.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.average,
                                    masked=True).astype(np.float32).filled(np.nan)
                    wt = src.window_transform(win) @ rasterio.Affine.scale(win.width / out_w, win.height / out_h)
                    part = dst[r:r + rows, c:c + cols].copy()
                    reproject(data, part, src_transform=wt, src_crs="EPSG:3006",
                              dst_transform=transform @ rasterio.Affine.translation(c, r), dst_crs=f"EPSG:{city.CRS}",
                              src_nodata=np.nan, dst_nodata=np.nan, init_dest_nodata=False,
                              resampling=Resampling.bilinear)
                    dst[r:r + rows, c:c + cols] = part
    return dst, transform, not bare


def write_dtm(path: Path, arr: np.ndarray, transform) -> None:
    import rasterio
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with rasterio.open(tmp, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                       crs=f"EPSG:{city.CRS}", transform=transform, nodata=np.nan, compress="deflate", predictor=3,
                       tiled=True, blockxsize=512, blockysize=512) as dst:
        dst.write(arr, 1)
    os.replace(tmp, path)


def unchanged(items, dest: Path = DTM) -> bool:
    """True when dest exists, matches its manifest entry and was read from these very tiles (ids and checksums)."""
    old = read_manifest().get(dest.relative_to(RAW).as_posix()) if dest.is_relative_to(RAW) else None
    if not old or not dest.exists() or sha256_file(dest) != old.get("sha256"):
        return False
    return [(i["id"], i["checksum"]) for i in old.get("items", [])] == [(i["id"], i["checksum"]) for i in items]


def fetch_dtm(creds, *, full_res=False, get=requests.get, open_path=lambda href: "/vsicurl/" + href,
              dest: Path = DTM) -> dict | None:
    area = municipality()
    bounds = tuple(float(v) for v in area.bounds)
    items = stac_items(bounds, get=get)
    if not items:
        raise SystemExit("the STAC search found no terrain tile over the municipality")
    if unchanged(items, dest):
        print(f"terrain model: {dest} is up to date ({len(items)} tiles)")
        return None
    arr, transform, overviews = read_dtm(items, bounds, area=area.buffer(MARGIN_M), open_path=open_path,
                                         options=gdal_options(*creds), full_res=full_res)
    write_dtm(dest, arr, transform)
    entry = {"url": STAC_SEARCH, "product": "Markhöjdmodell Nedladdning", "res": RES, "overviews": overviews,
             "items": items, "sha256": sha256_file(dest), "bytes": dest.stat().st_size, "etag": None,
             "last_modified": None}
    record(dest, entry)
    print(f"terrain model: {len(items)} tiles read at {RES:g} m{'' if overviews else ' (full resolution)'}, "
          f"{np.isfinite(arr).mean():.0%} of the grid covered -> {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return entry


UNAUTHORIZED = "401: the Geotorget order isn't active yet or the login is wrong"


def not_fetched(e: BaseException, creds) -> str:
    """Why the model was not fetched, on one line, for the warning: a 401 in words, else the error's own text with the
    login masked wherever GDAL or requests quoted it (as typed or percent-encoded)."""
    chain, x = [], e
    while x is not None and len(chain) < 5:          # rasterio chains GDAL's own error (CPLE_HttpResponseError)
        chain.append(x)
        x = x.__cause__ or x.__context__
    for x in chain:
        if getattr(getattr(x, "response", None), "status_code", None) == 401 or re.search(
                r"HTTP response code: ?401\b", str(x)):
            return UNAUTHORIZED
    text = " ".join(str(e).split()) or type(e).__name__
    for secret in sorted({s for c in creds if c for s in (c, quote(c, safe=""))}, key=len, reverse=True):
        text = text.replace(secret, "***")
    return text[:300]


def main(argv: list[str] | None = None) -> None:
    from rasterio.errors import RasterioIOError
    ap = argparse.ArgumentParser(prog="s00_fetch_dem", description=__doc__.splitlines()[0])
    ap.add_argument("--full-res", action="store_true",
                    help="read full-resolution blocks if a tile has no overviews (streams at least about 0.8 GB; the "
                         "figure is printed first)")
    args = ap.parse_args([] if argv is None else argv)
    for e in fetch_contours():
        print(f"contours: {e['member'].rsplit('/', 1)[-1]} {e['bytes']:,} bytes")
    creds = credentials()
    if creds is None:
        if DTM.exists():
            print(f"terrain model: no LM_USER/LM_PASSWORD, so the cached {DTM} stays, unchecked (s02_terrain uses it)")
        else:
            print("terrain model: no LM_USER/LM_PASSWORD in the environment, so s02_terrain builds the terrain from "
                  "the City's contour lines")
        return
    try:
        fetch_dtm(creds, full_res=args.full_res)
    except NoOverviews as e:
        raise SystemExit(f"terrain tiles {e} have no overviews: a full-resolution read streams at least "
                         f"{e.bytes / 1e9:.2f} GB (the tiles' own block sizes). Run again with --full-res to accept "
                         "that.") from None
    except (RasterioIOError, requests.RequestException) as e:
        # a refused login or a catalogue that does not answer stops no later step: the build goes on with what it has
        fallback = f"the cached {DTM}" if DTM.exists() else "the contours"
        print(f"warning: terrain model not fetched ({not_fetched(e, creds)}); s02_terrain uses {fallback}",
              file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
