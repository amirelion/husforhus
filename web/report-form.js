// The report dialog in the page: opens the form (web/report.js formHtml) for a card's building or for a suggestion,
// re-encodes a photo to a JPEG of at most 2048 px (a canvas keeps no EXIF or GPS), and sends it to this origin only.
import { API, MAX_BYTES, TYPES, formHtml, payload, fitSize, errorText } from './report.js';

const FIELD = { message: 'message', email: 'email', photo: 'photo', photo_type: 'photo', exif: 'photo', photo_size: 'photo',
  photo_credit: 'photo_credit', consent: 'consent_own' };

async function reencode(file) {
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  const [w, h] = fitSize(bmp.width, bmp.height);
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  canvas.getContext('2d').drawImage(bmp, 0, 0, w, h);
  bmp.close?.();
  return new Promise((ok, fail) => canvas.toBlob(b => (b ? ok(b) : fail(new Error('encode'))), 'image/jpeg', 0.88));
}

// openReport(ref): ref is buildingRef() for a card, null for a general suggestion. getT() gives the page's T.
export function reportDialog(dialog, getT) {
  let opener = null;
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus(); });

  return function openReport(ref) {
    const T = getT();
    opener = document.activeElement;
    dialog.innerHTML = formHtml(ref, T);
    dialog.lang = T.lang;
    const form = dialog.querySelector('form'), status = form.querySelector('.report-status');
    const send = form.querySelector('.report-send'), photoBox = form.querySelector('.report-photo');
    const opened = performance.now();
    dialog.querySelector('.report-close').onclick = () => dialog.close();
    form.querySelector('.report-cancel').onclick = () => dialog.close();
    const syncKind = () => {
      const photo = form.elements.kind.value === 'photo';
      if (!photoBox) return;
      photoBox.hidden = !photo;
      for (const n of ['photo', 'photo_credit', 'consent_own', 'consent_licence']) form.elements[n].required = photo;
    };
    form.addEventListener('change', syncKind);
    form.elements.photo_credit?.addEventListener('input', e => {
      form.querySelector('.report-credit-name').textContent = e.target.value.trim();
    });
    syncKind();
    form.addEventListener('submit', async e => {
      e.preventDefault();
      form.querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
      if (!form.checkValidity()) {
        const bad = [...form.elements].filter(el => el.willValidate && !el.validity.valid);
        bad.forEach(el => el.setAttribute('aria-invalid', 'true'));
        status.textContent = T('report.error.invalid');
        bad[0]?.focus();
        return;
      }
      const fields = Object.fromEntries(['kind', 'message', 'email', 'website', 'photo_credit']
        .map(n => [n, form.elements[n]?.value ?? '']));
      fields.consent_own = !!form.elements.consent_own?.checked;
      fields.consent_licence = !!form.elements.consent_licence?.checked;
      const body = payload(fields, ref, T.lang, performance.now() - opened);
      send.disabled = true;
      status.textContent = T('report.sending');
      let res, out = {};
      try {
        let init = { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) };
        const file = body.kind === 'photo' ? form.elements.photo.files[0] : null;
        if (file) {
          if (!TYPES.includes(file.type)) throw Object.assign(new Error('type'), { fields: ['photo_type'], status: 400 });
          if (file.size > MAX_BYTES) throw Object.assign(new Error('size'), { fields: ['photo_size'], status: 400 });
          const data = new FormData();
          data.set('report', JSON.stringify(body));
          data.set('photo', await reencode(file), 'photo.jpg');
          init = { method: 'POST', body: data };
        }
        res = await fetch(API, init);
        out = await res.json().catch(() => ({}));
      } catch (err) {
        res = { ok: false, status: err.status || 0 };
        out = { fields: err.fields || [] };
      }
      send.disabled = false;
      if (!res.ok) {
        const fieldsBad = out.fields || [];
        fieldsBad.map(f => form.elements[FIELD[f]]).filter(Boolean).forEach(el => el.setAttribute('aria-invalid', 'true'));
        status.textContent = errorText(T, res.status, fieldsBad);
        return;
      }
      form.innerHTML = `<h2 id="report-title">${T(ref ? 'report.title.card' : 'report.title.general')}</h2>
        <p class="report-thanks" tabindex="-1"></p><p class="report-address"></p>
        <p class="report-actions"><button type="button" class="report-done">${T('report.close')}</button></p>`;
      form.querySelector('.report-thanks').textContent = T('report.thanks', { ref: out.reference });
      form.querySelector('.report-address').textContent = body.email;
      form.querySelector('.report-done').onclick = () => dialog.close();
      form.querySelector('.report-thanks').focus();
    });
    dialog.showModal();
    (form.querySelector('input[name="kind"]:checked') || form.elements.message).focus();
  };
}
