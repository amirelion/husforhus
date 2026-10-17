import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ease, initialRelief, reliefNote, reliefValue, RELIEF_MAX, RELIEF_STEP } from '../relief.js';

// The Hills slider (decided 2026-10-16): the ground at true height by default (stockholm.json terrain.relief, 1),
// scaled from 0 (flat) to terrain.reliefMax (2.5) in steps of 0.5. The fallbacks when a build's config has no maximum.
test('the slider runs from 0 to 2.5 in steps of 0.5 unless the build says otherwise', () => {
  assert.equal(RELIEF_MAX, 2.5);
  assert.equal(RELIEF_STEP, 0.5);
});

test('?relief= beats the remembered value, which beats the default', () => {
  assert.equal(initialRelief('', null, 1, 2.5), 1);
  assert.equal(initialRelief('', '1.5', 1, 2.5), 1.5);
  assert.equal(initialRelief('?relief=2', '1.5', 1, 2.5), 2);
  assert.equal(initialRelief('?theme=arg&relief=0.5', null, 1, 2.5), 0.5);
  assert.equal(initialRelief('', null, 0), 0);   // a city with no relief by default
  assert.equal(initialRelief('', null, 1), 1);   // the maximum defaults to RELIEF_MAX
  assert.equal(initialRelief('?relief=9', null, 1), 2.5);
  assert.equal(initialRelief('', null, 3, 2.5), 2.5);   // a default above the top is clamped to it (S9)
});

// ?relief= (a shared link, the review's lever): off is flat, on is the default, a number is clamped to the slider.
test('?relief= takes off, on or a number, clamped to 0..reliefMax; nonsense falls through', () => {
  assert.equal(initialRelief('?relief=off', '2', 1, 2.5), 0);
  assert.equal(initialRelief('?relief=0', '2', 1, 2.5), 0);
  assert.equal(initialRelief('?relief=on', '0', 1, 2.5), 1);
  assert.equal(initialRelief('?relief=1.5', '0', 1, 2.5), 1.5);
  assert.equal(initialRelief('?relief=2.5', null, 1, 2.5), 2.5);
  assert.equal(initialRelief('?relief=9', null, 1, 2.5), 2.5);
  assert.equal(initialRelief('?relief=3', '0', 1, 2.5), 2.5);
  assert.equal(initialRelief('?relief=-1', '2', 1, 2.5), 0);
  // between the steps: snapped to the slider's step (S1), so its thumb, value, line and the map agree
  assert.equal(initialRelief('?relief=0.2', null, 1, 2.5), 0);
  assert.equal(initialRelief('?relief=1.23', null, 1, 2.5), 1);
  assert.equal(initialRelief('?relief=1.3', null, 1, 2.5), 1.5);
  assert.equal(initialRelief('?relief=2.4', null, 1, 2.5), 2.5);
  assert.equal(initialRelief('', '0.7', 1, 2.5), 0.5);              // a stored value too
  assert.equal(initialRelief('?relief=3', null, 2.5, 3), 3);        // an older build's own maximum
  for (const q of ['?relief=abc', '?relief=', '?relief=%20', '?relief=Infinity', '?relief=NaN']) {
    assert.equal(initialRelief(q, '2', 1, 2.5), 2, q);
    assert.equal(initialRelief(q, null, 1, 2.5), 1, q);
  }
});

// localStorage hfh-relief held 'on' or 'off' while the relief was a switch; it now holds the number.
test('the remembered value: a number, clamped; the old switch values migrate; anything else is the default', () => {
  assert.equal(initialRelief('', '0', 1, 2.5), 0);
  assert.equal(initialRelief('', '2.5', 1, 2.5), 2.5);
  assert.equal(initialRelief('', '7', 1, 2.5), 2.5);
  assert.equal(initialRelief('', '-3', 1, 2.5), 0);
  assert.equal(initialRelief('', 'off', 1, 2.5), 0);   // flat stays flat
  assert.equal(initialRelief('', 'on', 1, 2.5), 1);    // "on" was the default, which is now 1x
  assert.equal(initialRelief('', 'on', 0, 2.5), 0);
  for (const s of ['', 'yes', 'NaN', ' ']) assert.equal(initialRelief('', s, 1, 2.5), 1, JSON.stringify(s));
});

