"""s00_fetch_dem (Plan 3, Task 3): the contour members, the credentials, the STAC search and the windowed 5 m read
of Lantmäteriet's COGs. Nothing here touches the network or a real login: the COGs are local files written by the
test, and requests is faked."""
import builtins
import io
import json

import numpy as np
import pytest
import rasterio
import requests
import shapely
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from scipy import ndimage

from pipeline import city, s00_fetch_dem as dem
from pipeline.fetch import UA

E0, N0 = city.ORIGIN
USER = "user@example.org"
PASSWORD = "pw-never-printed-7Q"


def lm_href(tile):
    """A tile's data URL as Lantmäteriet's catalogue gives it."""
    return f"https://dl1.lantmateriet.se/hojd/data/grid/mhm/65_6/m{tile}.tif"


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.delenv("LM_USER", raising=False)
    monkeypatch.delenv("LM_PASSWORD", raising=False)
    return tmp_path / "data" / "raw"


def test_credentials_come_from_the_process_environment_only():
    assert dem.credentials({}) is None
    assert dem.credentials({"LM_USER": "env-user", "LM_PASSWORD": "env-pw"}) == ("env-user", "env-pw")
    assert dem.credentials({"LM_USER": "only-a-user"}) is None


def test_a_dotenv_file_in_the_working_directory_is_never_read(raw, tmp_path, monkeypatch, capsys):
    # The owner's .env sits in the checkout; an agent's run there (without --env-file) must not log in with it
    (tmp_path / ".env").write_text(f"LM_USER={USER}\nLM_PASSWORD={PASSWORD}\n")
    monkeypatch.setattr(dem, "fetch_zip_member", lambda url, member, dest, manifest=None: {"member": member, "bytes": 1})
    calls = []
    monkeypatch.setattr(dem, "fetch_dtm", lambda *a, **k: calls.append(a))
    real_open = builtins.open

    def guarded(file, *a, **k):
        # any .env, this one or the repo's own wherever the run starts: the step reads its environment, never a file
        if str(file).endswith(".env"):
            raise AssertionError(f"s00_fetch_dem opened {file}")
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded)
    monkeypatch.setattr(io, "open", guarded)      # pathlib's read_text and open go through io.open
    assert dem.credentials() is None
    dem.main([])
    assert calls == []
    out = capsys.readouterr()
    assert "no LM_USER/LM_PASSWORD in the environment" in out.out
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err


