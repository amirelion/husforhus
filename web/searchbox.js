// The search field (Plan 4b, Task 5; spec §4.4, §4.8): a combobox over web/search.js. On a desktop a pill beside the
// modes, "/" or Ctrl/⌘ + K to focus it; on a phone a button that opens a full-screen sheet. The index loads on the
// first focus, a street's numbers when an address is typed. ↑ ↓ move through the rows, Enter picks, Esc closes the
// list and a second Esc clears the field and gives the keyboard back to the map. Nothing typed is stored, and a pick
// never writes ?q= into the address bar (a home address would sit in the history).
import { prepare, search, rowText } from './search.js';

export function mountSearch({ root, openButton, getJson, base, T, onPick, swatch, isPhone, focusMap, buildings }) {
  const input = root.querySelector('input');
  const list = root.querySelector('[role="listbox"]');
  const msg = root.querySelector('.search-msg');
  const status = root.querySelector('.search-status');
  const clear = root.querySelector('.search-clear');
  const cancel = root.querySelector('.search-cancel');
  let P = null, loading = null, rows = [], active = -1, seq = 0, failed = false;
  let current = Promise.resolve();     // the latest run(): Enter waits for it, so it never picks an older query's row
  const shards = {};
  const loadShard = k => (shards[k] ??= getJson(`${base}addr/${k}.json`).catch(e => { delete shards[k]; throw e; }));

  function load() {
    loading ??= getJson(`${base}index.json`).then(index => { P = prepare(index); failed = false; return P; })
      .catch(e => { loading = null; failed = true; throw e; });
    return loading;
  }

  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function setOpen(open) {
    list.hidden = !open;
    input.setAttribute('aria-expanded', String(open));
  }
  function say(text) { status.textContent = text; }
  let shown = null;                    // what the message says: 'hint', a search's message, or null (redrawn by applyText)
  function showMessage(html) {
    msg.innerHTML = html;
    msg.hidden = !html;
    if (!html) shown = null;
  }
  // A search's message, with "Did you mean …?" as a button that runs the suggestion.
  function message(m) {
    if (!m) return showMessage('');
    const text = esc(T()(m.id, m.vars));
    showMessage(m.suggest
      ? text.replace(esc(m.suggest), `<button type="button" class="search-try" data-q="${esc(m.suggest)}">${esc(m.suggest)}</button>`)
      : text);
    shown = m;
  }
  // The keyboard is in the search (the field, ×, an example or the suggestion): the final review's F2 and F7.
  const inside = () => root.contains(document.activeElement);
  // The empty field: a few examples that exist in this build, and how much of the city has an address.
  function hint() {
    shown = 'hint';
    const t = T();
    if (!P) { showMessage(esc(t(failed ? 'search.failed' : 'search.loading'))); shown = 'hint'; return; }
    const chips = P.examples.map(e => `<button type="button" class="search-try" data-q="${esc(e)}">${esc(e)}</button>`).join(' · ');
    showMessage(`${chips ? `<b>${esc(t('search.try'))}</b> ${chips}<br>` : ''}${esc(t('search.coverage',
      { share: t.num(100 * P.addressed / Math.max(1, buildings), 0) }))}`);
    shown = 'hint';
  }
  function render() {
    const t = T();
    active = rows.length ? Math.min(Math.max(active, 0), rows.length - 1) : -1;
    list.innerHTML = rows.map((r, i) => {
      const { main, sub } = rowText(r, P, t);
      const sw = r.gid !== undefined ? `<i class="sw" style="background:${swatch(r.gid)}"></i>` : `<i class="sw kind-${r.kind}"></i>`;
      // a hidden comma, so a screen reader says "Hornsgatan, Street · Södermalm" rather than "Hornsgatan Street"
      return `<li id="search-opt-${i}" role="option" aria-selected="${i === active}" data-i="${i}">${sw}
        <b>${esc(main)}</b><span class="visually-hidden">, </span><span class="sub">${esc(sub)}</span></li>`;
    }).join('');
    if (active >= 0) input.setAttribute('aria-activedescendant', `search-opt-${active}`);
    else input.removeAttribute('aria-activedescendant');
    setOpen(rows.length > 0);
    list.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' });
  }

  async function run() {
    const q = input.value, my = ++seq;
    root.classList.toggle('filled', q.length > 0);
    if (!q.trim()) { rows = []; render(); hint(); say(''); return; }
    try { await load(); } catch { if (my === seq) { rows = []; render(); hint(); } return; }
    let res;
    try { res = await search(P, q, loadShard); } catch { res = { rows: [], message: { id: 'search.failed' } }; }
    if (my !== seq) return;                // a later keystroke has its own answer coming
    rows = res.rows;
    active = 0;
    render();
    const t = T();
    message(res.message);
    say(rows.length > 1 ? t('search.results', { n: rows.length }) : rows.length ? t('search.results.one') : t('search.results.none'));
  }

  // The phone's sheet covers the page: while it is open the rest of the page is inert, so Tab and a screen reader stay
  // in the sheet (spec §4.8).
  let inerted = [];
  function sheet(open) {
    root.classList.toggle('open', open);
    inerted.forEach(el => { el.inert = false; });
    inerted = open ? [...document.body.children].filter(el => el !== root && !el.contains(root) && !el.inert) : [];
    inerted.forEach(el => { el.inert = true; });
  }
  function close() {
    seq++;                                 // an answer still coming would open the list again
    rows = []; render(); showMessage('');
    sheet(false);
  }
  // Gives the keyboard back: to the search button on a phone (the sheet is gone), else to the map.
  function leave() {
    input.blur();
    if (isPhone()) openButton?.focus(); else focusMap();
  }
  function pick(i) {
    const row = rows[i];
    if (!row) return;
    input.value = row.label;
    close();
    if (isPhone()) input.blur();
    onPick(row, loadShard);
  }

  input.addEventListener('input', () => { current = run(); });
  // The examples once the index is in, but only while the keyboard is still in the search: a load that settles after
  // the visitor left would leave them under an unfocused pill (the final review's F7).
  input.addEventListener('focus', () => {
    const later = () => { if (inside() && !input.value.trim()) hint(); };
    load().then(later, later);
    if (!input.value.trim()) hint();
  });
  // On a desktop the list and the message close when the keyboard leaves the search, not when it moves from the field
  // to ×, an example or the suggestion (the final review's F2). The phone's sheet closes with Cancel or a pick.
  root.addEventListener('focusout', e => {
    if (isPhone() || root.contains(e.relatedTarget)) return;
    setTimeout(() => { if (!inside()) close(); }, 0);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!rows.length) { if (input.value.trim()) current = run(); return; }   // the list closed by Esc opens again
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length;
      render();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      // the rows of what is in the field now: a street's numbers may still be loading, or Esc closed the list
      if (!rows.length && input.value.trim()) current = run();
      const my = seq;
      current.then(() => { if (my === seq) pick(active >= 0 ? active : 0); });
    } else if (e.key === 'Escape') {
      e.preventDefault();                  // a search field clears itself on Escape; here the first one only closes
      e.stopPropagation();                 // the window's Escape closes a pinned card: not while searching
      if (!list.hidden || !msg.hidden) { seq++; rows = []; render(); showMessage(''); }   // and an answer still coming stays away
      else { input.value = ''; root.classList.remove('filled'); close(); leave(); }
    }
  });
  // A mouse pick: mousedown keeps the focus in the field, so the list stays until the click lands.
  list.addEventListener('mousedown', e => e.preventDefault());
  list.addEventListener('click', e => { const li = e.target.closest('[data-i]'); if (li) pick(+li.dataset.i); });
  msg.addEventListener('mousedown', e => e.preventDefault());
  msg.addEventListener('click', e => {
    const b = e.target.closest('.search-try');
    if (b) { input.value = b.dataset.q; input.focus(); run(); }
  });
  clear?.addEventListener('click', () => { input.value = ''; input.focus(); run(); });
  cancel?.addEventListener('click', () => { input.value = ''; root.classList.remove('filled'); close(); leave(); });
  openButton?.addEventListener('click', () => {
    sheet(true);
    input.focus();
  });
  // A phone turned to a wide screen while the sheet is open: the sheet becomes the pill, and the page is let go.
  addEventListener('resize', () => { if (root.classList.contains('open') && !isPhone()) close(); });
  // "/" or Ctrl/⌘ + K, unless the keys are going to another field or a dialog.
  addEventListener('keydown', e => {
    const el = e.target;
    const typing = el instanceof Element && (el.closest('input, textarea, select, [contenteditable="true"]') || el.isContentEditable);
    const slash = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey;
    const k = (e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey) && !e.altKey;
    if ((slash && !typing) || (k && el !== input)) {
      if (document.querySelector('dialog[open]') || (el instanceof Element && el.closest('[role="dialog"]'))) return;
      e.preventDefault();
      if (isPhone()) openButton?.click(); else input.focus();
    }
  });

  return {
    // The page's language changed: placeholder, labels and an open list or message in the new words.
    applyText() {
      const t = T();
      input.placeholder = t('search.placeholder');
      input.setAttribute('aria-label', t('search.label'));
      if (clear) clear.setAttribute('aria-label', t('search.clear'));
      if (cancel) cancel.textContent = t('search.cancel');
      if (openButton) openButton.setAttribute('aria-label', t('search.open'));
      if (rows.length) render();
      if (document.activeElement === input) run();
      else if (!msg.hidden) shown === 'hint' ? hint() : message(shown);   // a message under the unfocused pill
    },
    // ?q= (spec §4.5): search once the index is in and pick the top row.
    // A visitor who starts typing before it is in keeps what they typed.
    async runQuery(q) {
      input.value = q;
      root.classList.add('filled');
      const my = ++seq;
      let res;
      try { await load(); res = await search(P, q, loadShard); } catch { res = { rows: [], message: { id: 'search.failed' } }; }
      if (my !== seq) return;
      rows = res.rows;
      if (rows.length) pick(0);
      else { render(); message(res.message); }
    },
    get input() { return input; },
  };
}
