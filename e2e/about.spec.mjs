// About (Plan 4b, Task 7): written from the build, in the page's language, with links into its sections.
import { test, expect } from '@playwright/test';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const config = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await fetch(`data/${version}/stockholm.json`)).json();
});

test('About says the build\'s own numbers and follows the language switch', async ({ page }) => {
  await open(page);
  const cfg = await config(page);
  await page.locator('.about-open').click();
  const about = page.locator('#about');
  await expect(about).toBeVisible();
  await expect(about.locator('.lead').first()).toContainText(`(${cfg.stats.buildings.toLocaleString('en')} of them)`);
  await expect(about.locator('#about-years')).toHaveText('Where the years come from');
  await expect(about.locator('#about-data li').first()).toContainText(cfg.attribution[0].credit.en);   // D44's line
  await expect(about.locator('#about-contact ~ p').last()).toContainText(`Data version ${cfg.version}`);
  await about.locator('.about-close').click();
  await page.locator('.lang [data-lang="sv"]').click();
  await page.locator('.about-open').click();
  await expect(about.locator('#about-years')).toHaveText('Var årtalen kommer ifrån');
  await expect(about.locator('#about-data li').first()).toContainText(cfg.attribution[0].credit.sv);
  await expect(about.locator('#about-body')).toHaveAttribute('lang', 'sv');
});

test('#about/privacy opens About at its privacy section; closing it lets go of the link', async ({ page }) => {
  await open(page, '#about/privacy');
  const heading = page.locator('#about-privacy');
  await expect(heading).toBeInViewport();
  await expect(heading).toBeFocused();
  await expect(page.locator('#about')).toContainText('This map is about buildings, not people.');
  await page.keyboard.press('Escape');
  await expect(page.locator('#about')).toBeHidden();
  await expect(page).toHaveURL(u => !new URL(u).hash);     // the close event runs a moment after the dialog hides
});

test('the section links scroll inside About without changing the address', async ({ page }) => {
  await open(page);
  await page.locator('.about-open').click();
  await page.locator('.about-nav a[data-section="sources"]').click();
  await expect(page.locator('#about-sources')).toBeInViewport();
  expect(new URL(page.url()).hash).toBe('');
});
