// The terrain wait shared by scripts/look.mjs and scripts/measure.mjs (Plan 3, Task 11 review, fix round 1). No
// Playwright import: a script passes its page in, so look.mjs's checks still run where node_modules is not installed.

// What window.__dbg says about the terrain (web/app.js: terrain() and relief): its source (null in a build without
// one), its state ('flat', 'loading', 'ready' or 'failed'), the relief drawn now and the relief asked for (__dbg.relief,
// a number: the Hills slider's value, 0 for flat). It stands
// when it is ready at the relief asked for, or when the build has none. A failed terrain never stands (the map stays
// flat, which is not what a relief render claims to show), but the wait for it is done: 'failed' is final. Self-
// contained, because Playwright sends its source text to the page (waitForFunction(terrainStatus, true) for "done",
// evaluate(terrainStatus) for the whole record).
export function terrainStatus(doneOnly = false) {
  const dbg = window.__dbg;
  const t = typeof dbg.terrain === 'function' ? dbg.terrain() : {};
  const wanted = Number(dbg.relief) || 0;
  const stands = !t.source || (t.state === 'ready' && Math.abs(t.relief - wanted) < 1e-6);
  if (doneOnly) return stands || (!!t.source && t.state === 'failed');
  return { source: t.source || null, state: t.state ?? null, relief: t.relief ?? null, wanted, stands };
}

// Waits until the terrain stands and returns terrainStatus's record. A terrain that failed to load stops the wait at
// once with an error naming the run (`label`); one still not standing after `timeout` (loading, or not yet risen)
// throws an error that names the run and what the page reported. Any other error passes on as it is.
export async function waitForTerrain(page, label, timeout = 60_000) {
  try {
    await page.waitForFunction(terrainStatus, true, { timeout });
  } catch (e) {
    if (e?.name !== 'TimeoutError') throw e;
    const s = await page.evaluate(terrainStatus).catch(() => ({}));
    const n = x => (typeof x === 'number' ? Math.round(x * 100) / 100 : x);
    throw new Error(`terrain did not stand in ${timeout / 1000} s ` +
      `(${label}: state=${s.state}, relief=${n(s.relief)}, wanted=${n(s.wanted)})`, { cause: e });
  }
  const s = await page.evaluate(terrainStatus);
  if (s.source && s.state === 'failed') throw new Error(`terrain failed to load (${label})`);
  return s;
}

// A console message that counts as a problem in a run: any error, and a warning about the terrain (web/app.js warns
// "The terrain did not load; the map stays flat." and carries on).
export function pageProblem(type, text) {
  return type === 'error' || (type === 'warning' && /terrain/i.test(text));
}
