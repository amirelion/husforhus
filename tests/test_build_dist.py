"""scripts/build_dist.py: dist/ for Cloudflare holds the app, only the data version current.json names, and a
_headers file; the release gate (s99_validate) decides between a preview build and a public one."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIST = ROOT / "scripts" / "build_dist.py"
VERSION = "v20990101"
APP = ["index.html", "app.js", "worker.js", "styles.css", "vendor/three.module.js", "vendor/fflate.LICENSE",
       "fonts/inter/OFL.txt", "fonts/inter/inter-latin-wght-normal.woff2"]
DATA_FILES = ["stockholm.json", "labels.json", "attrs.bin.gz", "pack0.bin.gz", "cards/00.json"]


def load_build_dist():
    spec = importlib.util.spec_from_file_location("hfh_build_dist", BUILD_DIST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def web(tmp_path):
    """A tiny web/ tree: the app, its tests, dotfiles, the current version and two side builds."""
    w = tmp_path / "web"
    for rel in [*APP, "test/app.test.mjs", "test/fixtures/tile_v1.bin.gz", ".DS_Store", "fonts/.DS_Store"]:
        write(w / rel)
    write(w / "data" / "current.json", json.dumps({"version": VERSION}))
    for v in [VERSION, f"{VERSION}-t1200", "v20980101"]:
        for rel in [*DATA_FILES, ".DS_Store", "cards/.DS_Store"]:
            write(w / "data" / v / rel)
    return w


@pytest.fixture
def bd(monkeypatch, tmp_path):
    """The module with its release gate replaced: `bd.gate_errors[release]` is what the gate reports, and
    `bd.gate_calls` records (version folder, release) per call. git is replaced too (`bd.git_head`, and
    `bd.git_dirty` for uncommitted changes), and the record of built versions lives in tmp_path."""
    module = load_build_dist()
    module.gate_errors = {False: [], True: []}
    module.gate_calls = []
    module.git_head, module.git_dirty = "abc1234", []

    def gate(version_dir, data, release):
        module.gate_calls.append((Path(version_dir).name, release))
        return list(module.gate_errors[release])

    monkeypatch.setattr(module, "gate", gate)
    monkeypatch.setattr(module, "git_state", lambda: (module.git_head, list(module.git_dirty)))
    monkeypatch.setattr(module, "RECORD", tmp_path / "dist-versions.json")
    return module


def build(bd, web, tmp_path, **kw):
    out = tmp_path / "dist"
    bd.build(out, web=web, data=tmp_path / "data", **kw)
    return out


def files(out: Path) -> set[str]:
    return {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def rules(text: str) -> dict[str, dict[str, str]]:
    """_headers as {path pattern: {header: value}}; '#' lines are comments."""
    out, current = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = out.setdefault(line.strip(), {})
        else:
            name, value = line.strip().split(":", 1)
            current[name.strip()] = value.strip()
    return out


def matches(pattern: str, path: str) -> bool:
    """Cloudflare's rule matching: each '*' is a splat ('.*'), the rule is anchored at both ends."""
    return re.fullmatch(".*".join(map(re.escape, pattern.split("*"))), path) is not None


def headers_for(r: dict, path: str) -> dict[str, list[str]]:
    """Every value each header gets on `path`: matching rules combine, and a header set twice is joined."""
    got = {}
    for pattern, hs in r.items():
        if matches(pattern, path):
            for name, value in hs.items():
                got.setdefault(name, []).append(value)
    return got


def csp(value: str) -> dict[str, list[str]]:
    parts = [p.split() for p in value.split(";") if p.strip()]
    return {p[0]: p[1:] for p in parts}


def test_dist_holds_the_app_and_only_the_current_version(bd, web, tmp_path):
    out = build(bd, web, tmp_path)
    got = files(out)
    assert set(APP) <= got
    assert "data/current.json" in got
    assert {f"data/{VERSION}/{rel}" for rel in DATA_FILES} <= got
    # side builds (v20261015-t1200 and the like) and older versions never ship
    assert not [f for f in got if f.startswith("data/") and f != "data/current.json"
                and not f.startswith(f"data/{VERSION}/")]
    assert json.loads((out / "data" / "current.json").read_text())["version"] == VERSION


