"""Curated landmark seed: buildings whose year we state ourselves, each cited to a Wikipedia article.

The curated tier outranks RAÄ: RAÄ dates Stockholms slott to 1170–1199, the origin of
the site, while the palace standing today was completed in 1754.

Each entry:
  name       display name, and the timeline label when `timeline` is set (Swedish in both languages)
  qid        Wikidata item of the building itself, or "" when the building has none (a Gamla stan house cited to its
             kvarter article): then `point` is required, and the footprint keeps the item the rules place on it
  lat, lon   WGS84, copied from the item's P625 (coordinate location), unless `point` says why and where from
  year       the year shown (completion or inauguration)
  year_from  first year of construction
  year_to    last year of construction; year_from <= year <= year_to
  source     "<lang>:<article title>" on sv or en Wikipedia that states those years
  checks     strings that article must contain (s08_landmarks verifies them before s02_years reads the entry)
  timeline   optional: a priority (1 first) that puts the name on the timeline at `year`. Only an entry whose year
             the article states exactly gets one (never "c. 1292"), and never a private house.
  rebuilt    optional: [(year, kind), ...], the card's second line (§14 of the Gamla stan research): kind "rebuilt"
             (rebuilt or altered as a whole; "ombyggt"), "raised" (storeys added; "påbyggt") or "extended" (a wing or
             an addition built on; "tillbyggt"). Each year comes after year_to, by 2026, and is written in one of the
             checks, so the article is checked for it. A rebuild never sets the year or the colour; new façades,
             conversions and renovations get no line.
  cellars    optional: True when the article says the standing building was built from new on older cellar walls.
             The year stays the building's own; the card's dating line says so.
  point      optional: {"reason": ..., "source": ...}, a hand-checked point: why the item's P625 is not the building
             the year belongs to, and the research row, article or map that shows where it is. The entry's comment
             repeats the reason. The point must still place within 15 m (below); it never ships.

s02_years places each point on a LOD1 footprint (inside it or inside its outer ring, so a courtyard
point counts, else the nearest footprint within 15 m) and reports any entry it cannot place.
"""

# A Gamla stan house cited to its kvarter article that has no Wikidata item (qid ""): its point is the research's,
# inside the footprint the research matched to the house by its address, its KulturNav point or its property
# (the fact-check found each inside its footprint), so no P625 confirms it. A house that has an item (most made from
# its KulturNav entry) takes the item and its P625 like any other entry.
NO_ITEM = {"reason": "the building has no Wikidata item: a point inside the footprint the research matched to the "
                     "house",
           "source": "docs/research/2026-10-16-gamla-stan-years.csv, the house's row, and the placement table of "
                     "docs/research/2026-10-16-verify-gamla-placement.md"}

