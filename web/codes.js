// Year, source, floors and rating codes: a mirror of pipeline/codes.py. web/test/codes.test.mjs
// fails when the two drift apart. yflag 5 is retired (it was DECADE): a private house keeps the yflag that says
// how its year is known and carries its own `private` flag in attrs.bin (tile.js readAttrs).
export const YFLAG = Object.freeze({ EXACT: 0, RANGE: 1, LONG: 2, AREA: 3, ESTIMATE: 4, PERIOD: 6, UNKNOWN: 7 });
export const YSRC = Object.freeze({ NONE: 0, CURATED: 1, RAA: 2, RAA_AREA: 3, WIKIDATA: 4, ESTIMATE: 5, RAA_OLD: 6, OSM: 7 });
export const FSRC = Object.freeze({ OSM: 0, HEIGHT: 1 });
// Stadsmuseet klassificering; 0 = not rated.
export const RATING = Object.freeze({ 'Blått': 1, 'Grönt': 2, 'Gult': 3 });
// Legal protection (RAÄ skyddstyp): 1 statligt byggnadsminne, 2 byggnadsminne, 3 kyrkligt kulturminne; 0 none.
export const PROT = Object.freeze({ NONE: 0, STATE: 1, LISTED: 2, CHURCH: 3 });
