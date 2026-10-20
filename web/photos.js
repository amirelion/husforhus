// Photos through the years: the pinned card's one photo slot. Today's photo (card `photo`: Wikimedia Commons, or a
// reader's) comes first, then the City Museum's archive photos (card `arch`, s02_stadsmuseet_photos), oldest first;
// with more than one, the year strip below the picture (.years) switches between them. Each archive photo has one
// credit line, linked to its own page in Digitala Stadsmuseet. Pure functions, tested by node --test; the files are
// the site's own (data/photos/), so a card asks no other host.
import { photoCredit } from './card.js';

// An archive photo's own .info page (pipeline/stadsmuseet_photos.py PHOTO_PAGE): never a search or filter address
export const ARCHIVE_PAGE = /^https:\/\/digitalastadsmuseet\.stockholm\.se\/fotoweb\/archives\/5000-Alla-fotografier\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.(?:jpe?g|tiff?|png)\.info$/;

// The card's slides, today's first; a photo whose file failed to load (`failed`, by key) is left out.
export function photoSlides(card, failed = new Set()) {
  const today = card?.photo && !failed.has(card.photo.key) ? [{ ...card.photo, today: true }] : [];
  const archive = (card?.arch || []).filter(a => a && typeof a.page === 'string' && ARCHIVE_PAGE.test(a.page)
    && !failed.has(a.key));
  return [...today, ...archive];
}

// An archive photo's one-line credit: "Photo: <photographer>, Stadsmuseet i Stockholm, CC BY 4.0", one link.
export function archiveCredit(a, T) {
  return [{ text: a.by ? T('card.photo.sm', { by: a.by }) : T('card.photo.sm.unknown'), href: a.page }];
}

// A slide's tab in the year strip: "Today" for today's photo, else its year, or "Undated".
export function slideLabel(s, T) {
  return s.today ? T('card.photo.today') : s.y ? String(s.y) : T('card.photo.undated');
}

// The figure for slide `at` (clamped), or '' without slides. `link(href, text)` and `esc` are the card's;
// `alt(slide)` names what the picture shows.
export function photoFigure(slides, at, T, esc, link, alt) {
  if (!slides.length) return '';
  const k = Math.max(0, Math.min(at | 0, slides.length - 1)), s = slides[k];
  const size = s.w > 0 && s.h > 0 ? `width="${+s.w}" height="${+s.h}"` : '';
  const credit = s.today ? photoCredit(s, T) : archiveCredit(s, T);
  const strip = slides.length > 1 ? `<nav class="years" aria-label="${esc(T('card.photos'))}">${slides.map((x, j) =>
    `<button type="button" data-slide="${j}"${j === k ? ' aria-current="true"' : ''}>${esc(slideLabel(x, T))}</button>`).join('')}</nav>` : '';
  return `
    <figure class="photo"><div class="frame"><img src="data/photos/${esc(s.key)}" data-key="${esc(s.key)}" ${size}
      alt="${esc(alt(s))}" loading="lazy" decoding="async">${!s.today && s.y ? `<span class="year">${+s.y}</span>` : ''}</div>
      <figcaption>${credit.map(c => (c.href ? link(c.href, c.text) : esc(c.text))).join(' · ')}</figcaption>${strip}</figure>`;
}