def test_gdal_options_use_basic_auth_over_range_reads_one_request_at_a_time():
    o = dem.gdal_options("u", "p")
    assert o["GDAL_HTTP_AUTH"] == "BASIC" and o["GDAL_HTTP_USERPWD"] == "u:p"
    assert o["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"
    # the final review: GDAL never sends a range read straight to an S3-style redirect target with the login
    # (PIPELINE-4 / PRIVACY-1), and the shell cannot switch on curl's or GDAL's debug output, which prints the login,
    # nor switch off the certificate checks (PRIVACY-2): each is pinned, since GDAL reads an unset option from the
    # environment
    assert o["CPL_VSIL_CURL_USE_S3_REDIRECT"] == "NO"
    assert (o["CPL_CURL_VERBOSE"], o["CPL_DEBUG"], o["GDAL_HTTP_UNSAFESSL"]) == ("NO", "OFF", "NO")
    assert o["GDAL_HTTP_USERAGENT"] == UA["User-Agent"]      # GDAL's requests name the project like the others do
    # the project's polite-download rule: no parallel ranges, no HTTP/2 multiplexing, one thread
    assert (o["GDAL_HTTP_MULTIRANGE"], o["GDAL_HTTP_MULTIPLEX"], o["GDAL_NUM_THREADS"]) == ("SERIAL", "NO", "1")


STORE = r"""
import base64, json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tile, log = open(sys.argv[1], "rb").read(), sys.argv[2]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, code, headers=(), body=b""):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(body)

    def answer(self):
        auth = self.headers.get("Authorization")
        login = base64.b64decode(auth.split()[1]).decode() if auth and auth.startswith("Basic ") else auth
        with open(log, "a") as f:
            f.write(json.dumps([self.headers.get("Host", "").split(":")[0], login]) + "\n")
        name = self.path.split("?")[0].rsplit("/", 1)[-1]
        if self.path.startswith("/lm/"):
            if not auth:
                return self.send(401, [("WWW-Authenticate", 'Basic realm="lm"')])
            signed = ("?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=TEST%2F20261016%2Feu-north-1%2Fs3%2F"
                      "aws4_request&X-Amz-Date=" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                      + "&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=00")
            return self.send(302, [("Location", f"http://localhost:{port}/store/{name}{signed}")])
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, b = rng[6:].split("-")
            b = min(int(b) if b else len(tile) - 1, len(tile) - 1)
            return self.send(206, [("Content-Range", f"bytes {a}-{b}/{len(tile)}"), ("Accept-Ranges", "bytes")],
                             tile[int(a):b + 1])
        return self.send(200, [("Accept-Ranges", "bytes")], tile)

    do_GET = do_HEAD = answer


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
print(port, flush=True)
server.serve_forever()
"""


class Store:
    """A local stand-in for Lantmäteriet's download host on 127.0.0.1 (port 0: the OS picks a free one), in its own
    process (rasterio holds the GIL while GDAL reads). /lm/<name> asks for the login (401 without it) and answers with
    a 302 to an S3-style presigned URL for the same tile on another host name, localhost, as a store behind a login
    may; /store/<name> serves the tile's byte ranges. Each request is logged as (host, login or None). The X-Amz-Date
    is now: GDAL reuses only a URL still valid."""

    def __init__(self, tile_path, log_path):
        import subprocess
        import sys
        self.log_path = log_path
        self.proc = subprocess.Popen([sys.executable, "-I", "-c", STORE, str(tile_path), str(log_path)],
                                     stdout=subprocess.PIPE, text=True)
        self.url = f"http://127.0.0.1:{int(self.proc.stdout.readline())}/lm/"

    @property
    def log(self):
        text = self.log_path.read_text() if self.log_path.exists() else ""
        return [tuple(json.loads(line)) for line in text.splitlines()]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()


def read_through(store, tmp_path):
    """read_dtm over one tile behind the store, through GDAL's /vsicurl/ (the default open_path, as the owner's run) with
    gdal_options and a made-up login. A fresh name each time: GDAL caches what it learnt about a URL per process."""
    import uuid
    href = f"{store.url}{uuid.uuid4().hex}/m657_67.tif"
    return dem.read_dtm([{"id": "657_67", "href": href}], (E0 - 300, N0 - 300, E0 + 300, N0 + 300),
                        options=dem.gdal_options(USER, PASSWORD))


def test_the_login_never_follows_a_redirect_to_another_host(tmp_path):
    # PIPELINE-4 / PRIVACY-1: GDAL caches a 302 target that carries X-Amz-* parameters and sent the following range
    # reads straight to it, with GDAL_HTTP_USERPWD attached (4 of 5 requests in the review's probe). With
    # CPL_VSIL_CURL_USE_S3_REDIRECT=NO every read goes to Lantmäteriet's host with the login, and curl follows the
    # 302 without it (libcurl drops the login on a change of host).
    with Store(write_cog(tmp_path / "t.tif", width=600, height=600), tmp_path / "requests.jsonl") as store:
        arr, _, overviews = read_through(store, tmp_path)
    assert overviews and np.isfinite(arr).any()
    hosts = {h for h, _ in store.log}
    assert hosts == {"127.0.0.1", "localhost"}                     # the redirect was taken
    assert (f"{USER}:{PASSWORD}" in {login for h, login in store.log if h == "127.0.0.1"})
    assert [login for h, login in store.log if h == "localhost" and login] == []


def test_debug_variables_in_the_shell_never_print_the_login(tmp_path, monkeypatch, capfd):
    # PRIVACY-2: GDAL reads an option nobody set from the environment. With CPL_CURL_VERBOSE=YES and CPL_DEBUG=ON
    # left in a shell profile, curl wrote "Server auth using Basic with user ..." and the Basic header to stderr.
    import base64
    monkeypatch.setenv("CPL_CURL_VERBOSE", "YES")
    monkeypatch.setenv("CPL_DEBUG", "ON")
    with Store(write_cog(tmp_path / "t.tif", width=600, height=600), tmp_path / "requests.jsonl") as store:
        arr, _, _ = read_through(store, tmp_path)
    assert np.isfinite(arr).any()
    out, err = capfd.readouterr()
    token = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    for secret in (USER, PASSWORD, token):
        assert secret not in out + err


def test_target_grid_puts_pixel_edges_on_local_multiples_of_5_m():
    tr, w, h = dem.target_grid((E0 - 1003.0, N0 - 2001.0, E0 + 997.0, N0 + 1499.0), res=5.0, margin=500.0)
    assert ((tr.c - E0) % 5, (N0 - tr.f) % 5) == (0.0, 0.0)
    assert tr.c <= E0 - 1503.0 and tr.c + w * 5 >= E0 + 1497.0 and tr.f >= N0 + 1999.0 and tr.f - h * 5 <= N0 - 2501.0


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def feature(tile, bbox3006, href):
    return {"id": tile, "assets": {"data": {"href": href, "proj:bbox": list(bbox3006), "file:checksum": "1220" + tile}}}


def test_stac_items_keep_the_tiles_over_the_municipality_and_sort_them():
    bounds = (E0 - 1000, N0 - 1000, E0 + 1000, N0 + 1000)
    to3006 = Transformer.from_crs(city.CRS, 3006, always_xy=True)
    ex, ey = to3006.transform(E0, N0)
    near = (ex - 5000, ey - 5000, ex + 5000, ey + 5000)
    far = (ex + 50_000, ey, ex + 60_000, ey + 10_000)
    seen = {}

    def get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params)
        return FakeResponse({"features": [feature("658_67", near, lm_href("658_67")),
                                          feature("700_70", far, lm_href("700_70")),
                                          feature("657_67", near, lm_href("657_67"))], "links": [{"rel": "self"}]})

    items = dem.stac_items(bounds, get=get)
    assert [i["id"] for i in items] == ["657_67", "658_67"]
    assert items[0] == {"id": "657_67", "href": lm_href("657_67"), "checksum": "1220657_67"}
    assert seen["url"] == dem.STAC_SEARCH and seen["params"]["collections"] == "dtm-cog"

    def paged(url, params=None, headers=None, timeout=None):
        return FakeResponse({"features": [], "links": [{"rel": "next", "href": "https://x/page2"}]})

    with pytest.raises(SystemExit, match="more than one page"):
        dem.stac_items(bounds, get=paged)


