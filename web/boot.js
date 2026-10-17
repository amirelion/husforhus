// A start-up guard, loaded as a classic script just before app.js. If the browser cannot fetch app.js or a module
// it imports, the module never runs and the page would stay at "Building the city 0%"; this says so instead, with
// the same words as app.js's loadFailed. A failed script load fires `error` at its <script>, which does not bubble,
// so the listener captures it on the window. A module that arrives but cannot run (a top-level throw, or syntax the
// browser cannot parse) reports on the window itself, with the module's address; that counts while nothing has
// loaded yet. A file, not an inline handler: the page's Content-Security-Policy allows scripts from its own address
// only (scripts/build_dist.py).
addEventListener('error', e => {
  const el = document.getElementById('loading');
  if (!el) return;
  const fetchFailed = e.target instanceof HTMLScriptElement;
  const runFailed = e.target === window && /^[^?#]*\.js([?#]|$)/.test(e.filename || '')
    && e.filename.startsWith(location.origin) && document.getElementById('progress')?.textContent === '0';
  if (!fetchFailed && !runFailed) return;
  el.hidden = false;
  el.textContent = swedish()
    ? 'Kunde inte ladda stadens data. Ladda om sidan för att försöka igen.'
    : 'Could not load the city data. Reload the page to try again.';
}, true);
// The page's language before any module has loaded: web/i18n.js pickLang's order, ?lang=, the visitor's
// saved choice, then the browser's first Swedish or English language.
function swedish() {
  try {
    const q = new URLSearchParams(location.search).get('lang');
    if (q === 'sv' || q === 'en') return q === 'sv';
    const s = localStorage.getItem('hfh-lang');
    if (s === 'sv' || s === 'en') return s === 'sv';
  } catch {}
  for (const l of navigator.languages || [navigator.language]) {
    const p = String(l || '').toLowerCase();
    if (p === 'sv' || p.startsWith('sv-')) return true;
    if (p === 'en' || p.startsWith('en-')) return false;
  }
  return false;
}
