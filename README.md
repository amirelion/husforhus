# Hus för hus

*Stockholm, building by building.* A 3D map of every building in Stockholm municipality, about 78,000 of them, each coloured by when it was built.

The map is live at [husforhus.se](https://husforhus.se). On it you can:

- drag a timeline to watch the city grow, or pick one of twelve periods of Stockholm's building history;
- search for a street, an address ("Hornsgatan 30"), a named building ("Stadshuset", "Royal Palace") or a district, including everyday names such as "Söder" or "Vasastan";
- open a card for any building: its year and where that year comes from, its height and floors, and, where open sources have them, its name, address, architect, heritage rating and protection. Notable buildings also get a photo with its credit, a short excerpt from Wikipedia, and links to the heritage register, Wikipedia and Wikidata;
- read the About panel: how the years are known, how accurate the estimates are, privacy, sources and how to ask for a correction.

The whole interface is in English and Swedish. It opens in Swedish for a Swedish browser and in English otherwise, and a switch changes the language (`?lang=sv` or `?lang=en` does it for one visit). Scenes from the city's history are coming later.

The map is a port of [Amsterdam, building by building](https://github.com/alexbarakov/amsterdam-by-building) (MIT). It keeps that project's renderer and file layout and puts everything Stockholm-specific in one thin city layer (`pipeline/city.py`), so engine fixes can still move between the two.

More in this folder:

- [How the years work](HOW-YEARS-WORK.md): where each building's year comes from, how gaps are estimated, and why private houses show only a decade.
- [Data sources](DATA-SOURCES.md): every dataset, with its licence and credit.
- [Privacy](PRIVACY.md): what the map shows about private houses, what the site does not collect, and how to ask for a correction or a takedown.
- [Changelog](CHANGELOG.md): what changed on the map, features and data, and what is planned next.
- [Contributing](CONTRIBUTING.md): how to propose corrections, building details, history sources, new cities, translations and code.

## How it fits together

```
open data ──► pipeline/ (Python) ──► web/data/<version>/ (gzipped binaries + JSON) ──► web/ (three.js, no build step)
```

- **`pipeline/`** downloads open data, joins it onto the City's building footprints, works out a year, a height and a ground level for each building, and writes compact tiles.
- **`web/`** is a static viewer. It has no build step: serve the folder and open it in a browser.
- Raw downloads go to `data/` and generated output to `web/data/`. Neither is in the repository; you build them.

## Build it

You need [uv](https://docs.astral.sh/uv/) (it installs the Python the project pins) and, for the web tests, Node 22.

```bash
uv sync
uv run python -m pipeline.run --list     # the steps, in order
HFH_FIXTURE=1 uv run python -m pipeline.run   # quick build: Gamla stan and Riddarholmen only (519 buildings)
uv run python -m pipeline.run            # the whole city (downloads several hundred MB; takes a while)
python3 scripts/serve.py 8642            # then open http://localhost:8642
```

Start with the quick build: it runs every step on a small area and is what the continuous-integration checks use. The quick build replaces the current version folder, so run the full build afterwards if you want the whole city back.

Tests:

```bash
uv run pytest -q                 # pipeline tests (add --network for the ones that download data)
npm ci
npm run test:web                 # viewer unit tests
npx playwright install chromium  # once
npm run test:e2e                 # browser smoke tests
```

### Terrain

By default the ground is built from the City's 2 m contour lines, which need no account. The pipeline can instead use Lantmäteriet's 1 m terrain model if `LM_USER` and `LM_PASSWORD` for a free Lantmäteriet Geotorget account are in the environment of `s00_fetch_dem`. The pipeline never reads a `.env` file by itself; pass one explicitly, for example `uv run --env-file .env python -m pipeline.s00_fetch_dem`. Later builds reuse the cached model.

### Towers and spires

The City's 3D buildings give each footprint one flat height, so a tower or a spire is no higher than the roof beside it. With the same Lantmäteriet login (and an order of Laserdata Nedladdning, skog on Geotorget), `s00_fetch_laser` reads Lantmäteriet's laser points around the landmarks, churches and tall buildings (never around private houses), and `s02_towers` finds the parts that rise well above each roof. They are drawn as parts of their building: the same card, colour and year. The step prints how much it will read before it reads it and stops above 500 MB unless given `--full`; `--only list` reads just the hand-picked landmarks in `pipeline/city.py`, a small first check:

```bash
uv run --env-file .env python -m pipeline.s00_fetch_laser
uv run python -m pipeline.run s02_towers s03_tiles s04_base s07_labels s14_search s15_plaques s99_validate -- --version v20261017-2
```

`s02_towers` also writes `data/review-towers.md`, the largest raises and the buildings it skipped, for a check by hand before a version ships. The points stay in `data/raw/laser/` and are never published.

### Versions

Each build writes to `web/data/v<YYYYMMDD>/` and points `web/data/current.json` at it. To rebuild under another name, pass a version after `--`:

```bash
uv run python -m pipeline.run s03_tiles s04_base s07_labels s14_search s99_validate -- --version v20261015-2
```

## The pipeline steps

`uv run python -m pipeline.run` runs these in order; `uv run python -m pipeline.run <step> <step>` runs only the ones you name, still in this order.

| Step | What it does |
|---|---|
| `s00_fetch_city` | Downloads the City of Stockholm's 3D buildings, its 117 districts and the map layers (water, land, street names, contours). |
| `s00_fetch_raa` | Downloads the National Heritage Board's (RAÄ) building register for Stockholm county. |
| `s00_fetch_raa_old` | Keeps a snapshot of RAÄ's older register file, which dates some buildings the current register no longer does. |
| `s00_fetch_wikidata` | Queries Wikidata for buildings with a start or opening date, and for photos and article links. |
| `s00_fetch_osm` | Queries OpenStreetMap for dated buildings and for floor counts. |
| `s00_fetch_dem` | Fetches the contour lines, and Lantmäteriet's terrain model when a login is available. |
| `s01_load` | Turns the City's 3D buildings into one table of footprints with heights and building types. |
| `s08_landmarks` | Checks the hand-curated landmark list: each entry must match the Wikipedia article it cites, or it is dropped. |
| `s02_years` | Gives each building a year from the best source available, and estimates houses where that can be done reliably. See [How the years work](HOW-YEARS-WORK.md). |
| `s02_attributes` | Adds floors, heritage rating, protection status, architects and a display name. |
| `s02_terrain` | Builds the terrain grid and fixes each building's ground level to it. |
| `s06_wiki` | Fetches photos and short Wikipedia excerpts for the buildings that have them. |
| `s00_fetch_laser` | Reads Lantmäteriet's laser points around landmarks, churches and tall buildings, when a login is available. |
| `s02_towers` | Finds the towers and spires that rise above each building's flat roof in those points. |
| `s03_tiles` | Writes the building tiles the viewer loads. |
| `s04_base` | Writes the base map: water, land, terrain and the municipal edge. |
| `s07_labels` | Writes street-name and place labels. |
| `s14_search` | Writes the search index: districts and their everyday names, streets and their numbers, and named buildings, taken only from what the cards show. |
| `s99_validate` | Checks the output: counts, ranges, privacy rules and that every source carries its credit. |

Arguments after `--` go to every chosen step, for example `-- --version v20261017-2`.

## Licence

Code: MIT, see [LICENSE](LICENSE). Each dataset keeps its own licence; see [Data sources](DATA-SOURCES.md).