def test_stac_items_refuse_a_tile_anywhere_but_lantmateriets_https_hosts():
    # the login goes with every tile read: a catalogue entry pointing elsewhere stops the step before any read
    bounds = (E0 - 1000, N0 - 1000, E0 + 1000, N0 + 1000)
    ex, ey = Transformer.from_crs(city.CRS, 3006, always_xy=True).transform(E0, N0)
    near, far = (ex - 5000, ey - 5000, ex + 5000, ey + 5000), (ex + 50_000, ey, ex + 60_000, ey + 10_000)

    def catalogue(href, box=near):
        return lambda url, params=None, headers=None, timeout=None: FakeResponse(
            {"features": [feature("657_67", near, lm_href("657_67")), feature("658_67", box, href)]})

    for href in ["http://dl1.lantmateriet.se/hojd/m658_67.tif", "https://example.org/m658_67.tif",
                 "https://dl1.lantmateriet.se.example.org/m658_67.tif", "https://evillantmateriet.se/m658_67.tif",
                 "https://dl1.lantmateriet.se@example.org/m658_67.tif", "https://example.org/dl1.lantmateriet.se/x.tif",
                 "https://u:p@dl1.lantmateriet.se/m658_67.tif", "https://dl1.lantmateriet.se:8443/m658_67.tif",
                 "https://example.org\\@dl1.lantmateriet.se/m658_67.tif", "file:///tmp/m658_67.tif", "/tmp/m658_67.tif"]:
        with pytest.raises(SystemExit, match="outside Lantmäteriet"):
            dem.stac_items(bounds, get=catalogue(href))
    with pytest.raises(SystemExit, match="outside Lantmäteriet"):          # any href, even a tile it would not read
        dem.stac_items(bounds, get=catalogue("https://example.org/m700_70.tif", far))
    for href in ["https://dl1.lantmateriet.se/hojd/m658_67.tif", "https://lantmateriet.se/m658_67.tif",
                 "https://DL1.Lantmateriet.SE/hojd/m658_67.tif"]:
        assert [i["href"] for i in dem.stac_items(bounds, get=catalogue(href))] == [lm_href("657_67"), href]


