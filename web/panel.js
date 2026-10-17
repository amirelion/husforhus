// The legend panel's remembered state. Pure, so it can be tested without a browser.

// localStorage key for the viewer's last choice: 'collapsed' or 'open'.
export const LEGEND_KEY = 'hfh-legend';

// Should the legend start collapsed? A stored choice wins. Without one, phones (a bottom sheet) and narrow
// desktops (the panel would cover too much of the map) start collapsed; wide desktops start open.
export function initialCollapsed({ stored, phone, wide }) {
  if (stored === 'collapsed') return true;
  if (stored === 'open') return false;
  return Boolean(phone) || !wide;
}

// The "Highlight buildings with a photo" switch: kept in the URL (?photos=1), as the look is (web/look.js), so a reload or a
// shared link keeps it.
export const PHOTO_PARAM = 'photos';
export const photoOnlyFrom = search => new URLSearchParams(search).get(PHOTO_PARAM) === '1';
export function photoOnlyHref(href, on) {
  const u = new URL(href);
  if (on) u.searchParams.set(PHOTO_PARAM, '1'); else u.searchParams.delete(PHOTO_PARAM);
  return u.toString();
}

// The per-building flag the shader reads (float 9 of ATTR_FLOATS = 12, web/worker.js; float 3 is the gid): 1 for a
// building whose card has a photo. Written once per tile, when it loads or when the list arrives, never per frame.
export const PHOTO_FLOAT = 9;
export function markPhotos(attr, nB, gids, floats = 12) {
  let n = 0;
  for (let b = 0; b < nB; b++) {
    const on = gids.has(attr[b * floats + 3]) ? 1 : 0;
    attr[b * floats + PHOTO_FLOAT] = on;
    n += on;
  }
  return n;
}
