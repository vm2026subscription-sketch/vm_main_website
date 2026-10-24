"""Render isolated browser fixtures without importing the production app.

Used by test_epaper_zero_blocks.cjs. No database or live services are accessed.
"""
import base64
import io
import json
from pathlib import Path
import re
import subprocess
import sys

from flask import Flask, render_template
from jinja2 import ChoiceLoader, DictLoader
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def fixtures(baseline=False):
    app = Flask(__name__, static_folder=str(ROOT / 'static'),
                template_folder=str(ROOT / 'templates'))
    app.config.update(TESTING=True, SECRET_KEY='isolated-viewer-test')
    if baseline:
        original = subprocess.check_output(
            ['git', 'show', 'HEAD:templates/epaper_viewer.html'], cwd=ROOT).decode('utf-8')
        app.jinja_loader = ChoiceLoader([DictLoader({'epaper_viewer.html': original}), app.jinja_loader])
    navbar = (ROOT / 'templates/_shared_index_navbar.html').read_text(encoding='utf-8')
    for endpoint in set(re.findall(r'url_for\([\'"]([^\'"]+)', navbar)):
        if endpoint not in app.view_functions:
            app.add_url_rule('/test-nav/' + endpoint, endpoint, lambda: '')
    with app.test_request_context('/epaper/marathi/2026-10-19'):
        html = render_template('epaper_viewer.html', initial_date='2026-10-19',
                               initial_page=1, initial_language='marathi',
                               og_title='Zero block regression', og_url='',
                               og_image='', og_description='')
    edition = {
        'date': '2026-10-19', 'name': 'Regression edition', 'language': 'Marathi',
        'published': True, 'pages': [
            {'page_number': 1, 'page_image_url': '/test-page-1.jpg', 'blocks': []},
            {'page_number': 2, 'page_image_url': '/test-page-2.jpg', 'blocks': [
                {'id': 'read-more', 'type': 'article', 'headline': 'Read more test',
                 'body_text': 'Existing article must remain readable.',
                 'x': 20, 'y': 30, 'w': 400, 'h': 300}]},
            {'page_number': 3, 'image_path': '/test-page-3.jpg', 'blocks': []},
            {'page_number': 4, 'page_image_url': '/test-page-4.jpg'},
            {'page_number': 5, 'page_image_url': '/test-page-5.jpg', 'articles': [
                {'headline': 'Legacy article', 'body_text': 'Legacy article content.',
                 'click_region_x': 5, 'click_region_y': 5,
                 'click_region_w': 30, 'click_region_h': 20}]},
        ]}
    images = {}
    for number in range(1, 6):
        image = Image.new('RGB', (800, 1131), '#fffef4')
        draw = ImageDraw.Draw(image)
        draw.text((30, 30), f'NEWSPAPER PAGE {number}', fill='black')
        for y in range(70, 1100, 20):
            draw.text((30, y), 'Education news - admissions - exams. ' * 3, fill='black')
        data = io.BytesIO()
        image.save(data, 'JPEG')
        images[f'/test-page-{number}.jpg'] = base64.b64encode(data.getvalue()).decode('ascii')
    return {'html': html, 'edition': edition, 'images': images}


if __name__ == '__main__':
    print(json.dumps(fixtures(baseline='--baseline' in sys.argv)))