def test_the_catalogue_is_asked_for_the_box_plus_the_margin():
    # the search covers what the filter keeps: the municipality's box grown by MARGIN_M
    bounds = (E0 - 1000, N0 - 1000, E0 + 1000, N0 + 1000)
    seen = {}

    def get(url, params=None, headers=None, timeout=None):
        seen.update(params)
        return FakeResponse({"features": []})

    dem.stac_items(bounds, get=get)
    lon0, lat0, lon1, lat1 = map(float, seen["bbox"].split(","))
    m = dem.MARGIN_M - 1.0
    x0, y0, x1, y1 = bounds[0] - m, bounds[1] - m, bounds[2] + m, bounds[3] + m
    t = np.linspace(0.0, 1.0, 41)
    xs = np.concatenate([x0 + (x1 - x0) * t, np.full_like(t, x1), x1 - (x1 - x0) * t, np.full_like(t, x0)])
    ys = np.concatenate([np.full_like(t, y0), y0 + (y1 - y0) * t, np.full_like(t, y1), y1 - (y1 - y0) * t])
    lon, lat = Transformer.from_crs(city.CRS, 4326, always_xy=True).transform(xs, ys)
    assert lon.min() >= lon0 and lon.max() <= lon1 and lat.min() >= lat0 and lat.max() <= lat1


def plane(e, n):
    return 12.0 + 0.01 * (e - 674_000.0) + 0.02 * (n - 6_580_000.0)


def write_cog(path, overviews=True, dx=0.0, width=1200, height=1200):
    """A 1 m float32 GeoTIFF in EPSG:3006 from 600 m north-west of the origin (shifted east by dx), holding a plane;
    with average overviews."""
    to3006 = Transformer.from_crs(city.CRS, 3006, always_xy=True)
    ex, ey = to3006.transform(E0, N0)
    left, top = np.floor(ex - 600) + dx, np.ceil(ey + 600)
    cols = np.arange(width) + 0.5
    rows = np.arange(height) + 0.5
    E, N = np.meshgrid(left + cols, top - rows)
    with rasterio.open(path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32", crs="EPSG:3006",
                       transform=Affine(1, 0, left, 0, -1, top), nodata=-9999, tiled=True, blockxsize=256,
                       blockysize=256) as dst:
        dst.write(plane(E, N).astype("float32"), 1)
        if overviews:
            dst.build_overviews([2, 4, 8], Resampling.average)
    return path


def model_error(arr, tr, inner):
    """|arr - the plane| at the pixels `inner`, the plane evaluated at each pixel's centre in EPSG:3006."""
    rows, cols = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    e, n = tr.c + (cols + 0.5) * 5, tr.f - (rows + 0.5) * 5
    ex, ey = Transformer.from_crs(city.CRS, 3006, always_xy=True).transform(e, n)
    return np.abs(arr[inner] - plane(ex[inner], ey[inner]))


