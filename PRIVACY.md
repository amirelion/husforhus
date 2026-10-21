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

- **No cookies.** The site sets none, and the report form adds none.
- **No tracking.** There is no analytics or tracking script.
- **No accounts.** There is nothing to sign up for or log in to.
- **Your choices stay in your browser.** The map remembers the look, weather, hills, language, the boats switch and the legend's settings in your browser's local storage. They are never sent anywhere.
- **No third-party requests.** The map, its data, its fonts and its photos are served from the site itself, so using it, including opening a card or sending the report form, contacts no other service. Links to the heritage register, Wikipedia, Wikidata, Wikimedia Commons, OpenStreetMap, KulturNav, the City of Stockholm and the City Museum's archive (Digitala Stadsmuseet) open those sites, which have their own privacy policies.

Like any website, the server that delivers the pages handles the technical details of each request, such as your IP address and browser.

## The report form

A card's "Something wrong?" and About's "Suggest something" open a form. Sending it is the only way the site receives anything from you.

- **What it stores.** Your message, your email address, the kind of report, the language of the page and, from a card, the building it was about as the card showed it (its name or address, district, year, source line, its id in the map's data and the data version). If you add a photo: the photo, the name to credit it with, and your two confirmations (that it is your own, and that you license it under CC BY 4.0).
- **Why.** To answer you and to fix the map. The email address is used only to write back to you about your report.
- **What it does not store.** Your IP address. To stop abuse, at most five reports an hour are accepted from one connection; the count is kept by a salted hash of the address, in memory only, and forgotten after an hour.
- **Photos.** The page shrinks a photo to at most 2048 pixels and re-encodes it, which removes its location and camera data, before sending; the server refuses a JPEG that still has them. A private house's card offers no upload. A photo is used under the licence you grant, CC BY 4.0, credited with the name you give.
- **How long.** Your email address is deleted twelve months after your report is closed; the rest of the report is kept as a record of the correction.
- **What is published.** Some reports become a public issue on the project's GitHub, with the kind, the building and the message, and the photo only if the maintainer chooses to include it. Nothing published ever includes your email address.
- **When a report changes the map.** If the maintainer checks your report and accepts it, the change (a year, an address, a name or your photo) goes into the map's data and the building's card credits it only as "a reader's report (HFH-&lt;number&gt;)" with the maintainer's one-line note on how it was checked. Your name and email address are never part of the data. A photo keeps the credit you gave it, under CC BY 4.0. A private house never takes a name or a photo from a report.
- **No cookies.** The form adds none, and sends nothing to any other service.

The reports are stored with the site's host, Cloudflare (a database and a storage bucket), and only the maintainer can read them.

## Corrections and takedowns

To report a mistake, or to ask for a building's details to be taken off the map, use "Something wrong?" on the building's card, or the contact in the site's About panel. You do not need to say why. Please don't open a public issue about a private home.

A building taken off the map keeps its shape, its height and its district, and is shown as "Year unknown". Its year, name, architects, heritage rating, protection, addresses, links, photo and excerpt are removed at the next data update, so neither its card nor search shows them. The list of these buildings is not kept in this repository.

You can also complain to the Swedish Authority for Privacy Protection (IMY).
