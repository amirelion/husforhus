// web/apple-touch-icon.png from web/favicon.svg (the audit's finding 10): 180 × 180, drawn full-bleed on the icon's own
// ground, since iOS rounds the corners itself. Run from the repo: node scripts/og/icon.mjs
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

const svg = readFileSync('web/favicon.svg', 'utf8');
const ground = svg.match(/<rect [^>]*fill="(#[0-9a-f]{6})"/i)[1];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 180, height: 180 } });
await page.setContent(`<html><body style="margin:0;background:${ground}">${svg.replace('<svg ', '<svg width="180" height="180" ')}</body></html>`);
writeFileSync('web/apple-touch-icon.png', await page.screenshot({ clip: { x: 0, y: 0, width: 180, height: 180 } }));
await browser.close();
