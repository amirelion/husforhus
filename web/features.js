// ?try=stories,plaques: switches on, for this visit only, a feature the build still leaves off, so it can be tried on
// the live site (on a phone too) before it is switched on for everyone. Only the names below; anything else is
// ignored, and nothing is remembered. Pure, tested by node --test (web/test/features.test.mjs).
export const TRY = { stories: 'scenes', plaques: 'plaques' };

export function withTry(features, search) {
  const asked = (new URLSearchParams(search).get('try') || '').split(',').map(s => s.trim().toLowerCase());
  const on = asked.filter(n => Object.hasOwn(TRY, n)).map(n => TRY[n]);
  return on.length ? { ...features, ...Object.fromEntries(on.map(f => [f, true])) } : { ...features };
}
