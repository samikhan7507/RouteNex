const { chromium } = require('playwright-core');
const assert = require('assert');
const base = process.env.ROUTENEX_BASE_URL || 'http://127.0.0.1:8000';
const adminEmail = process.env.TEST_ADMIN_EMAIL || 'admin@test.in';
const adminPassword = process.env.TEST_ADMIN_PASSWORD || 'owner-pass-123';

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined, args:['--no-sandbox','--disable-dev-shm-usage'], headless:true});
  for (const timezoneId of ['America/Los_Angeles', 'Asia/Kolkata']) {
    const context = await browser.newContext({timezoneId, serviceWorkers:'block', viewport:{width:1440,height:900}});
    const page = await context.newPage(), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base); await page.locator('#email').fill(adminEmail); await page.locator('#password').fill(adminPassword);
    await page.locator('#loginForm button').click(); await page.locator('#app:not(.hidden)').waitFor();
    await page.locator('#nav button').filter({hasText:'Users & Audit'}).click();
    const realEvent = page.locator('.audit-event').filter({hasText: adminEmail}).first();
    await realEvent.waitFor(); assert((await realEvent.textContent()).includes('LOGIN'));
    assert((await realEvent.locator('.audit-time').textContent()).endsWith(' IST'));
    const timestamps = ['2026-11-14 19:17:58', '2026-11-14 19:17:58.192432+00', '2026-11-14T19:17:58Z', '2026-11-15 00:47:58+05:30', '2026-11-14T14:17:58-0500', 'not-a-date'];
    await page.route('**/api/audit', r => r.fulfill({json:timestamps.map((created_at,i) => ({user_id:i+1, entity_id:String(i+1), action:'LOGIN', entity:'user', name:i===0 ? '<img src=x>' : 'User '+i, user_role:'fleet_manager', user_email:'test@example.in', created_at}))}));
    await page.locator('#refresh').click();
    await page.waitForFunction(() => document.querySelectorAll('.audit-event').length === 6);
    const times = await page.locator('.audit-time').allTextContents();
    assert(times.slice(0,5).every(t => t === times[0]), JSON.stringify(times));
    assert(/15[- ]Nov[- ]2026/.test(times[0]) && /12:47:58/.test(times[0]) && times[0].endsWith(' IST'), times[0]);
    assert.equal(times[5], 'Time unavailable');
    assert((await page.locator('.audit-person').first().textContent()).includes('<img src=x> · fleet manager · test@example.in'));
    assert.equal(await page.locator('.audit-person img').count(), 0);
    assert((await page.locator('.audit-note').textContent()).includes('Indian Standard Time'));
    await page.setViewportSize({width:390,height:844});
    assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= 390);
    assert.deepEqual(errors, []); await context.close();
    console.log(timezoneId, times[0]);
  }
  await browser.close(); console.log('Audit login identity, UTC offsets, IST display, invalid timestamps and mobile: OK');
})().catch(e=>{console.error(e);process.exit(1)});