def test_dev_files_stay_out(bd, web, tmp_path):
    got = files(build(bd, web, tmp_path))
    assert not [f for f in got if f.startswith("test/")]
    assert not [f for f in got if Path(f).name.startswith(".")]


def test_headers_cache_rules(bd, web, tmp_path):
    r = rules((build(bd, web, tmp_path) / "_headers").read_text())
    immutable = "public, max-age=31536000, immutable"
    revalidate = "public, max-age=0, must-revalidate"
    expected = {
        f"/data/{VERSION}/pack0.bin.gz": immutable,
        f"/data/{VERSION}/stockholm.json": immutable,
        f"/data/{VERSION}/cards/00.json": immutable,
        "/data/current.json": "no-cache",
        "/": revalidate,
        "/index.html": revalidate,
        "/app.js": revalidate,
        "/vendor/three.module.js": revalidate,
        "/styles.css": revalidate,
        "/fonts/inter/inter-latin-wght-normal.woff2": "public, max-age=604800",
    }
    for path, value in expected.items():
        # exactly one rule sets it: Cloudflare would join two values with a comma
        assert headers_for(r, path).get("Cache-Control") == [value], path


def test_gz_data_is_opaque_binary(bd, web, tmp_path):
    r = rules((build(bd, web, tmp_path) / "_headers").read_text())
    gz = headers_for(r, f"/data/{VERSION}/attrs.bin.gz")
    assert gz["Content-Type"] == ["application/octet-stream"]
    # JSON keeps its own type (so Cloudflare compresses it on the wire), and nothing claims a Content-Encoding
    assert "Content-Type" not in headers_for(r, f"/data/{VERSION}/stockholm.json")
    assert not [p for p, hs in r.items() if "Content-Encoding" in hs]


def test_headers_security(bd, web, tmp_path):
    r = rules((build(bd, web, tmp_path) / "_headers").read_text())
    for path in ["/", "/app.js", "/worker.js", f"/data/{VERSION}/pack0.bin.gz"]:
        hs = headers_for(r, path)
        assert hs["X-Content-Type-Options"] == ["nosniff"], path
        assert len(hs["Referrer-Policy"]) == 1, path
        assert len(hs["Content-Security-Policy"]) == 1, path
    policy = csp(headers_for(r, "/")["Content-Security-Policy"][0])
    assert policy["default-src"] == ["'self'"]
    assert policy["script-src"] == ["'self'"]  # no inline scripts, no eval
    assert policy["worker-src"] == ["'self'"]  # app.js starts module workers from worker.js
    assert policy["connect-src"] == ["'self'"]
    assert policy["font-src"] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["frame-ancestors"] == ["'none'"]


def test_headers_fit_cloudflare_limits(bd, web, tmp_path):
    text = (build(bd, web, tmp_path) / "_headers").read_text()
    assert len(rules(text)) <= bd.CF_MAX_HEADER_RULES <= 100
    assert max(len(line) for line in text.splitlines()) <= bd.CF_MAX_HEADER_LINE <= 2000


def test_preview_build_is_noindex_and_says_so(bd, web, tmp_path, capsys):
    bd.gate_errors[True] = ["sources: city_lod1: status pending-O1 is not allowed in a release"]
    out = build(bd, web, tmp_path)
    assert (VERSION, False) in bd.gate_calls
    printed = capsys.readouterr().out
    assert "PREVIEW ONLY" in printed and "not for the public site" in printed
    assert "city_lod1" in printed  # why it is not releasable yet
    r = rules((out / "_headers").read_text())
    assert headers_for(r, "/")["X-Robots-Tag"] == ["noindex"]
    assert headers_for(r, f"/data/{VERSION}/pack0.bin.gz")["X-Robots-Tag"] == ["noindex"]


def test_release_build_is_indexable(bd, web, tmp_path, capsys):
    out = build(bd, web, tmp_path, release=True)
    assert bd.gate_calls == [(VERSION, True)]
    assert "PREVIEW ONLY" not in capsys.readouterr().out
    assert not [p for p, hs in rules((out / "_headers").read_text()).items() if "X-Robots-Tag" in hs]


def test_release_refused_when_the_gate_fails(bd, web, tmp_path, capsys):
    bd.gate_errors[True] = ["sources: city_lod1: status pending-O1 is not allowed in a release"]
    with pytest.raises(SystemExit) as e:
        build(bd, web, tmp_path, release=True)
    assert e.value.code not in (0, None)
    assert "city_lod1" in capsys.readouterr().err
    assert not (tmp_path / "dist").exists()


