// The Look button and its panel: one card per look (web/look.js), each with the look's name in its own font and
// a strip of its twelve period colours on its own ground, the current one pressed. A popover under the button on
// a desktop, a bottom sheet on a phone (styles.css). A tap switches at once and the panel stays open, so the looks
// can be compared; Escape, the close button, a click outside or the focus leaving closes it. Tab or the arrow keys
// move between the cards, Enter or Space picks one. The atmosphere row, headed Weather (Clear, Snow, Rain, Fog: app.js
// adds them from web/weather.js), appears once there is an atmosphere besides 'none'. "Show on the map" holds the
// map's layer switches (Tunnelbanan, the boats, the plaques, the photo highlight); while one differs from its default
// (most are off by default, the boats on), a dot on the Look button says so with the panel closed. A second row of
// switches (extras: the Quests and walks switch) sits under its own heading and never lights the dot. The Ground row's
// Hills slider scales the relief; it has the arrow keys while focused.
import { THEMES } from './themes.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// button: the Look button; panel: an empty <dialog>; looks: createLooks(); t: app.js's string table. relief (
// optional): {available, value, max, step, disabled, choose(v), label(v), note()}, the Hills slider, a row under the
// looks once available, from 0 (flat) to max, with its value (label: "Flat", "1×") and its honesty line (what the map
// shows now); disabled (the terrain did not load) dims it and a move snaps back, changing nothing.
// layers (optional): {title(), items()}, items() the switches to show, each {id, label, on, set(v), default?, hint?:
// {id, cls, text}}; the button keeps the id, a hint line shows while on; default (false unless given) is the switch's
// state on a fresh visit. extras (optional): the same shape, its own heading.
// app.js calls markLayers() after each switch changes.
// Returns render(), to call again when the language changes, markLayers(), and markRelief(), to call whenever the relief or the
// terrain's state changes (app.js calls it from setRelief, a move included, so it runs once per change).
export function mountSwitcher({ button, panel, looks, t, relief = null, layers = null, extras = null }) {
  const atmos = looks.atmospheres;
  const layerItems = () => layers?.items() ?? [];
  const extraItems = () => extras?.items() ?? [];
  const allItems = () => [...layerItems(), ...extraItems()];
  const dot = document.createElement('i');
  dot.className = 'look-dot';
  dot.hidden = true;
  button.append(dot);
  // The switches change in place (the focus stays), and the button's dot follows the layer switches: it shows while
  // one of them is not as a fresh visit has it.
  function markLayers() {
    for (const L of allItems()) {
      panel.querySelector(`#${L.id}`)?.setAttribute('aria-pressed', String(L.on));
      if (L.hint) { const h = panel.querySelector(`#${L.hint.id}`); if (h) h.hidden = !L.on; }
    }
    dot.hidden = !layerItems().some(L => !!L.on !== !!L.default);
  }
  // A heading and its row of switches, or nothing while the row is empty.
  const switchRow = (id, cls, group, items) => !items.length ? '' : `<h3 id="${id}">${esc(group.title())}</h3>
      <div class="${cls}" role="group" aria-labelledby="${id}">${items.map(L => `<div class="est-row">
        <button class="switch" id="${L.id}" data-layer aria-pressed="${L.on}"${L.hint ? ` aria-describedby="${L.hint.id}"` : ''}><span class="toggle" aria-hidden="true"></span>${
        esc(L.label)}</button>${L.hint ? `<span class="${L.hint.cls}" id="${L.hint.id}"${L.on ? '' : ' hidden'}>${esc(L.hint.text)}</span>` : ''}</div>`).join('')}</div>`;
  const card = l => {
    const th = THEMES[l.id];
    return `<button class="look-card" data-look="${l.id}" aria-pressed="${l.id === looks.current}"
      style="--card-bg:${th.ui['--panel']};--card-ink:${th.ui['--ink']};--card-ground:${th.land};--card-font:'${th.font}'">
      <span class="look-strip" aria-hidden="true">${th.periods.map(c => `<i style="background:${c}"></i>`).join('')}</span>
      <span class="look-name">${esc(t(l.name))}</span>
      <svg class="look-check" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10"/><path d="M5.6 10.4l2.9 2.9 5.9-6.4"/></svg></button>`;
  };
  function render() {
    const focused = panel.contains(document.activeElement) && document.activeElement.dataset.look;
    const slid = panel.contains(document.activeElement) && 'relief' in document.activeElement.dataset;
    const layerFocus = panel.contains(document.activeElement) && 'layer' in document.activeElement.dataset && document.activeElement.id;
    (button.querySelector('span') || button).textContent = t('Look');
    panel.innerHTML = `
      <header><h2 id="look-title">${t('Look')}</h2><button class="look-close" aria-label="${t('Close')}">×</button></header>
      <div class="look-cards" role="group" aria-labelledby="look-title">${looks.items.map(card).join('')}</div>
      ${atmos.items.length > 1 ? `<h3 id="atmos-title">${t('Weather')}</h3>
      <div class="look-atmos" role="group" aria-labelledby="atmos-title">${atmos.items.map(a =>
        `<button data-atmos="${a.id}" aria-pressed="${a.id === atmos.current}">${esc(t(a.name))}</button>`).join('')}</div>` : ''}
      ${switchRow('layers-title', 'look-layers', layers, layerItems())}
      ${switchRow('extras-title', 'look-layers look-extras', extras, extraItems())}
      ${relief?.available ? `<h3 id="relief-title">${t('Ground')}</h3>
      <div class="look-relief" role="group" aria-labelledby="relief-title"><div class="relief-row">
        <label for="relief-range">${t('Hills')}</label>
        <input type="range" id="relief-range" data-relief min="0" max="${relief.max}" step="${relief.step}"
          value="${relief.value}" aria-valuetext="${esc(relief.label(relief.value))}" aria-describedby="relief-note"${
          relief.disabled ? ' aria-disabled="true"' : ''}>
        <output id="relief-value" for="relief-range" aria-hidden="true">${esc(relief.label(relief.value))}</output></div>
        <span class="relief-note" id="relief-note">${esc(relief.note())}</span></div>` : ''}`;
    markLayers();
    if (focused) panel.querySelector(`[data-look="${focused}"]`)?.focus();
    if (layerFocus) panel.querySelector(`#${layerFocus}`)?.focus();
    if (slid) panel.querySelector('[data-relief]')?.focus();
  }
  // A switch only moves the pressed mark, so the focused card keeps the focus.
  const mark = () => {
    panel.querySelectorAll('[data-look]').forEach(b => b.setAttribute('aria-pressed', b.dataset.look === looks.current));
    panel.querySelectorAll('[data-atmos]').forEach(b => b.setAttribute('aria-pressed', b.dataset.atmos === atmos.current));
  };
  looks.subscribe(mark);
  atmos.subscribe(mark);
  // The Hills slider changes in place too (a drag keeps its hold): its value, as read out and as shown, whether it can
  // be moved, and its line.
  const markRelief = () => {
    const r = panel.querySelector('[data-relief]');
    if (!r) return;
    const v = relief.value, label = relief.label(v);
    if (Number(r.value) !== v) r.value = String(v);
    r.setAttribute('aria-valuetext', label);
    panel.querySelector('#relief-value').textContent = label;
    if (relief.disabled) r.setAttribute('aria-disabled', 'true');
    else r.removeAttribute('aria-disabled');
    panel.querySelector('#relief-note').textContent = relief.note();
  };
  // A move is the visitor's choice (app.js chooseRelief); while disabled the slider goes back to where it was.
  panel.addEventListener('input', e => {
    if (!('relief' in e.target.dataset)) return;
    if (relief.disabled) markRelief();
    else relief.choose(Number(e.target.value));
  });

  panel.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.look) looks.set(b.dataset.look);
    else if ('layer' in b.dataset) { const L = allItems().find(L => L.id === b.id); L?.set(!L.on); }
    else if (b.dataset.atmos) atmos.set(b.dataset.atmos);
    else if (b.classList.contains('look-close')) close(true);
  });
  // Arrow keys move along the cards (and along the atmospheres), wrapping at the ends.
  panel.addEventListener('keydown', e => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    const row = e.target.closest('.look-cards, .look-atmos');
    if (!step || !row) return;
    e.preventDefault();
    const bs = [...row.querySelectorAll('button')], i = bs.indexOf(e.target);
    bs[(i + step + bs.length) % bs.length].focus();
  });
  // Escape closes from anywhere while the panel is open; it then goes no further, so a pinned card stays pinned.
  const onKey = e => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    e.stopPropagation();
    close(true);
  };
  const outside = e => { if (!panel.contains(e.target) && !button.contains(e.target)) close(false); };
  panel.addEventListener('focusout', e => {
    const to = e.relatedTarget;
    if (to && !panel.contains(to) && to !== button) close(false);
  });

  function open() {
    render();
    panel.show();
    button.setAttribute('aria-expanded', 'true');
    panel.querySelector('[data-look][aria-pressed="true"]')?.focus();
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', outside, true);
  }
  function closed() {
    button.setAttribute('aria-expanded', 'false');
    document.removeEventListener('keydown', onKey);
    document.removeEventListener('pointerdown', outside, true);
  }
  function close(refocus) {
    if (panel.open) panel.close();
    closed();
    if (refocus) button.focus();
  }
  // The close event comes later (a task); by then the panel may be open again.
  panel.addEventListener('close', () => { if (!panel.open) closed(); });
  button.addEventListener('click', () => (panel.open ? close(true) : open()));
  render();
  return { render, markRelief, markLayers };
}
