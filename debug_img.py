from curl_cffi import requests
from bs4 import BeautifulSoup
import re

url = 'https://www.lcmusedcarcenter.com/used/honda-cars-for-sale-lancaster-pa.htm'
resp = requests.get(url, impersonate='chrome', timeout=30)
soup = BeautifulSoup(resp.text, 'html.parser')

MEDIA_SKIP_WIDGETS = [
    'ws-inv-', 'inventory-listing', 'inventory-search',
    'ws-specials', 'specials-listing', 'specials-widget',
    'navigation', 'ws-navigation', 'header-default',
]

def _is_excluded_widget(tag):
    p = tag
    while p:
        wn = p.get('data-widget-name', p.get('data-widget-id', p.get('data-name', ''))) or ''
        wn = wn.lower()
        if any(skip in wn for skip in MEDIA_SKIP_WIDGETS):
            return True
        if p.name in ['nav', 'header']:
            return True
        p = p.parent
    return False

def _extract_img_srcs(tag):
    srcs = set()
    src = tag.get('src', '')
    if src and not src.startswith('data:') and len(src) > 5:
        srcs.add(src)
    data_src = tag.get('data-src', '')
    if data_src and not data_src.startswith('data:') and len(data_src) > 5:
        srcs.add(data_src)
    style = tag.get('style', '')
    bg_urls = re.findall(r'url\(["\']?(https?://[^"\')\s]+|//[^"\')\s]+)["\']?\)', style)
    for bg in bg_urls:
        if not bg.startswith('data:'):
            srcs.add(bg)
    bg2 = tag.get('data-bg', '') or tag.get('data-lazy-src', '')
    if bg2 and not bg2.startswith('data:'):
        srcs.add(bg2)
    return srcs

analyzed = []
for img_tag in soup.find_all('img'):
    if _is_excluded_widget(img_tag): continue
    img_classes = img_tag.get('class') or []
    if any(c in img_classes for c in ['ddc-loader']): continue

    for src in _extract_img_srcs(img_tag):
        w = img_tag.get('width', '')
        h = img_tag.get('height', '')
        if (w == '1' and h == '1') or 'facebook.com/tr' in src or 'googleadservices.com' in src:
            continue
        analyzed.append(src)

for el in soup.find_all(style=re.compile(r'pictures\.dealer\.com', re.I)):
    if _is_excluded_widget(el): continue
    for src in _extract_img_srcs(el):
        if src and not src.startswith('data:'):
            analyzed.append(src)

for src in analyzed:
    print('SRC:', src)