def test_read_dtm_reprojects_a_window_at_5_m_onto_the_local_grid(tmp_path):
    cog = write_cog(tmp_path / "m657_67.tif")
    bounds = (E0 - 300, N0 - 300, E0 + 300, N0 + 300)
    arr, tr, overviews = dem.read_dtm([{"id": "657_67", "href": str(cog)}], bounds, open_path=lambda h: h)
    assert overviews and tr.a == 5.0 and (tr.c - E0) % 5 == 0
    inner = ndimage.binary_erosion(np.isfinite(arr), iterations=2)   # away from the tile's edge
    assert inner.sum() > 0.5 * arr.size
    # GDAL reads the 4 m overview and averages it to 5 m: a centimetre at most on a 2% slope
    assert model_error(arr, tr, inner).max() < 0.02


def test_read_dtm_reads_only_the_blocks_that_meet_the_area(tmp_path):
    cog = write_cog(tmp_path / "m657_67.tif")
    bounds = (E0 - 300, N0 - 300, E0 + 300, N0 + 300)
    corner = shapely.box(E0 - 800, N0 + 400, E0 - 700, N0 + 500)     # the grid's north-west 1 km block only
    arr, tr, _ = dem.read_dtm([{"id": "657_67", "href": str(cog)}], bounds, area=corner, open_path=lambda h: h)
    step = int(dem.BLOCK_M / dem.RES)
    assert arr.shape[0] > step and arr.shape[1] > step       # four blocks; the tile lies under all of them
    assert np.isfinite(arr[:step, :step]).any()
    assert np.isnan(arr[step:, :]).all() and np.isnan(arr[:, step:]).all()


def test_two_adjacent_tiles_mosaic_without_a_seam(tmp_path):
    # Lantmäteriet's tiles meet edge to edge; one with overviews, one without (read with full_res): no NaN row or
    # column where they meet, and the plane continues across
    a = write_cog(tmp_path / "a.tif", width=600)
    b = write_cog(tmp_path / "b.tif", overviews=False, dx=600, width=600)
    items = [{"id": "a", "href": str(a)}, {"id": "b", "href": str(b)}]
    bounds = (E0 - 250, N0 - 250, E0 + 250, N0 + 250)
    arr, tr, overviews = dem.read_dtm(items, bounds, open_path=lambda h: h, full_res=True, log=lambda *_: None)
    assert not overviews
    # every pixel more than 10 m inside the two tiles' union, the seam included, has a value on the plane
    with rasterio.open(a) as ra, rasterio.open(b) as rb:
        x0, y0, x1, y1 = ra.bounds.left, rb.bounds.bottom, rb.bounds.right, ra.bounds.top
    rows, cols = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    ex, ey = Transformer.from_crs(city.CRS, 3006, always_xy=True).transform(tr.c + (cols + 0.5) * 5,
                                                                            tr.f - (rows + 0.5) * 5)
    inner = (ex > x0 + 10) & (ex < x1 - 10) & (ey > y0 + 10) & (ey < y1 - 10)
    seam = inner & (np.abs(ex - (x0 + 600)) < 10)
    assert seam.sum() > 50 and np.isfinite(arr[inner]).all()
    assert model_error(arr, tr, inner).max() < 0.05


