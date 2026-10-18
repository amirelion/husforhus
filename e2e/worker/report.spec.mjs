// File a report from Börshuset's card against `wrangler dev` (playwright.worker.config.mjs): the form opens prefilled,
// read-only, sends to this origin only, and the Worker stores it and answers with a reference.
import { test, expect } from '@playwright/test';

const gidOf = (page, name) => page.evaluate(async name => {
  const { version } = await (await fetch('data/current.json')).json();
  for (let k = 0; k < 64; k++) {
    const shard = await (await fetch(`data/${version}/cards/${String(k).padStart(2, '0')}.json`)).json();
    for (const [g, c] of Object.entries(shard)) if (c.name === name) return +g;
  }
  return -1;
}, name);

test('a report about Börshuset, from its card', async ({ page, baseURL }) => {
  const foreign = [];
  page.on('request', r => { if (!r.url().startsWith(baseURL) && !r.url().startsWith('data:')) foreign.push(r.url()); });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const gid = await gidOf(page, 'Börshuset');
  expect(gid).toBeGreaterThanOrEqual(0);
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  await expect(page.locator('#card.pinned #card-title')).toHaveText('Börshuset', { timeout: 30_000 });

  await page.locator('#card.pinned .card-wrong').click();
  const dialog = page.getByRole('dialog', { name: 'Something wrong?' });
  await expect(dialog).toBeVisible();
  // the building, as text: nothing to edit
  const ref = dialog.locator('.report-ref');
  await expect(ref).toContainText('Börshuset');
  await expect(ref).toContainText(`building ${gid}, data v`);
  await expect(ref.locator('input, textarea')).toHaveCount(0);
  await expect(dialog.getByRole('radio', { name: 'Wrong or missing year or detail' })).toBeChecked();
  await expect(dialog.getByRole('radio', { name: 'Add a photo' })).toBeVisible();

  // too short and no email: the form says so and sends nothing
  const send = dialog.getByRole('button', { name: 'Send' });
  await dialog.getByLabel('Your message').fill('short');
  await send.click();
  await expect(dialog.getByRole('status')).toHaveText('Please check the marked fields.');
  await expect(dialog.getByLabel('Your message')).toHaveAttribute('aria-invalid', 'true');

  await dialog.getByLabel('Your message').fill('The plaque by the door says the building was finished in 1776.');
  await dialog.getByLabel('Your email address').fill('reader@example.org');
  await page.waitForTimeout(3000);   // a person takes longer than 3 s; the Worker silently drops faster forms
  const posted = page.waitForRequest(r => r.url().endsWith('/api/report') && r.method() === 'POST');
  await send.click();
  const body = (await posted).postDataJSON();
  expect(body).toMatchObject({ kind: 'year_or_detail', email: 'reader@example.org', lang: 'en', website: '',
    building: { gid, name: 'Börshuset' } });
  await expect(dialog.locator('.report-thanks')).toHaveText(/^Thanks: reference HFH-\d+\. We may write to you at this address\.$/);
  await expect(dialog.locator('.report-address')).toHaveText('reader@example.org');
  await expect(dialog.locator('.report-thanks')).toBeFocused();
  await dialog.getByRole('button', { name: 'Close' }).last().click();
  await expect(dialog).toBeHidden();
  await expect(page.locator('#card.pinned .card-wrong')).toBeFocused();   // the focus goes back where it came from
  expect(foreign).toEqual([]);

  // the admin API is closed without Cloudflare Access
  expect((await page.request.get('/api/admin/reports')).status()).toBe(403);
});

test("About's \"Suggest something\" files a general report, in Swedish", async ({ page }) => {
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await page.locator('.about-open').click();
  await page.getByRole('button', { name: 'Föreslå något' }).click();
  const dialog = page.getByRole('dialog', { name: 'Föreslå något' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('input[type="radio"], input[type="file"]')).toHaveCount(0);
  await dialog.getByLabel('Ditt meddelande').fill('Visa gärna gamla tunnelbanestationer också.');
  await dialog.getByLabel('Din e-postadress').fill('lasare@example.org');
  await page.waitForTimeout(3000);
  await dialog.getByRole('button', { name: 'Skicka' }).click();
  await expect(dialog.locator('.report-thanks')).toHaveText(/^Tack: referens HFH-\d+\./);
});