def test_preview_refused_when_the_data_fails(bd, web, tmp_path):
    bd.gate_errors[False] = ["attrs: 3 buildings with a height outside (0, 200] m (gids 1, 2, 3)"]
    with pytest.raises(SystemExit):
        build(bd, web, tmp_path)
    assert not (tmp_path / "dist").exists()
    assert not bd.RECORD.exists()


def test_a_build_records_what_its_version_holds(bd, web, tmp_path):
    build(bd, web, tmp_path)
    record = json.loads(bd.RECORD.read_text())
    assert set(record) == {VERSION}
    assert set(record[VERSION]) == set(DATA_FILES)  # what ships: no dotfiles


@pytest.mark.parametrize("change", ["edit", "add", "remove"])
def test_a_version_name_never_changes_content(bd, web, tmp_path, change):
    """/data/<version>/ is cached for a year (immutable), but a same-day pipeline run writes into the same folder:
    once built, a version name must keep its bytes, or browsers would mix old and new files."""
    out = build(bd, web, tmp_path)
    before = bd.RECORD.read_text()
    folder = web / "data" / VERSION
    if change == "edit":
        write(folder / "pack0.bin.gz", "changed")
    elif change == "add":
        write(folder / "pack9.bin.gz")
    else:
        (folder / "pack0.bin.gz").unlink()
    with pytest.raises(SystemExit, match=VERSION) as e:
        build(bd, web, tmp_path)
    assert re.search(r"pack[09]\.bin\.gz", str(e.value))  # names what changed
    assert f"--version {VERSION}-2" in str(e.value)  # and how to rebuild under a new name
    assert bd.RECORD.read_text() == before
    assert (out / "data" / VERSION / "pack0.bin.gz").read_text() == "x"  # the last good dist is left alone


def test_other_versions_keep_their_record(bd, web, tmp_path):
    build(bd, web, tmp_path)
    write(web / "data" / "current.json", json.dumps({"version": "v20980101"}))
    build(bd, web, tmp_path)
    assert set(json.loads(bd.RECORD.read_text())) == {VERSION, "v20980101"}


def test_uncommitted_changes_are_refused(bd, web, tmp_path):
    bd.git_dirty = [" M web/app.js", "?? web/new.js"]
    with pytest.raises(SystemExit, match="--allow-dirty") as e:
        build(bd, web, tmp_path)
    assert "web/app.js" in str(e.value) and "web/new.js" in str(e.value)
    assert not (tmp_path / "dist").exists()


def test_allow_dirty_builds_and_says_so(bd, web, tmp_path, capsys):
    bd.git_dirty = [" M web/app.js"]
    build(bd, web, tmp_path, allow_dirty=True)
    printed = capsys.readouterr().out
    assert "uncommitted" in printed and "web/app.js" in printed


def test_main_passes_allow_dirty(bd, monkeypatch):
    seen = []
    monkeypatch.setattr(bd, "build", lambda out, **kw: seen.append(kw))
    bd.main(["--allow-dirty"])
    bd.main([])
    assert [kw["allow_dirty"] for kw in seen] == [True, False]


def test_git_state_lists_uncommitted_files_that_ship(tmp_path):
    repo = tmp_path / "repo"

    def git(*args):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                       check=True, capture_output=True)

    for rel in ["web/app.js", "scripts/build_dist.py", "wrangler.jsonc", "docs/notes.md"]:
        write(repo / rel)
    git("init", "-q")
    git("add", "web", "scripts", "wrangler.jsonc", "docs")
    git("commit", "-q", "-m", "init")
    git_state = load_build_dist().git_state
    head, dirty = git_state(repo)
    assert re.fullmatch(r"[0-9a-f]{7,}", head) and dirty == []
    write(repo / "web" / "app.js", "y")
    write(repo / "web" / "new" / "look.js")
    write(repo / "docs" / "notes.md", "y")
    head, dirty = git_state(repo)
    assert sorted(line[3:] for line in dirty) == ["web/app.js", "web/new/look.js"]  # docs/ does not ship


def test_missing_current_json_fails(bd, web, tmp_path):
    (web / "data" / "current.json").unlink()
    with pytest.raises(SystemExit, match="current.json"):
        build(bd, web, tmp_path)