// The slider's visible value: "Flat" at 0, else the factor, with a decimal comma in Swedish.
test('the slider shows Flat or the factor', () => {
  assert.equal(reliefValue(0), 'Flat');
  assert.equal(reliefValue(0, 'sv'), 'Platt');
  assert.equal(reliefValue(0.5), '0.5×');
  assert.equal(reliefValue(0.5, 'sv'), '0,5×');
  assert.equal(reliefValue(1), '1×');
  assert.equal(reliefValue(1, 'sv'), '1×');
  assert.equal(reliefValue(1.5), '1.5×');
  assert.equal(reliefValue(1.5, 'sv'), '1,5×');
  assert.equal(reliefValue(2), '2×');
  assert.equal(reliefValue(2.5), '2.5×');
  assert.equal(reliefValue(2.5, 'sv'), '2,5×');
  assert.equal(reliefValue(1.23), '1.2×');   // a link's value between the steps, as the note rounds it
});

// The line under the slider says what the map shows now: flat at 0, true to scale at 1, the
// factor otherwise (reduced under 1, exaggerated over it), and a terrain that did not load beats them all (the slider
// is then aria-disabled). While the terrain is on its way ('flat' before it is asked for, then 'loading') the map is
// flat whatever the slider says, so the line says the ground is loading (the final review's VIEWER-3).
test('the honesty line says what the map shows: flat, reduced, true to scale, exaggerated, loading or not loaded', () => {
  const lines = {
    en: ['Ground drawn flat', 'Ground heights reduced to 0.5×', 'Ground heights true to scale',
      'Ground heights exaggerated 1.5×', 'Ground heights exaggerated 2.5×'],
    sv: ['Marken visas platt', 'Markhöjder i skala 0,5', 'Markhöjder i verklig skala',          // S7
      'Markhöjder överdrivna 1,5 gånger', 'Markhöjder överdrivna 2,5 gånger'],
  };
  for (const lang of ['en', 'sv']) {
    [0, 0.5, 1, 1.5, 2.5].forEach((v, i) => {
      assert.equal(reliefNote(v, lang, 'ready'), lines[lang][i], `${lang} ${v}`);
      assert.equal(reliefNote(v, lang, 'loading'), lang === 'en' ? 'Loading the ground…' : 'Laddar marken…');
      assert.equal(reliefNote(v, lang, 'flat'), lang === 'en' ? 'Loading the ground…' : 'Laddar marken…');
    });
  }
  assert.equal(reliefNote(1), 'Ground heights true to scale');   // English and ready by default
  assert.equal(reliefNote(2), 'Ground heights exaggerated 2×');
  assert.equal(reliefNote(1.04), 'Ground heights true to scale');   // as the line rounds it
  assert.equal(reliefNote(1.25), 'Ground heights exaggerated 1.3×');
  assert.equal(reliefNote(0.04), 'Ground drawn flat');
  for (const v of [0, 1, 2.5]) {
    assert.equal(reliefNote(v, 'en', 'failed'), "The ground's heights did not load");
    assert.equal(reliefNote(v, 'sv', 'failed'), 'Markhöjderna kunde inte laddas');
  }
});

test('ease runs from a to b and stays there', () => {
  assert.equal(ease(0, 2.5, 0), 0);
  assert.equal(ease(0, 2.5, 1), 2.5);
  assert.equal(ease(0, 2.5, 0.5), 1.25);
  assert.equal(ease(2.5, 0, 2), 0);
  assert.equal(ease(2.5, 0, -1), 2.5);
});
