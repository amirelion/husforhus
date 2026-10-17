// The look manager: which look (web/themes.js) the map wears, and the atmospheres that may one day play over it.
// app.js applies a look (applyLook) and web/switcher.js shows the choice; both subscribe here. Pure apart from the
// page's URL, history and localStorage, which are passed in, so it can be tested without a browser.
import { THEMES } from './themes.js';

// localStorage key for the viewer's last choice.
export const LOOK_KEY = 'hfh-look';
// Ärg. styles.css's :root tokens and pipeline/city.py's PERIODS colours are this look's, so the
// first paint, before this module runs, is already in it.
export const DEFAULT_LOOK = 'arg';

// The first look: ?theme= in the URL wins (a shared link shows what its sender saw), then the viewer's remembered
// choice, then Ärg. A name that is not a look (a dropped variant, "__proto__") falls through.
export function initialLook(search, stored, ids = Object.keys(THEMES)) {
  const q = new URLSearchParams(search).get('theme');
  if (ids.includes(q)) return q;
  if (ids.includes(stored)) return stored;
  return DEFAULT_LOOK;
}

// One choice out of a list of {id, name}, with change notifications; the looks and the atmospheres both use it.
// set() ignores an unknown id and the current one; subscribers hear (id, previous id).
function choice(items, first) {
  let current = first;
  const subs = new Set();
  return {
    items,
    get current() { return current; },
    set(id) {
      if (id === current || !items.some(it => it.id === id)) return false;
      const was = current;
      current = id;
      for (const fn of [...subs]) fn(id, was);
      return true;
    },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
}

// Atmospheres: effects over whichever look is on, such as snow, Halloween or Lucia. Each is one module that
// exports an object and is added with atmospheres.add():
//   { id: 'snow', name: 'Snow', start(ctx) { ... }, stop() { ... } }
// start(ctx) builds and shows the effect; ctx is atmospheres.context, what app.js lends an effect (the scene, the
// shared uniforms, the camera, the renderer, the look on now). stop() takes it away and disposes what it made.
// 'none' is the plain map. None are built yet: the switcher shows their row once there is one besides 'none'.
function atmospheres() {
  const a = choice([{ id: 'none', name: 'None' }], 'none');
  a.context = null;
  a.add = effect => { a.items.push(effect); };
  a.subscribe((id, was) => {
    a.items.find(e => e.id === was)?.stop?.();
    a.items.find(e => e.id === id)?.start?.(a.context);
  });
  return a;
}

const localStore = () => { try { return globalThis.localStorage ?? null; } catch { return null; } };

// The looks, by their shown names, starting on initialLook(). A switch is remembered and written into the URL
// (history.replaceState, the other parameters kept), so a reload or a shared link keeps it. Storage may be missing
// or throw (private windows, blocked site data): the looks then work for this visit only.
export function createLooks({ location = globalThis.location, history = globalThis.history, storage = localStore() } = {}) {
  let stored = null;
  try { stored = storage?.getItem(LOOK_KEY) ?? null; } catch {}
  const items = Object.entries(THEMES).map(([id, th]) => ({ id, name: th.name }));
  const looks = choice(items, initialLook(location?.search ?? '', stored));
  looks.subscribe(id => {
    try { storage?.setItem(LOOK_KEY, id); } catch {}
    const u = new URL(location.href);
    u.searchParams.set('theme', id);
    history.replaceState(null, '', u);
  });
  looks.atmospheres = atmospheres();
  return looks;
}