def test_a_sliver_of_a_tile_under_the_grid_is_left_out(tmp_path):
    # a neighbouring tile whose east edge reaches 0.3 m into the grid's padded footprint: its window rounds to zero
    # columns, and reading that would stop GDAL ("Cannot invert geotransform")
    bounds = (E0 - 100, N0 - 100, E0 + 100, N0 + 100)
    tr, w, h = dem.target_grid(bounds)
    todo, pad = dem.blocks(tr, w, h), dem.PAD_PX * dem.RES
    feet = []
    for r, c, rows, cols in todo:
        x0, y1 = tr @ (c, r)
        feet.append(transform_bounds(city.CRS, 3006, x0 - pad, y1 - rows * dem.RES - pad, x0 + cols * dem.RES + pad,
                                     y1 + pad, densify_pts=21))
    west, south, north = min(f[0] for f in feet), min(f[1] for f in feet), max(f[3] for f in feet)
    path = tmp_path / "sliver.tif"
    with rasterio.open(path, "w", driver="GTiff", width=50, height=50, count=1, dtype="float32", crs="EPSG:3006",
                       transform=Affine(1, 0, west + 0.3 - 50, 0, -1, (south + north) / 2 + 25), nodata=-9999) as dst:
        dst.write(np.full((50, 50), 7.0, dtype="float32"), 1)
    with rasterio.open(path) as src:
        assert [dem.source_window(src, tr, b) for b in todo] == [None] * len(todo)
    arr, _, _ = dem.read_dtm([{"id": "sliver", "href": str(path)}], bounds, open_path=lambda p: p, full_res=True,
                             log=lambda *_: None)
    assert np.isnan(arr).all()


def test_a_tile_without_overviews_stops_unless_full_res_is_given(tmp_path):
    cog = write_cog(tmp_path / "flat.tif", overviews=False, width=2400, height=2400)
    item = [{"id": "657_67", "href": str(cog)}]
    bounds = (E0 - 100, N0 - 100, E0 + 100, N0 + 100)
    area = shapely.box(*bounds)                              # one 1 km block of the grid
    with pytest.raises(dem.NoOverviews, match="657_67") as stop:
        dem.read_dtm(item, bounds, area=area, open_path=lambda h: h)
    # what the full-resolution read would stream, from the tile's own block sizes: the blocks under the grid's window,
    # never the whole tile
    with rasterio.open(cog) as src:
        whole = sum(int(src.get_tag_item(f"BLOCK_SIZE_{x}_{y}", "TIFF", bidx=1)) for x in range(10) for y in range(10))
    assert 0 < stop.value.bytes < whole
    said, events = [], []

    def opened(href):
        events.append("open")
        return href

    def log(msg):
        said.append(msg)
        events.append("log")

    arr, _, overviews = dem.read_dtm(item, bounds, area=area, open_path=opened, full_res=True, log=log)
    assert not overviews and np.isfinite(arr).any()
    # the figure is a lower bound (the headers and any retry come on top), and the owner sees it once the headers are read,
    # before the tile is opened again to stream its blocks
    assert said == [f"terrain model: 1 tiles without overviews: streaming at least {stop.value.bytes / 1e9:.2f} GB at "
                    "full resolution"]
    assert events == ["open", "log", "open"]


def one_tile_catalogue(monkeypatch, checksum="1220657_67", asked=None):
    """The municipality as a 600 m box at the origin and a catalogue listing one tile over it (Lantmäteriet's URL);
    `asked` collects every request made to the catalogue."""
    monkeypatch.setattr(dem, "municipality", lambda *a: shapely.box(E0 - 300, N0 - 300, E0 + 300, N0 + 300))
    ex, ey = Transformer.from_crs(city.CRS, 3006, always_xy=True).transform(E0, N0)

    def get(url, *args, **kwargs):
        if asked is not None:
            asked.append((url, args, kwargs))
        f = feature("657_67", (ex - 600, ey - 600, ex + 600, ey + 600), lm_href("657_67"))
        f["assets"]["data"]["file:checksum"] = checksum
        return FakeResponse({"features": [f]})

    return get


