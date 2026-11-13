/* Real Chromium smoke/E2E against a running demo API. No payment credentials required. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium as playwright } from 'playwright-core';
import serverlessChromium from '@sparticuz/chromium';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = process.env.SCREENSHOT_DIR || path.join(ROOT, '.local', 'screenshots');
fs.mkdirSync(SHOTS, { recursive: true });

// The serverless Chromium package ships AL2023 shared libraries for minimal Linux hosts.
const libDir = path.join(os.tmpdir(), 'al2023');
if (!fs.existsSync(path.join(libDir, 'lib', 'libnss3.so'))) {
  fs.mkdirSync(libDir, { recursive: true });
  const tar = path.join(os.tmpdir(), 'routenex-al2023.tar');
  fs.writeFileSync(tar, zlib.brotliDecompressSync(fs.readFileSync(path.join(ROOT, 'frontend/node_modules/@sparticuz/chromium/bin/al2023.tar.br'))));
  execFileSync('tar', ['-xf', tar, '-C', libDir]);
}
process.env.LD_LIBRARY_PATH = `${libDir}/lib:${process.env.LD_LIBRARY_PATH || ''}`;

const browser = await playwright.launch({
  executablePath: await serverlessChromium.executablePath(),
  args: serverlessChromium.args.filter(a => a !== '--disable-web-security'),
  headless: true,
  env: { ...process.env },
});
const context = await browser.newContext({ viewport: { width: 1360, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const shot = name => page.screenshot({ path: path.join(SHOTS, `v3-${name}.png`), fullPage: false });

async function login(email, password) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL(`${BASE}/`);
}
async function logout() {
  await page.getByTitle('Sign out').click();
  await page.waitForURL(`${BASE}/login`);
}

try {
  await login('samikhan@gmail.com', 'sami@123');
  await page.getByRole('link', { name: 'Administration', exact: true }).click();
  await page.getByText('Currently signed-in users').waitFor();
  await page.getByText('samikhan@gmail.com').first().waitFor({ timeout: 10000 });
  assert.match(await page.locator('body').innerText(), /samikhan@gmail\.com/);
  await shot('admin-sessions');
  await logout();

  await login('customer@routenex.in', 'Demo@123');
  await page.getByRole('link', { name: 'Shop', exact: true }).click();
  await page.locator('.product-card').first().waitFor();
  await shot('shop');
  await page.getByLabel('Search products').fill('notebook');
  await page.waitForTimeout(600);
  await page.locator('.product-card').first().getByRole('button', { name: /^Add/ }).click();
  await page.getByRole('button', { name: /Basket/ }).first().click();
  await page.locator('.cart-row').first().waitFor();
  await page.getByRole('button', { name: /Checkout/ }).click();
  await page.getByRole('dialog', { name: 'Checkout' }).waitFor();
  await page.getByLabel('To', { exact: true }).fill('23:59');
  await page.getByRole('button', { name: /Place order/ }).click();
  await page.getByText(/Order #\d+ placed/).waitFor({ timeout: 10000 });

  await page.getByRole('link', { name: 'Rides & parcels' }).click();
  await page.getByRole('tab', { name: 'Send a parcel' }).click();
  await page.getByRole('combobox', { name: 'Pickup' }).fill('mal');
  await page.getByRole('option', { name: /Malviya Nagar/ }).click();
  await page.getByRole('combobox', { name: 'Drop-off' }).fill('vaish');
  await page.getByRole('option', { name: /Vaishali Nagar/ }).click();
  await page.getByLabel('Recipient name').fill('Test Recipient');
  await page.getByLabel('Recipient phone').fill('+919876500000');
  await page.getByRole('button', { name: /Get fares/ }).click();
  await page.locator('.vehicle-option').first().waitFor();
  await shot('place-autocomplete');
  await page.getByRole('button', { name: /Book Bike courier/ }).click();
  await page.getByText(/Parcel requested/).waitFor({ timeout: 10000 });

  const mobile = await context.newPage();
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto(`${BASE}/shop`);
  await mobile.locator('.product-card').first().waitFor();
  await mobile.screenshot({ path: path.join(SHOTS, 'v3-mobile-shop.png') });
  await mobile.close();

  assert.deepEqual(errors, [], `Browser errors: ${errors.join('; ')}`);
  console.log('E2E passed: admin session table, shop checkout, place autocomplete, parcel booking, mobile layout.');
} catch (error) {
  console.error('E2E DEBUG', page.url(), (await page.locator('body').innerText().catch(() => '')).slice(0, 800), errors);
  await shot('failure').catch(() => {});
  throw error;
} finally {
  await browser.close();
}
