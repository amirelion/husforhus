// The timeline's landmark labels and its keyboard handles (spec §4.1; Plan 4a, Task 10). Pure, tested by node --test.

// Which landmark names fit on the timeline: highest priority first (stockholm.json landmarks' `timeline`, 1 first), then
// the older year, each placed centred on its year and kept inside the canvas, and dropped when it would come closer
// than `gap` px to one already placed. items: [{name, year, timeline, ...}]; xOf(year) -> px; measure(text) -> px.
// Returns the placed items with x0 and x1 (their box), in year order.
export function placeLabels(items, { xOf, width, measure, gap = 8 }) {
  const order = [...items].sort((a, b) => (a.timeline - b.timeline) || (a.year - b.year) || a.name.localeCompare(b.name));
  const placed = [];
  for (const it of order) {
    const w = measure(it.name);
    if (w + 2 > width) continue;
    const x0 = Math.min(Math.max(0, xOf(it.year) - w / 2), width - w);
    const x1 = x0 + w;
    if (placed.every(p => x1 + gap <= p.x0 || x0 >= p.x1 + gap)) placed.push({ ...it, x0, x1 });
  }
  return placed.sort((a, b) => a.year - b.year);
}

// The label under a pointer, or null: x inside its box (with a few px of slack), y within the label strip.
export const labelAt = (placed, x, y, strip = 16, slack = 3) =>
  (y <= strip ? placed.find(p => x >= p.x0 - slack && x <= p.x1 + slack) || null : null);

// A handle's next year for a key (the WAI-ARIA slider keys): arrows move a year (ten with Shift), Page Up/Down ten,
// Home/End to the ends. Returns null for any other key, so the caller lets it be.
export function stepYear(key, { value, min, max, shift = false }) {
  const step = shift ? 10 : 1;
  const next = { ArrowLeft: value - step, ArrowDown: value - step, ArrowRight: value + step, ArrowUp: value + step,
    PageDown: value - 10, PageUp: value + 10, Home: min, End: max }[key];
  return next === undefined ? null : Math.max(min, Math.min(max, next));
}
