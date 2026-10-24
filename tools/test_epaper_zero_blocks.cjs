/* Isolated Chrome regression tests. Requires Python (Flask + Pillow), Chrome,
 * and playwright-core: npm install --prefix .venv-test/browser --no-save playwright-core
 * Run: node tools/test_epaper_zero_blocks.cjs
 * Add --baseline before committing to reproduce the bug using HEAD's template.
 * All requests are intercepted locally; no production app or data is accessed.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require('../.venv-test/browser/node_modules/playwright-core');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(execFileSync(process.env.PYTHON || 'python', [
  path.join(__dirname, 'epaper_viewer_fixture.py'), ...process.argv.slice(2),
], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }));
const output = path.join(root, 'tests', 'epaper-zero-blocks');
fs.mkdirSync(output, { recursive: true });

async function check(browser, mobile) {
  const context = await browser.newContext({
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
    isMobile: mobile, hasTouch: mobile,
  });
  const errors = [];
  await context.route('**/*', async route => {
    const parsed = new URL(route.request().url());
    const p = parsed.pathname;
    if (parsed.hostname !== 'epaper.test') {
      // Exercise the standard reader with optional external CDN scripts unavailable.
      return route.fulfill({ status: 200, body: '' });
    }
    if (fixture.images[p]) {
      return route.fulfill({ contentType: 'image/jpeg', body: Buffer.from(fixture.images[p], 'base64') });
    }
    if (p === '/api/epaper/editions' || p.startsWith('/api/epaper/editions-by-date/')) {
      return route.fulfill({ json: { editions: [fixture.edition] } });
    }
    if (p.endsWith('/view') || p.endsWith('/views')) return route.fulfill({ json: { views: 1 } });
    if (p.startsWith('/api/epaper/edition/') || p === '/api/epaper/latest') {
      return route.fulfill({ json: fixture.edition });
    }
    if (p.startsWith('/api/')) return route.fulfill({ json: {} });
    if (p.startsWith('/static/')) {
      const file = path.resolve(root, '.' + p);
      assert.ok(file.startsWith(path.join(root, 'static') + path.sep));
      if (fs.existsSync(file) && fs.statSync(file).isFile()) return route.fulfill({ path: file });
    }
    if (p === '/epaper/marathi/2026-10-19') {
      return route.fulfill({ contentType: 'text/html', body: fixture.html });
    }
    return route.fulfill({ status: 200, body: '' });
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('http://epaper.test/epaper/marathi/2026-10-19');
    await page.waitForFunction(() => window.EP && EP.pages.length === 5);
    assert.equal(await page.locator('#epPageImg').count(), 1,
      'Uploaded pages need a standard image container even with zero blocks');
    async function assertScan(number) {
      await page.waitForFunction(n => EP.currentPage === n && EP.el.pageImg &&
        EP.el.pageImg.complete && EP.el.pageImg.naturalWidth === 800 &&
        EP.el.pageImg.src.endsWith('/test-page-' + n + '.jpg'), number);
      assert.ok(await page.locator('#epPageContainer').isVisible());
      const box = await page.locator('#epPageImg').boundingBox();
      assert.ok(box.width > 250);
      assert.ok(Math.abs(box.height / box.width - 1131 / 800) < 0.01,
        'The full newspaper scan must retain its aspect ratio');
    }
    await assertScan(1);
    await page.screenshot({ path: path.join(output, mobile ? 'mobile-zero-blocks.png' : 'desktop-zero-blocks.png') });
    const originalWidth = (await page.locator('#epPageImg').boundingBox()).width;
    await page.locator('#epZoomIn').click();
    await page.waitForFunction(() => EP.zoom > 1);
    await page.waitForFunction(width => EP.el.pageImg.getBoundingClientRect().width > width + 10, originalWidth);
    await page.evaluate(() => EP.fitToWidth());

    // Navigate between pages with and without Read More blocks using existing controls.
    await page.locator('.ep-thumb-card').nth(1).click();
    await page.waitForFunction(() => EP.currentPage === 2 && EP.articles.length === 1);
    assert.ok(await page.locator('#epBlockGrid').isVisible());
    await page.locator('.ep-block-card').click();
    await page.waitForFunction(() => EP.currentArticle?.headline === 'Read more test');
    assert.match(await page.locator('#epArtText').innerText(), /Existing article must remain readable\./);
    await page.evaluate(() => EP.closeArticle());
    await page.locator('#epNextPage').click();
    await assertScan(3);
    assert.equal(await page.locator('#epBlockGrid').isVisible(), false);
    assert.equal(await page.evaluate(() => EP.articles.length), 0);
    await page.locator('.ep-thumb-card').nth(3).click();
    await assertScan(4);
    await page.locator('.ep-thumb-card').nth(4).click();
    await assertScan(5);
    assert.equal(await page.locator('#epHotspots .ep-hotspot').count(), 1);
    await page.locator('#epHotspots .ep-hotspot').click();
    assert.equal(await page.evaluate(() => EP.currentArticle.headline), 'Legacy article');
    await page.evaluate(() => EP.closeArticle());
    // The floating chatbot overlaps the bottom of the first thumbnail.
    await page.locator('.ep-thumb-card').nth(0).locator('.ep-thumb-label').click();
    await assertScan(1);
    assert.equal(await page.locator('#epHotspots .ep-hotspot').count(), 0);
    await page.locator('#epFullscreen').click();
    await page.waitForFunction(() => !!document.fullscreenElement);
    await assertScan(1);
    await page.evaluate(() => document.exitFullscreen());
    await page.waitForFunction(() => !document.fullscreenElement);

    // Preserve native PDF rendering and recover to the standard image afterwards.
    await page.evaluate(() => {
      EP.pages.push({ page_image_url: '/test.pdf', blocks: [] });
      EP.totalPages = EP.pages.length;
      EP.renderPageDirect(6);
    });
    assert.ok(await page.locator('#epPdfFrame').isVisible());
    await page.evaluate(() => EP.renderPageDirect(1));
    await assertScan(1);
    assert.equal(await page.locator('#epPdfFrame').isVisible(), false);
    assert.deepEqual(errors, []);
    console.log(`PASS ${mobile ? 'mobile' : 'desktop'}: zero/missing blocks, image_path, navigation, Read More, legacy hotspots, zoom, fullscreen, PDF recovery`);
  } catch (error) {
    console.error('Reader diagnostics:', await page.evaluate(() => ({
      zoom: EP.zoom,
      container: EP.el.pageContainer?.getBoundingClientRect().toJSON(),
      image: EP.el.pageImg?.getBoundingClientRect().toJSON(),
      containerStyle: EP.el.pageContainer?.style.cssText,
    })));
    await page.screenshot({ path: path.join(output, mobile ? 'mobile-failure.png' : 'desktop-failure.png') });
    throw error;
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({
    executablePath: path.join(process.env.PROGRAMFILES || 'C:/Program Files', 'Google/Chrome/Application/chrome.exe'),
    headless: true,
  });
  try {
    await check(browser, false);
    await check(browser, true);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