LANDMARKS = [
    {
        "name": "Riddarholmskyrkan", "qid": "Q657118", "lat": 59.324722222222, "lon": 18.064722222222,
        "year": 1292, "year_from": 1280, "year_to": 1300, "source": "sv:Riddarholmskyrkan",
        "checks": ("1292", "1280–1300", "äldsta bevarade byggnad"),
    },
    {
        "name": "Storkyrkan", "qid": "Q1133075", "lat": 59.325833333333, "lon": 18.070555555556,
        "year": 1306, "year_from": 1306, "year_to": 1306, "source": "sv:Storkyrkan",
        "checks": ("invigdes 1306",), "timeline": 1,
    },
    {
        "name": "Klara kyrka", "qid": "Q1540683", "lat": 59.33111111, "lon": 18.06166667, "year": 1590,
        "year_from": 1572, "year_to": 1590, "source": "sv:Klara kyrka", "checks": ("uppfördes 1572–1590",),
        "timeline": 4,
    },
    {
        "name": "Förgyllda Lejonet", "qid": "Q136354189", "lat": 59.324114, "lon": 18.071101, "year": 1636,
        "year_from": 1636, "year_to": 1636, "source": "sv:Kvarteret Atlas", "checks": ("1636", "1625"),
    },
    {
        "name": "Tyska kyrkan", "qid": "Q2164087", "lat": 59.324166666667, "lon": 18.071666666667,
        "year": 1642, "year_from": 1638, "year_to": 1642, "source": "sv:Tyska kyrkan, Stockholm",
        "checks": ("1638–1642", "invigningen ägde rum 1642"), "timeline": 2,
    },
    {
        "name": "Lilla Nygatan 5", "qid": "", "lat": 59.324433, "lon": 18.067865, "year": 1647, "year_from": 1642,
        "year_to": 1647, "source": "sv:Kvarteret Tritonia", "checks": ("1642", "1647", "1937"),
        "rebuilt": [(1937, "rebuilt")], "point": NO_ITEM,
    },
    {
        "name": "Stora Nygatan 32", "qid": "Q136354726", "lat": 59.323871, "lon": 18.069621, "year": 1651,
        "year_from": 1651, "year_to": 1651, "source": "sv:Kvarteret Pyramus", "checks": ("1651", "1780", "1912"),
        "rebuilt": [(1780, "raised")],
    },
    {
        "name": "Stora Nygatan 35", "qid": "", "lat": 59.323745, "lon": 18.070248, "year": 1651, "year_from": 1636,
        "year_to": 1651, "source": "sv:Kvarteret Cybele", "checks": ("1636", "1651", "1751", "1946", "1970"),
        "rebuilt": [(1751, "rebuilt")], "point": NO_ITEM,
    },
    {
        "name": "Riddarhuset", "qid": "Q1547268", "lat": 59.32593, "lon": 18.06573,
        "year": 1674, "year_from": 1641, "year_to": 1674, "source": "sv:Riddarhuspalatset",
        "checks": ("1641–1674",), "timeline": 2,
    },
    {
        "name": "Katarina kyrka", "qid": "Q1736102", "lat": 59.317083, "lon": 18.078056, "year": 1695,
        "year_from": 1656, "year_to": 1695, "source": "sv:Katarina kyrka",
        "checks": ("1656–1695", "18 oktober 1724", "1995"), "rebuilt": [(1724, "rebuilt"), (1995, "rebuilt")],
        "timeline": 4,
    },
    {
        "name": "Klockstapeln, Bromma kyrka", "qid": "Q10546403", "lat": 59.356111, "lon": 17.9225, "year": 1695,
        "year_from": 1692, "year_to": 1695, "source": "sv:Klockstapeln, Bromma kyrka", "checks": ("1692-1695",),
    },
    {
        "name": "Helledayska huset", "qid": "", "lat": 59.323927, "lon": 18.070201, "year": 1740, "year_from": 1740,
        "year_to": 1740, "source": "sv:Kvarteret Cybele", "checks": ("1740", "1887"), "point": NO_ITEM,
    },
    {
        "name": "Västerlånggatan 38", "qid": "", "lat": 59.324378, "lon": 18.069637, "year": 1740, "year_from": 1740,
        "year_to": 1740, "source": "sv:Kvarteret Pandora", "checks": ("1740", "1897"), "point": NO_ITEM,
    },
    {
        "name": "Kornhamnstorg 57", "qid": "Q136354297", "lat": 59.322643, "lon": 18.071968, "year": 1741,
        "year_from": 1741, "year_to": 1741, "source": "sv:Kvarteret Deucalion", "checks": ("1741", "1620"),
    },
    {
        "name": "Buckauska huset", "qid": "", "lat": 59.322975, "lon": 18.070323, "year": 1750, "year_from": 1750,
        "year_to": 1750, "source": "sv:Kvarteret Cerberus", "checks": ("1750", "1855-65"), "point": NO_ITEM,
    },
    {
        "name": "Stora Nygatan 5", "qid": "", "lat": 59.325258, "lon": 18.067855, "year": 1752, "year_from": 1752,
        "year_to": 1752, "source": "sv:Kvarteret Pyreneus", "checks": ("1752", "1748", "1878", "1876"),
        "rebuilt": [(1878, "raised")], "point": NO_ITEM,
    },
    {
        "name": "Västerlånggatan 18", "qid": "", "lat": 59.325406, "lon": 18.06858, "year": 1753, "year_from": 1753,
        "year_to": 1753, "source": "sv:Kvarteret Pyreneus", "checks": ("1753", "1870"),
        "point": NO_ITEM,
    },
    {
        "name": "Stockholms slott", "qid": "Q750444", "lat": 59.326666666667, "lon": 18.071666666667,
        "year": 1754, "year_from": 1697, "year_to": 1754, "source": "sv:Stockholms slott",
        "checks": ("1697", "1754"), "timeline": 1,
    },
    {
        "name": "Stora Nygatan 38", "qid": "", "lat": 59.323562, "lon": 18.069954, "year": 1762, "year_from": 1762,
        "year_to": 1762, "source": "sv:Kvarteret Pyramus", "checks": ("1762",), "point": NO_ITEM,
    },
    {
        "name": "Stora Nygatan 27", "qid": "", "lat": 59.324153, "lon": 18.069581, "year": 1771, "year_from": 1771,
        "year_to": 1771, "source": "sv:Kvarteret Cybele", "checks": ("1771",), "point": NO_ITEM,
    },
    {
        "name": "Stora Nygatan 13", "qid": "", "lat": 59.324909, "lon": 18.068446, "year": 1780, "year_from": 1779,
        "year_to": 1780, "source": "sv:Kvarteret Pomona", "checks": ("1779–1780", "1400-talet"), "cellars": True,
        "point": NO_ITEM,
    },
    {
        "name": "Forsströmska huset", "qid": "", "lat": 59.32223, "lon": 18.072711, "year": 1781, "year_from": 1781,
        "year_to": 1781, "source": "sv:Kvarteret Medusa", "checks": ("1781", "1877-1878", "1896"), "point": NO_ITEM,
    },
    {
        "name": "Lilla Blecktornet", "qid": "Q31871398", "lat": 59.308889, "lon": 18.087222, "year": 1787,
        "year_from": 1787, "year_to": 1787, "source": "sv:Lilla Blecktornet", "checks": ("1787",),
    },
    {
        "name": "Arvfurstens palats", "qid": "Q717105", "lat": 59.329167, "lon": 18.067778, "year": 1794,
        "year_from": 1783, "year_to": 1794, "source": "sv:Arvfurstens palats", "checks": ("1783", "1794", "1651"),
        "timeline": 5,
    },
    {
        "name": "Västerlånggatan 20", "qid": "", "lat": 59.325354, "lon": 18.068852, "year": 1817, "year_from": 1817,
        "year_to": 1817, "source": "sv:Kvarteret Erisichton", "checks": ("1817", "1888", "1889"), "point": NO_ITEM,
    },
    {
        "name": "Skeppsholmskyrkan", "qid": "Q1785830", "lat": 59.326388888, "lon": 18.0825, "year": 1842,
        "year_from": 1824, "year_to": 1842, "source": "sv:Skeppsholmskyrkan",
        "checks": ("påbörjades 1824", "24 juli 1842"), "timeline": 5,
    },
    {
        "name": "Kastellet", "qid": "Q4176816", "lat": 59.32263889, "lon": 18.09027778, "year": 1848, "year_from": 1846,
        "year_to": 1848, "source": "sv:Kastellet, Stockholm", "checks": ("mellan 1846 och 1848",), "timeline": 5,
    },
    {
        "name": "Mälartorget 13", "qid": "Q136354594", "lat": 59.323346, "lon": 18.068551, "year": 1860,
        "year_from": 1858, "year_to": 1860, "source": "sv:Kvarteret Midas", "checks": ("1858–1860",),
    },
    {
        "name": "Utrikespolitiska Institutets Bibliotek", "qid": "Q136354902", "lat": 59.323259, "lon": 18.069729,
        "year": 1860, "year_from": 1860, "year_to": 1860, "source": "sv:Kvarteret Pan",
        "checks": ("1860", "1890-talet"),
    },
    {
        "name": "Bromma kyrkskola", "qid": "Q10436027", "lat": 59.355797, "lon": 17.919731, "year": 1864,
        "year_from": 1862, "year_to": 1864, "source": "sv:Bromma kyrkskola", "checks": ("1864",),
    },
    {
        "name": "Nationalmuseum", "qid": "Q10594801", "lat": 59.32849, "lon": 18.07829, "year": 1866, "year_from": 1847,
        "year_to": 1866, "source": "sv:Nationalmuseum (byggnad)", "checks": ("Redan 1847", "15 juni 1866"),
        "timeline": 4,
    },
    {
        "name": "Östermalms saluhall", "qid": "Q298475", "lat": 59.335972222, "lon": 18.078083333, "year": 1888,
        "year_from": 1888, "year_to": 1888, "source": "sv:Östermalms saluhall", "checks": ("30 november 1888",),
        "timeline": 5,
    },
    {
        "name": "Österlånggatan 14", "qid": "Q31866837", "lat": 59.324711, "lon": 18.07385, "year": 1889,
        "year_from": 1888, "year_to": 1889, "source": "sv:Kvarteret Perseus", "checks": ("1888—1889",),
    },
    {
        "name": "Roslagstulls sjukhus", "qid": "Q10657114", "lat": 59.352778, "lon": 18.058611, "year": 1893,
        "year_from": 1890, "year_to": 1893, "source": "sv:Roslagstulls sjukhus",
        "checks": ("18 september 1893", "28 mars 1890"),
    },
    # P625 and the article's coordinate fall on Gasklocka 2 (1900); the point is inside Gasklocka 1, the 1893 plant
    {
        "name": "Värtagasverket", "qid": "Q10717747", "lat": 59.357295, "lon": 18.089855, "year": 1893,
        "year_from": 1890, "year_to": 1893, "source": "sv:Värtagasverket",
        "checks": ("1 april 1890", "6 november 1893"),
        "point": {"reason": "P625 and the article's coordinate fall on Gasklocka 2 (1900); the 1893 year belongs to "
                            "Gasklocka 1",
                  "source": "docs/research/2026-10-16-landmark-years.csv, Värtagasverket's notes"},
    },
    {
        "name": "Mosebacke vattentorn", "qid": "Q10589503", "lat": 59.317944, "lon": 18.075194, "year": 1896,
        "year_from": 1896, "year_to": 1896, "source": "sv:Mosebacke vattentorn", "checks": ("1896",),
    },
    {
        "name": "Kungliga Operan", "qid": "Q118463941", "lat": 59.329722222222, "lon": 18.070555555556,
        "year": 1898, "year_from": 1892, "year_to": 1898, "source": "sv:Kungliga Operan",
        "checks": ("1892", "19 september 1898"), "timeline": 2,
    },
    {
        "name": "Österlånggatan 17", "qid": "", "lat": 59.325116, "lon": 18.074095, "year": 1902, "year_from": 1902,
        "year_to": 1902, "source": "sv:Kvarteret Diana", "checks": ("1902",), "point": NO_ITEM,
    },
    {
        "name": "Högloftet och Nyloftet", "qid": "Q18290837", "lat": 59.32765, "lon": 18.1077, "year": 1905,
        "year_from": 1904, "year_to": 1905, "source": "sv:Högloftet och Nyloftet", "checks": ("1904–1905", "1925"),
        "rebuilt": [(1925, "extended")],
    },
    {
        "name": "Nordiska museet", "qid": "Q102246855", "lat": 59.32916667, "lon": 18.09333333,
        "year": 1907, "year_from": 1889, "year_to": 1907, "source": "sv:Nordiska museet",
        "checks": ("1889 och 1907",), "timeline": 3,
    },
    {
        "name": "Bällstalundsskolan", "qid": "Q10438495", "lat": 59.361944, "lon": 17.939167, "year": 1912,
        "year_from": 1912, "year_to": 1912, "source": "sv:Bällstalundsskolan", "checks": ("1912", "1935"),
        "rebuilt": [(1935, "extended")],
    },
    {
        "name": "Fasta paviljongen", "qid": "Q10494280", "lat": 59.322189, "lon": 18.026925, "year": 1915,
        "year_from": 1914, "year_to": 1915, "source": "sv:Fasta paviljongen, Långholmen", "checks": ("1914", "1915"),
    },
    {
        "name": "Långbrodalsskolan", "qid": "Q10572549", "lat": 59.276667, "lon": 17.988611, "year": 1915,
        "year_from": 1914, "year_to": 1915, "source": "sv:Långbrodalsskolan", "checks": ("1914–1915",),
    },
    {
        "name": "Stockholms stadshus", "qid": "Q648483", "lat": 59.3275, "lon": 18.054722,
        "year": 1923, "year_from": 1911, "year_to": 1923, "source": "sv:Stockholms stadshus",
        "checks": ("1911–1923", "23 juni 1923"), "timeline": 1,
    },
    {
        "name": "KTH-huset", "qid": "Q10658837", "lat": 59.349494, "lon": 18.070836, "year": 1927, "year_from": 1927,
        "year_to": 1927, "source": "sv:Röda Korsets sjukhus", "checks": ("1927", "5 september 1927"),
    },
    {
        "name": "Folkoperan", "qid": "Q5464597", "lat": 59.318461, "lon": 18.058339, "year": 1928, "year_from": 1928,
        "year_to": 1928, "source": "sv:Folkoperan", "checks": ("1928", "1976"),
    },
    {
        "name": "Stockholms stadsbibliotek", "qid": "Q1246991", "lat": 59.34333333, "lon": 18.05472222,
        "year": 1928, "year_from": 1924, "year_to": 1928, "source": "en:Stockholm Public Library",
        "checks": ("construction began in 1924", "31 March 1928"), "timeline": 2,
    },
    {
        "name": "Ålstensskolan", "qid": "Q10726494", "lat": 59.325278, "lon": 17.957222, "year": 1929,
        "year_from": 1928, "year_to": 1929, "source": "sv:Ålstensskolan", "checks": ("1929", "1928"),
    },
    {
        "name": "Olovslundsskolan", "qid": "Q10609300", "lat": 59.331944, "lon": 17.938056, "year": 1931,
        "year_from": 1931, "year_to": 1931, "source": "sv:Olovslundsskolan", "checks": ("31 augusti 1931",),
    },
    {
        "name": "Enskedefältets skola", "qid": "Q90200257", "lat": 59.282944, "lon": 18.068694, "year": 1933,
        "year_from": 1933, "year_to": 1933, "source": "sv:Enskedefältets skola", "checks": ("1933", "1947"),
        "rebuilt": [(1947, "extended")],
    },
    {
        "name": "Själagårdsgatan 13", "qid": "Q136354182", "lat": 59.324461, "lon": 18.073052, "year": 1936,
        "year_from": 1936, "year_to": 1936, "source": "sv:Kvarteret Andromeda", "checks": ("1933", "1936"),
        "cellars": True,
    },
    {
        "name": "Tekniska museet", "qid": "Q177550", "lat": 59.3325, "lon": 18.118611, "year": 1936, "year_from": 1936,
        "year_to": 1936, "source": "sv:Tekniska museet", "checks": ("1936", "1923", "utökades ytterligare 1994"),
        "rebuilt": [(1994, "extended")], "timeline": 4,
    },
    {
        "name": "Eriksdalsskolan", "qid": "Q10487739", "lat": 59.308142, "lon": 18.063303, "year": 1938,
        "year_from": 1937, "year_to": 1938, "source": "sv:Eriksdalsskolan", "checks": ("1937–1938",),
    },
    {
        "name": "Själagårdsgatan 15", "qid": "Q136354181", "lat": 59.324234, "lon": 18.073029, "year": 1939,
        "year_from": 1939, "year_to": 1939, "source": "sv:Kvarteret Andromeda", "checks": ("1939",),
    },
    {
        "name": "Järntorgsgatan 5", "qid": "", "lat": 59.322272, "lon": 18.073492, "year": 1940, "year_from": 1939,
        "year_to": 1940, "source": "sv:Kvarteret Cadmus", "checks": ("1939-40",), "point": NO_ITEM,
    },
    {
        "name": "Skogskrematoriet", "qid": "Q10670368", "lat": 59.27620833, "lon": 18.10094167, "year": 1940,
        "year_from": 1940, "year_to": 1940, "source": "sv:Skogskrematoriet", "checks": ("21 juni 1940",), "timeline": 5,
    },
    {
        "name": "Södra Ängby skola", "qid": "Q22276614", "lat": 59.344844, "lon": 17.892139, "year": 1946,
        "year_from": 1946, "year_to": 1946, "source": "sv:Södra Ängby skola", "checks": ("1946",),
    },
    {
        "name": "Wenner-Gren Center", "qid": "Q178863", "lat": 59.35111111, "lon": 18.04861111, "year": 1961,
        "year_from": 1959, "year_to": 1961, "source": "sv:Wenner-Gren Center", "checks": ("1959-1961",), "timeline": 5,
    },
    {
        "name": "DN-skrapan", "qid": "Q9200752", "lat": 59.32805556, "lon": 18.01611111, "year": 1964,
        "year_from": 1960, "year_to": 1964, "source": "sv:DN-skrapan",
        "checks": ("1960 till 1964", "24 september 1964"), "timeline": 5,
    },
    {
        "name": "Kaknästornet", "qid": "Q1721899", "lat": 59.335, "lon": 18.126388888889,
        "year": 1967, "year_from": 1963, "year_to": 1967, "source": "sv:Kaknästornet",
        "checks": ("1963", "12 maj 1967"), "timeline": 2,
    },
    {
        "name": "Bromma sjukhus", "qid": "Q124609324", "lat": 59.358278, "lon": 17.900056, "year": 1971,
        "year_from": 1971, "year_to": 1971, "source": "sv:Bromma sjukhus", "checks": ("1971",),
    },
    {
        "name": "Arrheniuslaboratoriet", "qid": "Q10418460", "lat": 59.365278, "lon": 18.058889, "year": 1973,
        "year_from": 1973, "year_to": 1973, "source": "sv:Arrheniuslaboratoriet", "checks": ("1973",),
    },
    {
        "name": "Kulturhuset", "qid": "Q204298", "lat": 59.33194444, "lon": 18.06472222, "year": 1974,
        "year_from": 1971, "year_to": 1974, "source": "sv:Kulturhuset, Stockholm",
        "checks": ("första etapp öppnades 1971", "invigt 1974", "togs i drift år 1974"),
        "timeline": 4,
    },
    {
        "name": "Avicii Arena", "qid": "Q32926", "lat": 59.29361111111111, "lon": 18.083333333333332,
        "year": 1989, "year_from": 1986, "year_to": 1989, "source": "sv:Globen",
        "checks": ("september 1986", "19 februari 1989"), "timeline": 1,
    },
    {
        "name": "Prins Bertils boulehall", "qid": "Q60970859", "lat": 59.328083, "lon": 18.115383, "year": 1989,
        "year_from": 1989, "year_to": 1989, "source": "sv:Prins Bertils boulehall",
        "checks": ("1989", "22 februari 1989"),
    },
    {
        "name": "Vasamuseet", "qid": "Q901371", "lat": 59.32807, "lon": 18.09139,
        "year": 1990, "year_from": 1987, "year_to": 1990, "source": "en:Vasa Museum",
        "checks": ("1987", "15 June 1990"), "timeline": 3,
    },
    {
        "name": "Sätra pistolskyttebana", "qid": "Q88563883", "lat": 59.288514, "lon": 17.931444, "year": 1995,
        "year_from": 1984, "year_to": 1995, "source": "sv:Sätra pistolskyttebana", "checks": ("1984", "1995"),
    },
    {
        "name": "Clarion Hotel Stockholm", "qid": "Q10454566", "lat": 59.30727222, "lon": 18.07486389, "year": 2003,
        "year_from": 2001, "year_to": 2003, "source": "sv:Clarion Hotel Stockholm",
        "checks": ("2001", "2003", "5 maj 2003"),
    },
    {
        "name": "Clarion Hotel Sign", "qid": "Q10454565", "lat": 59.3347, "lon": 18.05303611, "year": 2008,
        "year_from": 2008, "year_to": 2008, "source": "sv:Clarion Hotel Sign", "checks": ("5 februari 2008",),
        "timeline": 5,
    },
    {
        "name": "Abbamuseet", "qid": "Q19978145", "lat": 59.325, "lon": 18.096389, "year": 2013, "year_from": 2012,
        "year_to": 2013, "source": "sv:Abbamuseet", "checks": ("2012", "2013"), "timeline": 4,
    },
    # the item has no P625: the point is the article's title coordinate
    {
        "name": "Studenthuset, Stockholms universitet", "qid": "Q26253515", "lat": 59.362222, "lon": 18.058333,
        "year": 2013, "year_from": 2011, "year_to": 2013, "source": "sv:Studenthuset, Stockholms universitet",
        "checks": ("2013", "2011"),
        "point": {"reason": "the item has no P625: the point is the article's title coordinate",
                  "source": "sv:Studenthuset, Stockholms universitet (oldid 50035232), as "
                            "docs/research/2026-10-16-landmark-years.csv records"},
    },
    {
        "name": "Hägerstenshamnens skola", "qid": "Q60967510", "lat": 59.307381, "lon": 17.978478, "year": 2017,
        "year_from": 2016, "year_to": 2017, "source": "sv:Hägerstenshamnens skola", "checks": ("2016", "2017"),
    },
]
