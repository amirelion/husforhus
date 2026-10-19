"""The CI workflows run what the plan says: offline checks on every push, network tests weekly or on demand."""
import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
# The weekly Network run is private (scripts/public/allowlist.txt): the public copy has ci.yml only.
private_only = pytest.mark.skipif(not (WORKFLOWS / "network.yml").exists(), reason="no network.yml in the public copy")


def load(name):
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return wf, wf.get("on", wf.get(True))  # YAML 1.1 reads a bare `on` key as True


def check_uv_job(job):
    """Checkout, a pinned uv, a locked install and pytest. Returns the job's run commands as one string."""
    steps = job["steps"]
    assert job["runs-on"] == "ubuntu-latest"
    assert any(s.get("uses", "").startswith("actions/checkout@") for s in steps)
    setup_uv = next(s for s in steps if s.get("uses", "").startswith("astral-sh/setup-uv@"))
    assert setup_uv["uses"] == "astral-sh/setup-uv@v10.3.0"
    # astral-sh/setup-uv publishes exact release tags only (no floating v10), so the ref must stay exact.
    assert re.fullmatch(r"astral-sh/setup-uv@v\d+\.\d+\.\d+", setup_uv["uses"]), setup_uv["uses"]
    assert setup_uv["with"]["version"]  # uv itself is pinned too
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "uv sync --locked" in runs and "uv run pytest -q" in runs
    return runs


def test_ci_workflows():
    ci, on = load("ci.yml")
    assert set(on) == {"push", "pull_request"}
    assert set(ci["jobs"]) == {"test"}, "network and e2e jobs belong in network.yml"
    assert "HFH_NETWORK" not in str(ci["jobs"])  # offline: the network tests skip on every push
    test = ci["jobs"]["test"]
    runs = check_uv_job(test)
    assert "uv run ruff check pipeline tests scripts" in runs  # scripts/serve.py runs in the launch config and e2e
    assert 'node --test "web/test/*.test.mjs"' in runs
    node = next(s for s in test["steps"] if s.get("uses", "").startswith("actions/setup-node@"))
    assert node["with"]["node-version-file"] == ".nvmrc"


@private_only
def test_network_job():
    net, on = load("network.yml")
    assert set(on) == {"workflow_dispatch", "schedule"} and on["schedule"][0]["cron"]
    job = net["jobs"]["network"]  # the `e2e` job next to it is checked in test_e2e_job
    assert job["env"]["HFH_NETWORK"] == "1"
    check_uv_job(job)
    caches = {s["with"]["path"]: s["with"]["key"] for s in job["steps"]
              if s.get("uses", "").startswith("actions/cache@")}
    assert "hashFiles('tests/conftest.py')" in caches["data/cache"]
    assert "hashFiles('pipeline/sources.yml')" in caches["data/raw"]


@private_only
def test_e2e_job():
    """The viewer end to end on the fixture, in network.yml (weekly and on demand), with the golden check."""
    net, _ = load("network.yml")
    job = net["jobs"]["e2e"]
    steps = job["steps"]
    assert job["runs-on"] == "ubuntu-latest" and "if" not in job  # the workflow's triggers decide when it runs
    uses = {s["uses"].split("@")[0]: s.get("with", {}) for s in steps if "uses" in s}
    network = {s["uses"].split("@")[0]: s.get("with", {}) for s in net["jobs"]["network"]["steps"] if "uses" in s}
    assert uses["astral-sh/setup-uv"]["version"] == network["astral-sh/setup-uv"]["version"]  # the uv pin
    assert uses["actions/setup-node"]["node-version-file"] == ".nvmrc"
    assert uses["actions/cache"] == {"path": "data/raw", "key": "raw-${{ hashFiles('pipeline/sources.yml') }}"}
    runs = [s.get("run", "") for s in steps]
    assert "uv run python -m pipeline.run" in [r.strip() for r in runs]  # every step in STEPS, on the fixture
    golden = next(r for r in runs if "diff -r" in r)
    # The search index is rebuilt and compared too (s14_search reads the version's own cards)
    assert "uv run python -m pipeline.run s03_tiles s04_base s07_labels s14_search -- --version" in golden
    assert sum(s.get("env", {}).get("HFH_FIXTURE") == "1" for s in steps) == 2  # the pipeline and the golden check
    # the smoke and launch specs only (2026-10-19): the whole suite needs about 75 min on a runner without a GPU
    for command in ["uv sync --locked", "npm ci", "npx playwright install --with-deps chromium",
                    "npx playwright test e2e/smoke.spec.mjs e2e/launch.spec.mjs"]:
        assert command in "\n".join(runs), command
    assert job["timeout-minutes"] == 90
