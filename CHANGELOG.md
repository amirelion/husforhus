# Changelog

What changed on [husforhus.se](https://husforhus.se), newest first: the map's features and the data behind it. Each data build has a version (shown in About), such as `v20261017-p4i`.

## Planned

Plans, not promises: the order can change.

- **Old Klara traced from maps**, replacing the story's approximate blocks drawn on today's plots.
- **Narration** for the history stories, in English and Swedish.
- **More blue plaques** when Samfundet S:t Erik publishes its updated plaque list, and a second look at the 17 plaques not yet placed on a building (the other 17 unplaced are on bridges).
- **Finer ground.** Lantmäteriet's 1 m elevation model instead of the City's contour lines, which also fixes about 130 buildings that stand on too-tall pedestals.

## 2026-10-18

### Features
- **On a phone, the legend folds** when you touch the map or swipe its handle down, so the city is not half hidden.
- **Google Maps from a card**: a pin at the end of a pinned card's address line opens the building in Google Maps. Not on private houses.
- **Station cards** have the same margins as building cards (their text sat on the edge).
- **For search engines**: a structured description of the map, and a line for browsers without JavaScript.
- **Quests and walks, to try**: riddles around Gamla stan and walks past buildings with a story, adapted from Amsterdam, building by building. Off for now; `?try=quests,walks` switches them on for one visit.
- **Readers' reports become map data.** A checked report can date a building, choose its main address, name it or give it a photo; the card credits only "a reader's report" and its reference.
- **A report form.** "Something wrong?" on a card opens a form with the building as the card shows it: a wrong or missing year or detail, a photo of your own (shrunk and stripped of its location data in the browser, CC BY 4.0 with your name), or something else. About's Contact has "Suggest something". See [Privacy](PRIVACY.md) for what is kept and for how long.
- **The layer switches moved into Look**, under "Show on the map": Tunnelbanan, the blue plaques and the photo highlight. A dot on the Look button shows while one is on, and the legend is shorter.
- On a phone, a tap just under the Look button no longer opens About.
- **Story cards.** The Stories list shows each story's opening line, its length and number of steps, and a "Mentions deaths" tag on the stories that do; a story picked from the list starts without a second warning. When a story ends: "Replay story" or "Back to map".

### Data
- Data version `v20261018-p4n`: the quests' data and the walks' starting points.
- Data version `v20261018-p4m`: **the first reader's report on the map.** L.M. Ericssons väg 30 in Midsommarkransen, unknown until now, is dated 1938–1939 from construction photos a reader sent (HFH-3). Its card says so: "A reader's report (HFH-3), checked". Reports accepted from the form now reach the map this way, with no name or email.
- Data version `v20261018-p4l`.
- **More plaques on the right building**: 130 placed (was 127). The address is read more carefully (number ranges such as 18–24, house letters such as 50A, short street forms such as "g." and "St."), then the building's card name, and Open Plaques positions within 25 m. Five more plaques are placed, among them Hvita Björn and Mariebergs kollektivhus. Plaques from the list's bridge section are no longer put on a house nearby, which took two off the wrong buildings.
- **Globen**: two buildings of the arena complex no longer carry the name; the arena itself keeps its name, Avicii Arena, and search finds it as "Globen".

## 2026-10-17: launch day

### Features
- **The map is public** at husforhus.se, in English and Swedish (Swedish for Swedish browsers), with no cookies and no tracking.
- **Search** for a street, an address, a named building, a district, or what is inside a building ("Nobel" finds the Nobel Prize Museum in Börshuset).
- **History stories** (Berättelser), eleven of them: the great fire of 1625; the Vasa sinks, 1628; Queen Kristina's lock, 1637–1642 (and the locks that followed it at Slussen); Tre Kronor burns, 1697; the Stockholm Olympics, 1912; the Stockholm Exhibition, 1930; the first metro, 1950; Vällingby, a town built around its station, 1950–1954; the clearance of Klara, 1952–1977 (old Klara drawn approximately, on today's plots); the blue line and Järvafältet, 1975–1977; Kymlinge, the station that never opened. The metro stories show the lines as they open. Today's city is drawn faintly for orientation and the lost buildings in sandstone, with period photos and sources on every step.
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
