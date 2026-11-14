const { chromium } = require('playwright-core');
const assert = require('assert');
const base = process.env.ROUTENEX_BASE_URL || 'http://127.0.0.1:8000';
const adminEmail = process.env.TEST_ADMIN_EMAIL || 'admin@test.in';
const adminPassword = process.env.TEST_ADMIN_PASSWORD || 'owner-pass-123';
async function checkControlSizes(page, sidebarVisible) {
  for (const selector of ['#refresh', ...(sidebarVisible ? ['#logout'] : [])]) {
    const button = page.locator(selector);
    const box = await button.boundingBox();
    const icon = await button.locator('svg').boundingBox();
    assert(box && box.height >= 40 && box.height <= 56, `${selector} height: ${box && box.height}`);
    assert(icon && icon.width <= 22 && icon.height <= 22, `${selector} icon: ${JSON.stringify(icon)}`);
  }
}

(async () => {
 const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox', '--disable-dev-shm-usage'], headless:true});
 const roles = ['customer@routenex.in','driver@routenex.in','dispatcher@routenex.in','fleet@routenex.in',adminEmail];
 for (const email of roles) {
  const page = await browser.newPage({viewport:{width:390,height:844}, deviceScaleFactor:1});
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));
  await page.goto(base + '/',{waitUntil:'domcontentloaded'});
  await page.locator('#email').fill(email); await page.locator('#password').fill(email===adminEmail ? adminPassword : 'Demo@123');
  await page.locator('#loginForm button').click(); await page.locator('#app:not(.hidden)').waitFor();
  await page.waitForTimeout(500);
  assert(await page.locator('#navToggle').isVisible()); assert(!(await page.locator('#appSidebar').isVisible()));
  await checkControlSizes(page, false);
  await page.locator('#navToggle').click();
  assert.equal(await page.locator('#navToggle').getAttribute('aria-expanded'),'true');
  await page.locator('#appSidebar').waitFor({state:'visible'}); await page.waitForFunction(() => document.activeElement.id === 'navClose');
  assert.equal(await page.locator('#appSidebar').getAttribute('role'),'dialog');
  assert((await page.locator('#nav button').count()) >= 3);
  const labels=await page.locator('#nav button').allTextContents();
  await page.keyboard.press('Shift+Tab'); assert(await page.locator('#logout').evaluate(el=>el===document.activeElement));
  await page.keyboard.press('Tab'); assert(await page.locator('#navClose').evaluate(el=>el===document.activeElement));
  await page.keyboard.press('Escape'); assert.equal(await page.locator('#navToggle').getAttribute('aria-expanded'),'false');
  assert(await page.locator('#navToggle').evaluate(el=>el===document.activeElement));
  await page.locator('#navToggle').click(); await page.locator('#nav button').nth(1).click();
  assert.equal(await page.locator('#navToggle').getAttribute('aria-expanded'),'false');
  assert.equal(await page.locator('#nav button').nth(1).getAttribute('aria-current'),'page');
  await page.locator('#refresh').click();
  await page.locator('#navToggle').click(); await page.locator('#navBackdrop').click({position:{x:380,y:300}});
  assert.equal(await page.locator('#navToggle').getAttribute('aria-expanded'),'false');
  let width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
  assert(width.scroll<=width.client,JSON.stringify(width));
  await page.setViewportSize({width:1440,height:900});
  assert(await page.locator('#appSidebar').isVisible()); await checkControlSizes(page, true);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.locator('#logout2').count(), 0);
  await page.locator('#navToggle').click(); await page.locator('#logout').click();
  assert(await page.locator('#auth').isVisible());
  assert.equal(await page.evaluate(() => localStorage.getItem('rn_session')), null);
  assert.equal(await page.evaluate(() => document.body.classList.contains('nav-open')), false);
  assert(errors.length===0,errors.join('\n')); console.log(email,labels.join(' | '));
  await page.close();
 }
 const page = await browser.newPage({viewport:{width:1440,height:900}}); await page.goto(base + '/');
 await page.locator('#email').fill(adminEmail); await page.locator('#password').fill(adminPassword); await page.locator('#loginForm button').click(); await page.locator('#app:not(.hidden)').waitFor();
 assert(!(await page.locator('#navToggle').isVisible())); assert(await page.locator('#appSidebar').isVisible()); assert(await page.locator('#logout').isVisible()); assert.equal(await page.locator('#logout2').count(), 0);
 await page.setViewportSize({width:320,height:540});
 assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= 320);
 assert(await page.locator('#refresh').isVisible()); assert.equal(await page.locator('#logout2').count(), 0);
 await page.locator('#navToggle').click(); await page.locator('#nav button').last().click();
 assert.equal(await page.locator('#navToggle').getAttribute('aria-expanded'), 'false');
 await page.setViewportSize({width:600,height:844}); assert(await page.locator('#navToggle').isVisible());
 await page.locator('#navToggle').click(); await page.setViewportSize({width:1440,height:900});
 assert(await page.locator('#appSidebar').isVisible()); assert.equal(await page.locator('#appMain').evaluate(el=>el.inert),false);
 await page.setViewportSize({width:1440,height:900}); await checkControlSizes(page, true);
 await page.locator('#logout').click(); assert(await page.locator('#auth').isVisible());
 assert.equal(await page.evaluate(() => localStorage.getItem('rn_session')), null);
 await page.locator('#email').fill(adminEmail); await page.locator('#password').fill(adminPassword);
 await page.locator('#loginForm button').click(); await page.locator('#app:not(.hidden)').waitFor();
 // Seed a stale unversioned stylesheet as if an earlier installed app had cached it.
 // The current versioned app shell must still render correctly after going offline.
 await page.evaluate(async () => {
   const reg = await navigator.serviceWorker.ready;
   await new Promise(resolve => { if (reg.active) resolve(); else reg.addEventListener('updatefound', resolve, {once:true}); });
   const cache = await caches.open('routenex-shell-v13');
   await cache.put('/static/styles.css', new Response('svg { width: 250px; height: 250px; }', {headers:{'Content-Type':'text/css'}}));
 });
 await page.context().setOffline(true); await page.reload({waitUntil:'domcontentloaded'});
 await page.locator('#app:not(.hidden)').waitFor(); await checkControlSizes(page, true);
 console.log('desktop, resize and stale-cache offline shell: OK'); await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