def test_fetch_dtm_writes_the_raster_records_the_tiles_and_skips_an_unchanged_run(raw, tmp_path, monkeypatch, capsys):
    cog = write_cog(tmp_path / "m657_67.tif")
    get = one_tile_catalogue(monkeypatch)
    entry = dem.fetch_dtm((USER, PASSWORD), get=get, open_path=lambda h: str(cog))
    assert dem.DTM.exists() and entry["items"] == [{"id": "657_67", "href": lm_href("657_67"), "checksum": "1220657_67"}]
    manifest = (raw / "MANIFEST.json").read_text()
    assert "dem/dtm5.tif" in json.loads(manifest) and PASSWORD not in manifest and USER not in manifest
    with rasterio.open(dem.DTM) as src:
        assert src.crs.to_epsg() == city.CRS and src.res == (5.0, 5.0)
    monkeypatch.setattr(dem, "read_dtm", lambda *a, **k: pytest.fail("an unchanged run must not read the tiles"))
    assert dem.fetch_dtm((USER, PASSWORD), get=get, open_path=lambda h: str(cog)) is None
    out = capsys.readouterr()
    assert "up to date" in out.out and PASSWORD not in out.out + out.err and USER not in out.out + out.err


def test_a_tile_with_a_new_checksum_is_read_again(raw, tmp_path, monkeypatch, capsys):
    cog = write_cog(tmp_path / "m657_67.tif")
    dem.fetch_dtm((USER, PASSWORD), get=one_tile_catalogue(monkeypatch), open_path=lambda h: str(cog))
    reads, real = [], dem.read_dtm

    def counted(*a, **k):
        reads.append(a[0])
        return real(*a, **k)

    monkeypatch.setattr(dem, "read_dtm", counted)
    # Lantmäteriet republished the tile: same id, same URL, a new checksum
    entry = dem.fetch_dtm((USER, PASSWORD), get=one_tile_catalogue(monkeypatch, checksum="1220beef"),
                          open_path=lambda h: str(cog))
    assert len(reads) == 1 and entry["items"][0]["checksum"] == "1220beef"
    assert json.loads((raw / "MANIFEST.json").read_text())["dem/dtm5.tif"]["items"][0]["checksum"] == "1220beef"
    assert "up to date" not in capsys.readouterr().out


def test_the_login_reaches_gdal_alone_never_a_url_or_the_catalogue(raw, monkeypatch):
    # the default open_path, as the owner's run uses it: /vsicurl/ on the catalogue's href, the login in GDAL's options only
    asked, seen = [], {}
    get = one_tile_catalogue(monkeypatch, asked=asked)

    def fake_read(items, bounds, *, area=None, open_path=None, options=None, full_res=False, **kwargs):
        seen.update(items=items, open_path=open_path, options=options)
        tr, w, h = dem.target_grid(bounds)
        return np.zeros((h, w), dtype=np.float32), tr, True

    monkeypatch.setattr(dem, "read_dtm", fake_read)
    dem.fetch_dtm((USER, PASSWORD), get=get)
    paths = [seen["open_path"](i["href"]) for i in seen["items"]]
    assert paths == ["/vsicurl/" + lm_href("657_67")]
    o = seen["options"]
    assert o["GDAL_HTTP_AUTH"] == "BASIC" and o["GDAL_HTTP_USERPWD"] == f"{USER}:{PASSWORD}"
    assert [k for k, v in o.items() if PASSWORD in str(v) or USER in str(v)] == ["GDAL_HTTP_USERPWD"]
    assert len(asked) == 1 and "auth" not in asked[0][2]              # the catalogue is searched anonymously
    manifest = (raw / "MANIFEST.json").read_text()
    for text in paths + [json.dumps(seen["items"]), repr(asked), manifest]:
        assert PASSWORD not in text and USER not in text


