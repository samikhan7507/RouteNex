const { chromium } = require('playwright-core');
const assert = require('assert');
const base = process.env.ROUTENEX_BASE_URL || 'http://127.0.0.1:8000';

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined, args:['--no-sandbox', '--disable-dev-shm-usage'], headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base); await page.locator('#email').fill('customer@routenex.in');
  await page.locator('#password').fill('Demo@123'); await page.locator('#loginForm button').click();
  await page.locator('#app:not(.hidden)').waitFor();
  await page.locator('#nav button').filter({hasText:'Shop'}).click();
  await page.locator('#shopGrid .shopcard').first().waitFor();
  assert.equal(await page.locator('#shopGrid .shop-photo').count(), 10);
  assert.equal(await page.locator('#shopGrid .shop-illustrative').count(), 10);
  for (const img of await page.locator('#shopGrid .shop-photo').all()) {
    await img.scrollIntoViewIfNeeded();
    await img.evaluate(el => el.decode());
    assert(await img.evaluate(el => el.naturalWidth > 0));
  }
  const first = page.locator('.shopcard').filter({hasText:'Ruled Notebook, A4 (200 pages)'});
  assert((await first.locator('img').getAttribute('src')).endsWith('/ruled-notebook.jpg'));
  await first.getByRole('button',{name:'Add one Ruled Notebook, A4 (200 pages)'}).click();
  assert.equal(await first.locator('.quantity b').textContent(), '1');
  assert(await page.locator('#cartBar').isVisible());
  await page.locator('#shopChips button').filter({hasText:'Books & Exam Prep'}).click();
  assert.equal(await page.locator('#shopGrid .shop-photo').count(), 2);
  await page.locator('#shopQ').fill('chemistry');
  assert.equal(await page.locator('#shopGrid .shopcard').count(), 1);
  assert(await page.locator('#shopGrid .shop-fallback').isVisible());
  await page.locator('#shopSort').selectOption('low');
  await page.setViewportSize({width:390,height:844});
  assert((await page.evaluate(() => document.documentElement.scrollWidth)) <= 390);
  assert(await page.locator('#shopGrid .shopcard').isVisible());
  assert.equal(await page.evaluate(() => {
    const f = window.__rnShop.imageFor;
    return f({name:'Ruled Notebook, A4 (200 pages)', image_url:'/static/product-images/custom.jpg'}).url;
  }), '/static/product-images/custom.jpg');
  assert.equal(await page.evaluate(() => window.__rnShop.imageFor({name:'unknown', image_url:'https://example.com/a.jpg'})), null);
  // Exercise a genuinely broken image, including removal of the illustration label.
  await page.locator('#shopQ').fill('');
  await page.locator('#shopChips button').filter({hasText:'Stationery'}).click();
  const broken = page.locator('.shopcard').filter({hasText:'Ruled Notebook, A4 (200 pages)'});
  await broken.scrollIntoViewIfNeeded();
  await broken.locator('img').evaluate(el => { el.src = '/static/product-images/does-not-exist.jpg'; });
  await broken.locator('img').waitFor({state:'detached'});
  assert(await broken.locator('.shop-fallback').isVisible());
  assert.equal(await broken.locator('.shop-illustrative').count(),0);
  assert.deepEqual(errors, []);
  await browser.close(); console.log('Shop images, fallback, filters, cart and mobile: OK');
})().catch(e=>{console.error(e);process.exit(1)});
