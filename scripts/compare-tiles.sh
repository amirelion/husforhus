#!/usr/bin/env bash
# Task 18: build the tiles at 1200 m and 1500 m and measure draw calls at the home view and from 20 km.
# Needs a full pipeline run first, Node 22+ on PATH and a server of this checkout in another terminal, on HFH_PORT
# (default 8653; never 8642, the owner's preview of the main checkout, which scripts/measure.mjs refuses):
#   python3 scripts/serve.py 8653 --bind 0.0.0.0   (0.0.0.0 so a phone on the same network can open it)
#   source ~/.nvm/nvm.sh && nvm use 22 >/dev/null && ./scripts/compare-tiles.sh
# Each size is a side build v<today>-t<T>. s03_tiles, s04_base and s07_labels run together (contract C7), so the
# folder has its own land, water and labels, and current.json points at it while it is measured. Writes
# data/perf/tile-<T>-<device>.json. With HFH_PHONE=1 it pauses after each build so you can read the ?debug=1
# overlay on a phone. At the end TILE in pipeline/city.py is restored and the main version is rebuilt in place,
# which points current.json back at it.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${HFH_URL:-http://127.0.0.1:${HFH_PORT:-8653}/}"
orig=$(uv run python -c "from pipeline import city; print(city.TILE)")
main=$(python3 -c "import json;print(json.load(open('web/data/current.json'))['version'])")   # the main build
build() {   # $1 = TILE in metres, $2 = the version to write
  uv run python - "$1" <<'PY'
import pathlib, re, sys
p = pathlib.Path("pipeline/city.py")
p.write_text(re.sub(r"^TILE = [0-9.]+", f"TILE = {float(sys.argv[1])}", p.read_text(), count=1, flags=re.M))
PY
  uv run python -m pipeline.run s03_tiles s04_base s07_labels -- --version "$2"
}
trap 'build "$orig" "$main"' EXIT
mkdir -p data/perf
ip=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d" " -f1 || echo "<laptop-ip>")
for T in 1200 1500; do
  build "$T" "$(date +v%Y%m%d)-t$T"
  node scripts/measure.mjs --url "$URL" --label "tile$T" > "data/perf/tile-$T-desktop.json"
  node scripts/measure.mjs --url "$URL" --label "tile$T" --phone > "data/perf/tile-$T-phone-emulated.json"
  node -e 'for (const f of process.argv.slice(1)) { const d = JSON.parse(require("fs").readFileSync(f, "utf8"));
    console.log(f, "home", d.home.calls, "calls", d.home.triangles, "tris | 20 km", d.overview.calls, "calls", d.overview.triangles, "tris", d.errors.length ? d.errors : ""); }' \
    "data/perf/tile-$T-desktop.json" "data/perf/tile-$T-phone-emulated.json"
  if [ "${HFH_PHONE:-0}" = 1 ]; then
    read -r -p "TILE $T: open http://$ip:${HFH_PORT:-8653}/?debug=1 on the phone, note calls and fps at 'Home view' and '20 km', then press Enter. "
  fi
done
