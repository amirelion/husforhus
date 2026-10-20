# Contributing

Thanks for helping. Useful contributions include corrections to the data, details for notable buildings, history sources, new cities, translations and code. Small contributions are as welcome as big ones.

Before opening a pull request, run the checks:

```bash
uv run pytest -q
npm run test:web
HFH_FIXTURE=1 uv run python -m pipeline.run   # quick build of a small area
```

## Opening an issue

[Open an issue](https://github.com/amirelion/husforhus/issues/new/choose) with one of the forms: **Wrong year or detail**, **Photo problem**, **New data source** or **Translation**. Each asks for what we need to act on it. Something about a private home goes to the contact in the site's About panel ([husforhus.se/#about/contact](https://husforhus.se/#about/contact)), not to a public issue.

## Proposing a correction

First find where the wrong value comes from. A building's card names the source of its year (see [How the years work](HOW-YEARS-WORK.md)). Then:

### The source itself is wrong

Most years come from open registers: RAÄ's building register, Wikidata and OpenStreetMap. The best fix is upstream, where everyone benefits, and the map picks it up on its next build:

- **Wikidata** or **OpenStreetMap**: edit the item or the building directly, citing your source.
- **RAÄ's register** or **the City's buildings**: these are maintained by their publishers. Open a **Wrong year or detail** issue with the building, what is wrong and your source, and we can pass it on or work around it.

### A notable building has the wrong year

Open an issue or a pull request adding the building to the curated landmark list, `pipeline/landmarks.py`. The comment at the top of that file describes each field. In short, an entry needs:

- the building's Wikidata item (or a point inside its footprint, with the reason);
- the year shown (completion or inauguration), and the first and last year of construction;
- a Swedish or English Wikipedia article that states those years, and a few `checks`: exact strings from that article.

`s08_landmarks` fetches the article before every build and drops any entry whose checks no longer match, so an entry is only as good as its citation. Private houses can be added only when they are genuinely notable; the entry then gives the house its full card (see "Private houses" in [How the years work](HOW-YEARS-WORK.md)).

### Something else looks wrong

A height, a floor count, a label: open a **Wrong year or detail** issue (a photo: a **Photo problem** issue) with the building (a link from the map, or its address), what you see and what you expected. Screenshots help.

### Privacy

If a card shows something about a private home that it should not, don't open a public issue: write to the contact in the site's About panel ([husforhus.se/#about/contact](https://husforhus.se/#about/contact)), as described in [Privacy](PRIVACY.md), and describe where it is without repeating the personal detail. The same contact takes requests to take a building's details off the map. Names of houses and of rarely seen architects ship only from lists a person has checked (`pipeline/private_names.txt`, `pipeline/private_firms.txt`); please don't add to those lists without a source.

## Adding building details

Useful details for a building:

- a construction or rebuild year, with a source;
- the architect, with a source;
- a better photo, openly licensed (CC BY, CC BY-SA, CC0 or public domain) and with a named author;
- a short fact, with a source.

**Privacy rules.** The map is about buildings, not the people in them:

- Public and notable buildings may get full details.
- Private houses show only their decade.
- No owners, residents or other private persons are named.
- No property designations.
- Facts only, in your own words; never text copied from other sites.

**How to submit.**

- Years, architects and facts for a notable building go in `pipeline/landmarks.py`, as described in [A notable building has the wrong year](#a-notable-building-has-the-wrong-year). The comment at the top of that file describes each field.
- Photos go in `pipeline/photo_picks.csv` (columns `qid`, `commons_file`, `decision`), one row per building's Wikidata item, naming a file on Wikimedia Commons. The rules for choosing a photo are in the comment at the top of `pipeline/s06_wiki.py`, which reads the table.

Open a pull request editing the file, or an issue with the building, the detail and your source if you'd rather not edit code.

## Helping with history

Useful help:

- sources for past events in the city, such as fires, demolitions and new districts;
- georeferenced old maps;
- footprints of lost buildings;
- fact-checks of dates and claims already on the map.

**Licence rules.** Maps and views must be in the public domain; data must be CC BY or CC0. Cite everything: the publisher, the title and a link.

Open a **New data source** issue describing what you have, with its link and licence.

### Adding a history story

A story is a short camera tour of a past event, kept as CSV files in one folder under [`scenes/`](https://github.com/amirelion/husforhus/tree/main/scenes). Copy the 1912 Olympics story (`scenes/s10-olympics-1912`) and work through this checklist; the full version is in [`scenes/README.md`](https://github.com/amirelion/husforhus/blob/main/scenes/README.md).

- **Sourced beats** in English and Swedish: a short caption per beat, every fact with its source.
- **Lost buildings** in `ghosts.csv`, each with the map or source its shape comes from and a confidence (high, medium or low).
- **Cameras that frame the action**: the subject whole and in the middle of the screen, seen from above, on a computer and a phone.
- **Period photos on 3–5 beats** where they exist: photographs, paintings, engravings or maps from Wikimedia Commons, with a short caption in both languages saying what the image shows and its date. Present-day photos only where the beat is about today.
- **Licences checked**: public domain, CC0, CC BY or CC BY-SA only, never NC, ND or fair use. Note each file's licence, author and the date you checked in the story's `README.md`.
- **Screenshots of every beat**, on a computer and a phone, in your pull request.

## Translations and code

- **Translations.** The whole interface's strings live in `web/i18n/en.json` and `web/i18n/sv.json`, by the same ids in both. Open a pull request fixing a string or adding a language file.
- **What's new.** A release that changes what a visitor sees adds an entry to `web/news.json` in both languages, newest first: what a visitor can now do or see, in one to three plain sentences, without version strings or other internal names. [`CHANGELOG.md`](CHANGELOG.md) keeps the full detail.
- **Search names.** The everyday names search knows for districts and landmarks ("Söder", "Slottet", "City Hall") are `DISTRICT_ALIASES` and `BUILDING_ALIASES` in `pipeline/city.py`. A name can point only at a district or a building whose card already carries the target name, never at a private house.
- **Code.** Fixes are welcome as pull requests; please include a test and run the checks above.

## Adding a new city

The code was built as a port, with everything city-specific kept in a thin layer, so a new city follows the same path. Expect real work: most of it is finding and joining the city's data.

1. **Find the data.** You need open building footprints with heights (ideally a 3D or LOD1 dataset), and at least one openly licensed source of construction years that joins onto them. Floors, terrain and a base map help. Check every licence allows reuse; see [Data sources](DATA-SOURCES.md) for the credit form.
2. **Write the city layer.** Copy `pipeline/city.py` and set the city's coordinate system, origin, bounds, home view, periods with their colours, building types, private-house types and estimate settings. The viewer reads the generated city JSON, so it needs no city-specific code.
3. **Write the adapters.** Replace the `s00_fetch_*` steps and the year sources in `s02_years` with ones for your data, and list each source in `pipeline/sources.yml`.
4. **Choose a fixture area.** A small, well-dated area (`FIXTURE_BBOX`) lets `HFH_FIXTURE=1` build quickly in tests.
5. **Measure before you estimate.** Run the accuracy report (`uv run python -m pipeline.report_accuracy`) and estimate only where it shows the method works for your city. Leave the rest unknown.

Open an issue early to say which city you are working on and what data you have found; it saves duplicate work and we can point you to the parts that differ.

## Licence

By contributing you agree that your code is released under the project's MIT licence. Data you add must be openly licensed and credited.
