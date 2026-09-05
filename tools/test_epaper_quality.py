"""Isolated upload/storage and Chrome viewer regression checks.

Run: .venv/Scripts/python tools/test_epaper_quality.py
Requires Flask-Limiter, PyMuPDF, Pillow and Playwright plus installed Chrome.
Cloudinary delivery is simulated with real resized images; no live services or
production edition files are touched. Browser results are saved under tests/.
"""
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz
from PIL import Image
from flask import Flask, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


class EpaperQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.temp = Path(cls.stack.enter_context(tempfile.TemporaryDirectory()))
        cls.app = Flask(__name__, static_folder=str(ROOT / 'static'),
                        template_folder=str(ROOT / 'templates'))
        cls.app.config.update(TESTING=True, SECRET_KEY='isolated-test', RATELIMIT_ENABLED=False)
        cls.app.add_url_rule('/static/uploads/epaper/<path:filename>', 'test_upload',
                             lambda filename: send_from_directory(cls.temp / 'missing', filename))
        # The blueprint imports only limiter from app; avoid main-app startup,
        # credentials, background jobs and unrelated database connections.
        app_module = types.ModuleType('app')
        app_module.limiter = Limiter(get_remote_address, app=cls.app, storage_uri='memory://')
        cls.stack.enter_context(patch.dict(sys.modules, {'app': app_module}))
        cls.stack.enter_context(patch.dict(os.environ, {
            'CLOUDINARY_URL': '', 'MONGO_DISABLED': '1', 'MONGODB_URI': '',
            'UPSTASH_REDIS_REST_URL': '', 'UPSTASH_REDIS_REST_TOKEN': '',
        }))
        import epaper_routes as routes
        import epaper_storage as storage
        cls.routes, cls.storage = routes, storage
        cls.app.register_blueprint(routes.epaper_bp)
        navbar = (ROOT / 'templates/_shared_index_navbar.html').read_text(encoding='utf-8')
        for endpoint in set(re.findall(r'url_for\([\'"]([^\'"]+)', navbar)):
            if endpoint not in cls.app.view_functions:
                cls.app.add_url_rule('/test-nav/' + endpoint, endpoint, lambda: '')
        for module in (routes, storage):
            cls.stack.enter_context(patch.object(module, 'pg_url', return_value=''))
        cls.stack.enter_context(patch.object(storage, 'EDITIONS_FILE', str(cls.temp / 'editions.json')))
        cls.stack.enter_context(patch.object(storage, 'EDITIONS_TMP', str(cls.temp / 'fallback.json')))
        cls.stack.enter_context(patch.object(routes, 'EPAPER_TMP_UPLOAD_DIR', str(cls.temp)))
        cls.stack.enter_context(patch.object(routes, 'EPAPER_UPLOAD_DIR', str(cls.temp / 'missing')))
        cls.stack.enter_context(patch.object(routes, 'load_editions', storage.load_editions_from_file))
        cls.stack.enter_context(patch.object(routes, 'fast_load_single_edition', return_value=None))
        cls.stack.enter_context(patch.object(routes, 'fast_editions_list_from_pg', return_value=None))
        for name in ('invalidate_editions_cache', 'save_edition_backup', 'send_new_edition_notification',
                     'redis_set', 'increment_edition_view'):
            cls.stack.enter_context(patch.object(routes, name, return_value=None))
        cls.stack.enter_context(patch.object(routes, 'redis_get', return_value=None))
        cls.client = cls.app.test_client()
        with cls.client.session_transaction() as session:
            session['epaper_admin_auth'] = True
        doc = fitz.open()
        for number in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((30, 45), f'NEWSPAPER QUALITY CHECK - PAGE {number + 1}', fontsize=20)
            for y in range(65, 820, 12):
                page.insert_text((30, y), 'Small newspaper text: education, admissions, exams. 0123456789', fontsize=8)
        cls.pdf = doc.tobytes()
        doc.close()

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def test_upload_storage_viewer(self):
        response = self.client.post('/api/epaper/admin/pdf-to-pages',
                                    data={'pdf': (io.BytesIO(self.pdf), 'newspaper.pdf')})
        self.assertEqual(response.status_code, 200)
        urls = response.json['pages']
        self.assertEqual(len(urls), 2)
        images = []
        for url in urls:
            stored = self.client.get(url)
            self.assertEqual(stored.status_code, 200)
            img = Image.open(io.BytesIO(stored.data))
            self.assertGreater(img.width, 2400)
            images.append(stored.data)
            stored.close()

        # Test the unchanged single-image and single-PDF upload paths too.
        for content, filename in ((images[0], 'scan.jpg'), (self.pdf, 'first-page.pdf')):
            response = self.client.post('/api/epaper/admin/upload-image',
                                        data={'image': (io.BytesIO(content), filename)})
            self.assertEqual(response.status_code, 201)
            self.assertTrue(response.json['url'])
            with self.client.get(response.json['url']) as stored:
                self.assertEqual(stored.status_code, 200)
                self.assertGreater(Image.open(io.BytesIO(stored.data)).width, 2000)
        self.assertEqual(self.app.test_client().post('/api/epaper/admin/pdf-to-pages').status_code, 401)
        self.assertEqual(self.client.post('/api/epaper/admin/pdf-to-pages',
                         data={'pdf': (io.BytesIO(b'bad'), 'bad.txt')}).status_code, 400)

        edition = {'date': '2026-09-05', 'name': 'Quality test', 'language': 'English',
                   'published': True, 'pages': [
                       {'page_number': i + 1, 'page_image_url': url, 'blocks': []}
                       for i, url in enumerate(urls)]}
        saved = self.client.post('/api/epaper/admin/edition', json=edition)
        self.assertEqual(saved.status_code, 201, saved.data)
        loaded = self.client.get('/api/epaper/edition/2026-09-05?lang=English')
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual([p['page_image_url'] for p in loaded.json['pages']], urls)
        self.assertTrue((self.temp / 'editions.json').is_file())
        html = self.client.get('/epaper/english/2026-09-05')
        self.assertEqual(html.status_code, 200)
        self.assertIn(b'20260905-sharp-pages', html.data)
        self.check_browser(edition, images)

    def check_browser(self, edition, images):
        from playwright.sync_api import sync_playwright
        output = ROOT / 'tests' / 'epaper-quality'
        output.mkdir(parents=True, exist_ok=True)
        chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
        cloud = 'https://res.cloudinary.com/test/image/upload/v1/'
        remote = json.loads(json.dumps(edition))
        remote['pages'][0]['page_image_url'] = cloud + 'page1.jpg'
        remote['pages'][1]['page_image_url'] = cloud + 'page2.jpg'
        remote['pages'][1]['blocks'] = [
            {'id': 'article-test', 'type': 'article', 'headline': 'Read article',
             'body_text': 'Existing article content.', 'x': 20, 'y': 30, 'w': 400, 'h': 500,
             'image_url': cloud + 'block.jpg'}]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=str(chrome), headless=True)
            for mobile, viewport, dpr in [(False, {'width': 1440, 'height': 1000}, 1),
                                          (True, {'width': 390, 'height': 844}, 3)]:
                context = browser.new_context(viewport=viewport, device_scale_factor=dpr,
                                              is_mobile=mobile, has_touch=mobile)
                requests, errors = [], []
                failures = {'enabled': False, 'delay': False}
                delayed = []
                cache = {}

                def route_request(route):
                    from urllib.parse import urlsplit
                    req = route.request
                    parsed = urlsplit(req.url)
                    if parsed.hostname == 'res.cloudinary.com':
                        requests.append(req.url)
                        match = re.search(r'w_(\d+)', parsed.path)
                        width = int(match[1]) if match else 2480
                        if failures['enabled'] and width > 800:
                            route.fulfill(status=503, body='test failure')
                            return
                        if failures['delay'] and 'stale.jpg' in parsed.path and width > 800:
                            delayed.append(route)
                            return
                        key = (parsed.path.rsplit('/', 1)[-1], width)
                        if key not in cache:
                            img = Image.open(io.BytesIO(images[1 if 'page2' in key[0] else 0]))
                            if width < img.width:
                                img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
                            buf = io.BytesIO()
                            img.save(buf, 'JPEG', quality=95)
                            cache[key] = buf.getvalue()
                        route.fulfill(content_type='image/jpeg', body=cache[key])
                    elif parsed.hostname == 'epaper.test':
                        path = parsed.path + ('?' + parsed.query if parsed.query else '')
                        if path == '/test-file.pdf':
                            route.fulfill(content_type='application/pdf', body=self.pdf)
                        elif path.startswith('/api/epaper/edition/') and path.endswith('/view'):
                            route.fulfill(json={'views': 1})
                        else:
                            response = self.client.open(path, method=req.method, data=req.post_data)
                            route.fulfill(status=response.status_code, body=response.data,
                                          content_type=response.content_type)
                            response.close()
                    else:
                        route.fulfill(status=200, body='')

                context.route('**/*', route_request)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto('http://epaper.test/epaper/english/2026-09-05')
                page.wait_for_function('window.EP && EP.pages.length === 2 && EP.el.pageImg.complete')
                self.assertTrue(page.evaluate('''() => {
                  const source = 'https://res.cloudinary.com/test/image/upload/f_auto,q_auto,w_160/v1/page.jpg?keep=1';
                  const result = EP.pageImageUrl(source, 2400);
                  return result.includes('c_limit,w_2400/f_auto/q_auto:best/v1/page.jpg?keep=1') &&
                    EP.pageImageUrl(result, 2400) === result &&
                    EP.pageImageUrl('/local.jpg', 2400) === '/local.jpg' &&
                    EP.pageImageUrl('https://example.com/scan.png', 2400) === 'https://example.com/scan.png';
                }'''))
                # The actual locally uploaded PDF pages render unchanged.
                self.assertGreater(page.evaluate('EP.el.pageImg.naturalWidth'), 2400)
                page.evaluate('(edition) => EP.applyEditionData(edition, false)', remote)
                page.wait_for_timeout(900)
                page.evaluate('EP.el.viewer.scrollIntoView()')
                page.wait_for_timeout(500)
                self.assertFalse(any('page2.jpg' in url and 'w_160' not in url for url in requests))
                self.assertTrue(all('w_160' in src for src in page.locator('.ep-thumb-img').evaluate_all('(els) => els.map(e => e.src)')))
                page.locator('#epZoomIn').click()
                page.wait_for_timeout(650)
                self.assertGreater(page.evaluate('EP.zoom'), 1)
                page.evaluate('EP.setZoom(3); EP.el.viewer.scrollIntoView()')
                page.wait_for_timeout(900)
                self.assertEqual(page.evaluate('EP.zoom'), 3)
                self.assertGreater(page.evaluate('EP.el.pageImg.naturalWidth'), 800)
                page.screenshot(path=str(output / ('mobile-zoom.png' if mobile else 'desktop-zoom.png')))
                previous = page.evaluate('EP.el.pageImg.src')
                page.evaluate('EP.fitToWidth()')
                page.wait_for_timeout(450)
                self.assertEqual(page.evaluate('EP.el.pageImg.src'), previous)
                if mobile:
                    page.evaluate('''() => {
                      const target = EP.el.viewer;
                      const touches = (x) => [new Touch({identifier: 1, target, clientX: 50, clientY: 250}),
                        new Touch({identifier: 2, target, clientX: x, clientY: 250})];
                      target.dispatchEvent(new TouchEvent('touchstart', {touches: touches(150), bubbles: true}));
                      target.dispatchEvent(new TouchEvent('touchmove', {touches: touches(250), bubbles: true}));
                      target.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: touches(250), bubbles: true}));
                    }''')
                    page.wait_for_timeout(450)
                    self.assertEqual(page.evaluate('EP.zoom'), 2)
                    page.set_viewport_size({'width': 844, 'height': 390})
                    page.wait_for_timeout(500)
                    self.assertEqual(page.evaluate('EP.zoom'), 2)
                    page.set_viewport_size(viewport)
                    page.evaluate('EP.fitToWidth()')
                    page.wait_for_timeout(450)
                # Fullscreen uses the existing control and must retain a loaded scan.
                page.locator('#epFullscreen').click()
                page.wait_for_timeout(450)
                self.assertTrue(page.evaluate('!!document.fullscreenElement'))
                page.evaluate('EP.setZoom(2)')
                page.wait_for_timeout(450)
                self.assertEqual(page.evaluate('EP.zoom'), 2)
                page.evaluate('document.exitFullscreen()')
                page.wait_for_timeout(450)
                page.locator('.ep-thumb-card').nth(1).click()
                page.wait_for_timeout(1100)
                self.assertEqual(page.evaluate('EP.currentPage'), 2)
                page.evaluate('EP.setZoom(3); EP.el.viewer.scrollIntoView()')
                page.wait_for_timeout(900)
                self.assertIn('q_auto:best', page.locator('.ep-canvas-viewer').evaluate('(e) => e.style.backgroundImage'))
                self.assertGreater(page.locator('.ep-block-img').evaluate('(e) => e.naturalWidth'), 400)
                self.assertEqual(page.evaluate('EP.articles[0].body_text'), 'Existing article content.')
                page.locator('#epPrevPage').click()
                page.wait_for_timeout(1100)
                self.assertEqual(page.evaluate('EP.currentPage'), 1)
                # Failed upgrades preserve a readable preview and do not reset zoom.
                failures['enabled'] = True
                failed = json.loads(json.dumps(remote))
                failed['pages'][0]['page_image_url'] = cloud + 'failure.jpg'
                page.evaluate('(edition) => EP.applyEditionData(edition, false)', failed)
                page.wait_for_timeout(500)
                page.evaluate('EP.setZoom(3); EP.el.viewer.scrollIntoView()')
                page.wait_for_timeout(700)
                self.assertEqual(page.evaluate('EP.zoom'), 3)
                self.assertEqual(page.evaluate('EP.el.pageImg.naturalWidth'), 800)

                # A response from the previous page must never replace the new one.
                failures.update(enabled=False, delay=True)
                stale = json.loads(json.dumps(remote))
                stale['pages'][0]['page_image_url'] = cloud + 'stale.jpg'
                page.evaluate('(edition) => EP.applyEditionData(edition, false)', stale)
                page.wait_for_timeout(500)
                page.evaluate('EP.setZoom(3); EP.el.viewer.scrollIntoView()')
                page.wait_for_timeout(500)
                self.assertTrue(delayed)
                page.evaluate('EP.renderPageDirect(2)')
                page.wait_for_timeout(500)
                for delayed_route in delayed:
                    delayed_route.fulfill(content_type='image/jpeg', body=images[0])
                page.wait_for_timeout(300)
                self.assertEqual(page.evaluate('EP.currentPage'), 2)
                self.assertNotIn('stale.jpg', page.locator('.ep-canvas-viewer').evaluate('(e) => e.style.backgroundImage'))
                self.assertTrue(page.evaluate("EP._pageQualityImages.every(s => !s.source.includes('stale.jpg'))"))

                # Existing PDF URLs retain the native iframe path, without transforms.
                legacy = json.loads(json.dumps(edition))
                legacy['pages'][0]['page_image_url'] = '/test-file.pdf'
                page.evaluate('(edition) => EP.applyEditionData(edition, false)', legacy)
                page.wait_for_timeout(300)
                self.assertTrue(page.locator('#epPdfFrame').is_visible())
                self.assertEqual(page.locator('#epPdfFrame').get_attribute('src'), '/test-file.pdf')
                self.assertEqual(page.evaluate('EP._pageQualityImages.length'), 0)
                self.assertEqual(errors, [])
                print(f'PASS {"mobile DPR3" if mobile else "desktop"}: upload display, zoom, fullscreen, thumbnails, navigation, blocks, CDN failure, stale response, legacy PDF')
                context.close()
            browser.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
