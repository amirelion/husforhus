# Changelog

What changed on [husforhus.se](https://husforhus.se), newest first: the map's features and the data behind it. Each data build has a version (shown in About), such as `v20261017-p4i`.

## Planned

Plans, not promises: the order can change.

- **More history stories.** The clearance of Klara (1952–1977), and more about Tunnelbanan: the blue line and Järvafältet; Kymlinge, the station that never opened.
- **Narration** for the history stories, in English and Swedish.
- **More blue plaques** when Samfundet S:t Erik publishes its updated plaque list, and a second look at the 37 plaques not yet placed on a building.
- **Finer ground.** Lantmäteriet's 1 m elevation model instead of the City's contour lines, which also fixes about 130 buildings that stand on too-tall pedestals.

## 2026-10-17: launch day

### Features
- **The map is public** at husforhus.se, in English and Swedish (Swedish for Swedish browsers), with no cookies and no tracking.
- **Search** for a street, an address, a named building, a district, or what is inside a building ("Nobel" finds the Nobel Prize Museum in Börshuset).
- **History stories** (Berättelser), eight of them: the great fire of 1625; the Vasa sinks, 1628; Queen Kristina's lock, 1637–1642 (and the locks that followed it at Slussen); Tre Kronor burns, 1697; the Stockholm Olympics, 1912; the Stockholm Exhibition, 1930; the first metro, 1950; Vällingby, a town built around its station, 1950–1954. The metro stories show the lines as they open. Today's city is drawn faintly for orientation and the lost buildings in sandstone, with period photos and sources on every step.
- **Tunnelbanan** as a legend switch: the green, red and blue lines grow with the timeline from 1950, and every station has a card with its opening date and earlier names.
- **Blue plaques** as a legend switch: 127 of Samfundet S:t Erik's plaques, with their Swedish texts on the cards.
- **Real tower heights** for 189 buildings, from Lantmäteriet's laser data: Stadshuset 103 m, Kaknästornet 139 m, Klara kyrka 95 m, the Gamla stan churches, Hötorgscity, DN-skrapan, Folksamhuset and more, instead of flat blocks, and a Tower row on their cards. About 3,100 buildings were checked; one that changed since the 2021 scan keeps its old height.
- **Highlight buildings with a photo**: a legend switch that turns the others pale.
- **Share a building**: a link that opens its card, or the phone's share sheet.
- **Phones and accessibility**: 44-pixel tap targets, the whole interface by keyboard, and screen-reader labels; a smaller build of the 3D library (about 220 KB less to download on a first visit).
- A link to the source code in About, and issue forms on GitHub for corrections, photos, data sources and translations.

### Data
- Data versions `v20261017-p4c` to `v20261017-p4k`.
- 77 public institutions inside buildings, from Wikidata, for search.
- Samfundet S:t Erik's plaque list and texts (CC BY 4.0), placed by address and by Open Plaques positions.
- Tunnelbanan: 101 stations (Wikidata) and 32 dated line sections on OpenStreetMap's track.
- Lantmäteriet's Laserdata Nedladdning, skog (CC BY 4.0, scanned 2020–2021) for the towers: points read only around about 3,100 candidate buildings.
- Period photos for the stories from Wikimedia Commons, public domain or CC licences only, each checked by hand.

## 2026-10-14 to 2026-10-16: before launch

- The 3D map of all 77,743 buildings in Stockholm municipality, coloured by construction year, ported from [Amsterdam, building by building](https://github.com/alexbarakov/amsterdam-by-building).
- Years from RAÄ's building registers, area years, a hand-checked landmark list, Wikidata and OpenStreetMap; estimates for houses only where a test showed they work; "Year unknown" for the rest. See [How the years work](HOW-YEARS-WORK.md).
- The timeline and its film, twelve periods, the Floors view, four looks, the hills from the City's contour lines.
- Building cards with about 900 photos and Wikipedia excerpts, and the privacy rules for private houses (see [Privacy](PRIVACY.md)).
