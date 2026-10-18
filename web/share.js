// "Share" on a pinned card: the link, stable across data rebuilds (gids are not). Pure, tested by node --test
// (web/test/share.test.mjs). The link carries only what the card shows: its name, else its first address (a
// private house: its address only, like its card), as ?q= when search finds that text back to the same building;
// otherwise ?at=<x>,<z>,<zoom> in the local frame, which app.js flies to and pins the building under.
export const SITE = 'https://husforhus.se/';

export const shareText = (card, b) => (b?.private ? card?.addr : card?.name || card?.addr) || '';

export function shareLink({ text, resolves, x, z, zoom }) {
  if (text && resolves) return `${SITE}?q=${encodeURIComponent(text)}`;
  return `${SITE}?at=${x.toFixed(1)},${z.toFixed(1)},${Math.round(zoom)}`;
}

export function parseAt(s) {
  const v = String(s ?? '').split(',').map(Number);
  if (v.length !== 3 || v.some(n => !Number.isFinite(n)) || v[2] <= 0) return null;
  return { x: v[0], z: v[1], zoom: v[2] };
}

// ?layer=<id>: a context layer by its id (ids are stable names in layers.json, unlike gids). Unknown ids give null.
export const findLayer = (layers, id) => (id && layers?.find(L => L.id === id)) || null;