def test_main_fetches_the_contours_and_builds_without_a_login(raw, monkeypatch, capsys):
    got = []

    def fake_member(url, member, dest, manifest=None):
        got.append(member)
        return {"member": member, "bytes": 10}

    monkeypatch.setattr(dem, "fetch_zip_member", fake_member)
    monkeypatch.setattr(dem, "fetch_dtm", lambda *a, **k: pytest.fail("no login: no DTM"))
    dem.main([])
    assert got == [dem.CONTOUR_PREFIX + m for m in dem.CONTOUR_MEMBERS]
    assert "builds the terrain from the City's contour lines" in capsys.readouterr().out
    # a model the owner fetched earlier stays, and is used, when a later build has no login
    dem.DTM.parent.mkdir(parents=True)
    dem.DTM.write_bytes(b"tif")
    dem.main([])
    assert "the cached data/raw/dem/dtm5.tif stays, unchecked (s02_terrain uses it)" in capsys.readouterr().out


def test_main_with_a_login_never_prints_the_password(raw, monkeypatch, capsys):
    got = []

    def fake_member(url, member, dest, manifest=None):
        got.append(member)
        return {"member": member, "bytes": 1}

    monkeypatch.setattr(dem, "fetch_zip_member", fake_member)
    monkeypatch.setenv("LM_USER", USER)
    monkeypatch.setenv("LM_PASSWORD", PASSWORD)
    seen = []
    monkeypatch.setattr(dem, "fetch_dtm", lambda creds, full_res=False: seen.append((creds, full_res)))
    dem.main(["--full-res"])
    assert seen == [((USER, PASSWORD), True)]
    assert got == [dem.CONTOUR_PREFIX + m for m in dem.CONTOUR_MEMBERS]     # the contours come with a login too
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err

    def no_overviews(creds, full_res=False):
        raise dem.NoOverviews(["657_67"], 812_000_000)

    monkeypatch.setattr(dem, "fetch_dtm", no_overviews)
    with pytest.raises(SystemExit, match=r"657_67 have no overviews: a full-resolution read streams at least 0\.81 GB"
                                         r".*--full-res") as stop:
        dem.main([])
    assert PASSWORD not in str(stop.value) and USER not in str(stop.value)


def test_a_refused_login_or_a_catalogue_error_warns_and_the_build_goes_on(raw, monkeypatch, capsys):
    # a 401 (the order not active yet, a mistyped login) or a catalogue that does not answer must not stop the later
    # steps: the step warns and s02_terrain builds from what is there
    monkeypatch.setattr(dem, "fetch_zip_member", lambda url, member, dest, manifest=None: {"member": member, "bytes": 1})
    monkeypatch.setenv("LM_USER", USER)
    monkeypatch.setenv("LM_PASSWORD", PASSWORD)

    def raising(e):
        def fetch_dtm(creds, full_res=False):
            raise e
        return fetch_dtm

    monkeypatch.setattr(dem, "fetch_dtm", raising(RasterioIOError("HTTP response code: 401")))   # GDAL's own words
    assert dem.main([]) is None
    out = capsys.readouterr()
    assert ("warning: terrain model not fetched (401: the Geotorget order isn't active yet or the login is wrong); "
            "s02_terrain uses the contours") in out.err
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err

    unauthorized = requests.Response()
    unauthorized.status_code = 401
    monkeypatch.setattr(dem, "fetch_dtm", raising(requests.HTTPError("401 Client Error", response=unauthorized)))
    dem.main([])
    assert "(401: the Geotorget order isn't active yet or the login is wrong)" in capsys.readouterr().err

    # the catalogue down, a model fetched earlier on disk: that one is used; a login quoted in the error is masked
    dem.DTM.parent.mkdir(parents=True)
    dem.DTM.write_bytes(b"tif")
    monkeypatch.setattr(dem, "fetch_dtm", raising(requests.ConnectionError(
        f"https://{USER}:{PASSWORD}@api.lantmateriet.se/stac-hojd/v1/search refused (user {USER.replace('@', '%40')})")))
    assert dem.main([]) is None
    out = capsys.readouterr()
    assert "warning: terrain model not fetched (https://***:***@api.lantmateriet.se/" in out.err
    assert out.err.rstrip().endswith("; s02_terrain uses the cached data/raw/dem/dtm5.tif")
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err and "user%40" not in out.err
