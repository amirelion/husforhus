# Privacy

Hus för hus is a map of buildings, not of people. This page says what it shows about private homes, what the site does not collect, and how to ask for a correction or for a building to be taken off the map. The About panel on the site has the same information, in English and Swedish.

## What the map shows about private houses

Private houses are villas, row and chain houses and allotment cottages. For these:

- **The address is shown.** A private house's street address is on its card and search finds it. An address names no one.
- **The owner is never shown.** Nor are residents, or who had the house built. Sentences in Wikipedia texts that say who owns a building or had it built are cut out before the text reaches any card, and the build fails if one slips through.
- **Only the decade.** A private house shows the decade it was built ("1950s"), never the exact year, and gets no link to the heritage register's record.
- **Names only from reviewed lists.** A house's name, and an architect's name that appears on only a few buildings in the whole city, are shown only if a person has checked them and added them to `pipeline/private_names.txt` or `pipeline/private_firms.txt`.
- **No photo, excerpt or Wikipedia and Wikidata links**, unless the house is one of the hand-checked landmarks in `pipeline/landmarks.py`.

For every building, the map never shows property designations (fastighetsbeteckningar) or the registers' internal ids. See [How the years work](HOW-YEARS-WORK.md) for why private houses show only a decade.

## What the site does not collect

- **No cookies.** The site sets none.
- **No tracking.** There is no analytics or tracking script.
- **No accounts.** There is nothing to sign up for or log in to.
- **Your choices stay in your browser.** The map remembers the look, hills, language and the legend's settings in your browser's local storage. They are never sent anywhere.
- **No third-party requests.** The map, its data, its fonts and its photos are served from the site itself, so using it, including opening a card, contacts no other service. Links to the heritage register, Wikipedia, Wikidata, Wikimedia Commons and OpenStreetMap open those sites, which have their own privacy policies.

Like any website, the server that delivers the pages handles the technical details of each request, such as your IP address and browser.

## Corrections and takedowns

To report a mistake, or to ask for a building's details to be taken off the map, use the contact in the site's About panel. You do not need to say why. Please don't open a public issue about a private home.

A building taken off the map keeps its shape, its height and its district, and is shown as "Year unknown". Its year, name, architects, heritage rating, protection, addresses, links, photo and excerpt are removed at the next data update, so neither its card nor search shows them. The list of these buildings is not kept in this repository.

You can also complain to the Swedish Authority for Privacy Protection (IMY).