def test_current_json_naming_a_missing_folder_fails(bd, web, tmp_path):
    write(web / "data" / "current.json", json.dumps({"version": "v20000101"}))
    with pytest.raises(SystemExit, match="v20000101"):
        build(bd, web, tmp_path)


def test_current_json_naming_a_path_fails(bd, web, tmp_path):
    write(web / "data" / "current.json", json.dumps({"version": "../data"}))
    with pytest.raises(SystemExit, match="version"):
        build(bd, web, tmp_path)


def test_file_over_the_size_limit_fails(bd, web, tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "CF_MAX_FILE_BYTES", 10)
    write(web / "data" / VERSION / "pack1.bin.gz", "y" * 11)
    with pytest.raises(SystemExit, match="pack1.bin.gz"):
        build(bd, web, tmp_path)


def test_too_many_files_fails(bd, web, tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "CF_MAX_FILES", 5)
    with pytest.raises(SystemExit, match="files"):
        build(bd, web, tmp_path)


def test_summary(bd, web, tmp_path, capsys):
    write(web / "data" / VERSION / "pack0.bin.gz", "z" * 5000)
    build(bd, web, tmp_path)
    printed = capsys.readouterr().out
    n = len(APP) + 1 + len(DATA_FILES)  # _headers is configuration, not a served file
    assert f"{n} files" in printed
    assert f"data/{VERSION}/pack0.bin.gz" in printed
    assert "abc1234" in printed  # the commit it was built from


def test_rebuild_replaces_the_previous_dist(bd, web, tmp_path):
    out = build(bd, web, tmp_path)
    write(out / "stale.js")
    build(bd, web, tmp_path)
    assert not (out / "stale.js").exists()


def test_refuses_to_replace_a_folder_it_did_not_build(bd, web, tmp_path):
    write(tmp_path / "dist" / "notes.txt")
    with pytest.raises(SystemExit, match="dist"):
        build(bd, web, tmp_path)
    assert (tmp_path / "dist" / "notes.txt").exists()


def test_gate_is_s99_validate(monkeypatch, tmp_path):
    import pipeline.s99_validate

    seen = []
    monkeypatch.setattr(pipeline.s99_validate, "validate",
                        lambda out, data, *, release: seen.append((out, data, release)) or ["x"])
    assert load_build_dist().gate(tmp_path / VERSION, tmp_path / "data", True) == ["x"]
    assert seen == [(tmp_path / VERSION, tmp_path / "data", True)]


def test_wrangler_config():
    lines = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8").splitlines()
    cfg = json.loads("\n".join(line for line in lines if not line.lstrip().startswith("//")))
    assert cfg["name"] == "husforhus"
    # A Worker script in front of the assets, run first only for /api/* (the report form and the owner's triage)
    assert cfg["main"] == "src/worker.js" and (ROOT / cfg["main"]).is_file()
    assert cfg["assets"]["binding"] == "ASSETS"
    assert cfg["assets"]["run_worker_first"] == ["/api/*"]
    assert [(d["binding"], d["migrations_dir"]) for d in cfg["d1_databases"]] == [("REPORTS", "src/migrations")]
    assert [r["binding"] for r in cfg["r2_buckets"]] == ["PHOTOS"]
    assert len(cfg["triggers"]["crons"]) == 1
    # No secret and no Access setting in the repo: they are dashboard variables and Worker secrets, kept across deploys
    assert cfg["keep_vars"] is True and "vars" not in cfg
    assert "account_id" not in cfg  # wrangler takes it from `wrangler login`
    assert cfg["assets"]["directory"] == "./dist"
    assert cfg["assets"]["not_found_handling"] == "none"  # a missing data file is a 404, not index.html
    assert cfg["workers_dev"] is False  # launched 2026-10-17: only the production address
    assert cfg["observability"] == {"enabled": False}
    assert {r["pattern"] for r in cfg["routes"]} == {"husforhus.se", "www.husforhus.se"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cfg["compatibility_date"])


def test_worker_sources_are_public_and_hold_no_secret():
    allow = (ROOT / "scripts" / "public" / "allowlist.txt").read_text(encoding="utf-8").splitlines()
    assert "src/**" in allow
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "src").rglob("*")) if p.is_file())
    text += (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    assert not re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", text)  # no GitHub token
    assert "cloudflare" "access" not in text  # the Access team domain is a dashboard variable (and a leak rule)
    assert "env.GITHUB_TOKEN" in text and "env.ACCESS_AUD" in text


def test_package_scripts_and_ignores():
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", pkg["devDependencies"]["wrangler"])  # pinned exactly
    assert "build_dist.py" in pkg["scripts"]["dist"]
    assert "8787" in pkg["scripts"]["preview:local"]
    assert "--allow-dirty" in pkg["scripts"]["preview:local"]  # local only: uncommitted work may be looked at
    deploy = pkg["scripts"]["deploy:preview"]
    assert "wrangler deploy" in deploy and "--allow-dirty" not in deploy
    assert deploy.index("dist") < deploy.index("wrangler")
    assert "--message" in deploy and "git rev-parse" in deploy  # the version records the commit it came from
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert "dist/" in ignored and ".wrangler/" in ignored and ".dist-versions.json" in ignored


def test_the_photos_the_version_uses_ship_and_no_others(bd, web, tmp_path):
    # S06_wiki copies photos to web/data/photos/ by key; s03_tiles lists the ones a version uses
    keys = ["0123456789abcdef-500.jpg", "fedcba9876543210-500.png"]
    write(web / "data" / VERSION / "photos.json", json.dumps(keys))
    for k in [*keys, "aaaaaaaaaaaaaaaa-500.jpg"]:
        write(web / "data" / "photos" / k)
    out = build(bd, web, tmp_path)
    assert {f for f in files(out) if f.startswith("data/photos/")} == {f"data/photos/{k}" for k in keys}
    r = rules((out / "_headers").read_text())
    assert headers_for(r, "/data/photos/0123456789abcdef-500.jpg")["Cache-Control"] == [
        "public, max-age=31536000, immutable"]


def test_a_listed_photo_that_is_missing_stops_the_build(bd, web, tmp_path):
    write(web / "data" / VERSION / "photos.json", json.dumps(["0123456789abcdef-500.jpg"]))
    with pytest.raises(SystemExit, match="1 missing photos"):
        build(bd, web, tmp_path)
    write(web / "data" / VERSION / "photos.json", json.dumps(["../../secret.txt"]))
    with pytest.raises(SystemExit, match="1 bad"):
        build(bd, web, tmp_path)


def test_robots_and_sitemap_ship(bd):
    # the real web/: both are top-level app files, so they land at dist/robots.txt and dist/sitemap.xml
    shipped = {str(p) for p in bd.app_files(ROOT / "web")}
    assert {"robots.txt", "sitemap.xml"} <= shipped
    robots = (ROOT / "web" / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://husforhus.se/sitemap.xml" in robots.splitlines()
    sitemap = (ROOT / "web" / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://husforhus.se/</loc>" in sitemap and re.search(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", sitemap)


def test_the_page_describes_itself_without_javascript():
    # search engines and no-JS readers: valid JSON-LD on the canonical URL, and a plain-text noscript line
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert ld["@type"] == "WebApplication" and ld["url"] == "https://husforhus.se/"
    assert ld["image"] == "https://husforhus.se/og.png" and (ROOT / "web" / "og.png").is_file()
    assert '<link rel="canonical" href="https://husforhus.se/">' in html
    assert re.search(r"<noscript><p[^>]*>[^<]*Stockholm", html)


def test_every_documented_rebuild_runs_the_search_step():
    # final review F4: with config.features.search on, s99 fails on a version without search/ (only s14_search
    # writes it), so every rebuild command that ends in s99_validate runs s14_search first
    root = Path(__file__).resolve().parents[1]
    # the public repo has one README at its root (the export moves docs-public/README.md there)
    docs = [p for p in (root / "README.md", root / "docs-public" / "README.md") if p.exists()]
    assert root / "README.md" in docs
    for path in (*docs, root / "scripts" / "build_dist.py"):
        commands = re.findall(r"pipeline\.run ([a-z0-9_ ]+?) --", path.read_text(encoding="utf-8"))
        rebuilds = [c.split() for c in commands if "s03_tiles" in c.split() and "s99_validate" in c.split()]
        assert rebuilds, path
        for steps in rebuilds:
            assert "s14_search" in steps and steps.index("s14_search") < steps.index("s99_validate"), (path, steps)
