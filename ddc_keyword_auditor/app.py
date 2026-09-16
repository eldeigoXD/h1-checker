import os
import re
import json
import time
from urllib.parse import urljoin, urlparse
from flask import Flask, request, jsonify, send_from_directory
from bs4 import BeautifulSoup
try:
    from curl_cffi import requests
except Exception:
    import requests

app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

DOH_GOOGLE = "https://dns.google/dns-query"
DOH_CLOUDFLARE = "https://cloudflare-dns.com/dns-query"

def fetch_html_robust(url, timeout=20):
    """Fetches URL with DoH to prevent ISP DNS blocks on Akamai/Dealer.com nodes."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # Try Google DoH
    try:
        s = requests.Session(impersonate='chrome', verify=False)
        r = s.get(url, timeout=timeout, headers=headers, doh_url=DOH_GOOGLE)
        if r.status_code == 200:
            return r.text, r.status_code
    except Exception as e:
        print(f"[DoH Google] Error: {e}")

    # Try Cloudflare DoH
    try:
        s = requests.Session(impersonate='chrome', verify=False)
        r = s.get(url, timeout=timeout, headers=headers, doh_url=DOH_CLOUDFLARE)
        if r.status_code == 200:
            return r.text, r.status_code
    except Exception as e:
        print(f"[DoH CF] Error: {e}")

    # Try Direct curl_cffi
    try:
        s = requests.Session(impersonate='chrome', verify=False)
        r = s.get(url, timeout=timeout, headers=headers)
        return r.text, r.status_code
    except Exception as e:
        print(f"[Direct curl_cffi] Error: {e}")

    # Fallback to standard requests
    import requests as standard_req
    r = standard_req.get(url, headers=headers, timeout=timeout, verify=False)
    return r.text, r.status_code


def audit_page_keywords(
    html_text: str, 
    keyword: str, 
    case_sensitive: bool = False,
    include_title: bool = True,
    include_metadata: bool = True,
    include_content: bool = True,
    include_images: bool = False,
    include_links: bool = False
) -> dict:
    """
    Audits a DDC page HTML specifically breaking down matches in:
    1. Page Title (<title>)
    2. Head Metadata (description, keywords, og:*, twitter:*, canonical, schema)
    3. Head Scripts & Structured Data
    4. Head Raw Remaining Content
    5. SEO Headings (H1, H2, H3, H4)
    6. Content Widgets & Body Text (p, li, div.content-default, etc.)
    7. Image Tags (alt & title attributes) - Optional toggle
    8. Links & CTAs (href, anchor text, title, button text) - Optional toggle
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Decompose all scripts, styles, and noscript elements so scripts and internal code are never searched
    for el in soup(['script', 'style', 'noscript']):
        el.decompose()

    flags = 0 if case_sensitive else re.IGNORECASE
    escaped_kw = re.escape(keyword)
    regex = re.compile(rf'({escaped_kw})', flags)
    
    def count_matches(text):
        if not text: return 0
        return len(regex.findall(text))

    results = {
        'keyword': keyword,
        'case_sensitive': case_sensitive,
        'scope': {
            'title': include_title,
            'metadata': include_metadata,
            'content': include_content,
            'images': include_images,
            'links': include_links
        },
        'total_matches': 0,
        'title': {'found': False, 'matches': 0, 'value': '', 'occurrences': [], 'enabled': include_title},
        'metadata': {'found': False, 'matches': 0, 'items': [], 'enabled': include_metadata},
        'headings': {'found': False, 'matches': 0, 'items': [], 'enabled': include_content},
        'seo_content': {'found': False, 'matches': 0, 'items': [], 'enabled': include_content},
        'images': {'found': False, 'matches': 0, 'items': [], 'enabled': include_images},
        'links': {'found': False, 'matches': 0, 'items': [], 'enabled': include_links}
    }

    # 1. Title Tag
    if include_title:
        title_tag = soup.find('title')
        title_val = title_tag.get_text(strip=True) if title_tag else ''
        title_cnt = count_matches(title_val)
        if title_cnt > 0:
            results['title'] = {
                'found': True,
                'matches': title_cnt,
                'value': title_val,
                'occurrences': [title_val],
                'enabled': True
            }
            results['total_matches'] += title_cnt
        else:
            results['title']['value'] = title_val
    else:
        results['title']['value'] = ''

    # 2. Head Metadata Tags
    # Only searches customer-facing text in <meta> tags (description, og:title, og:description, keywords, etc.)
    # Explicitly ignores asset links (<link rel="shortcut icon">, <link rel="preload">, CDN files) and scripts
    if include_metadata:
        head = soup.find('head')
        if head:
            for meta in head.find_all('meta'):
                name = meta.get('name') or meta.get('property') or meta.get('http-equiv') or ''
                content = meta.get('content') or ''
                if not content:
                    continue

                # Ignore asset URLs (e.g. image URLs or CDN media paths)
                content_lower = content.lower().strip()
                if content_lower.startswith('http://') or content_lower.startswith('https://'):
                    if any(content_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.css', '.js']):
                        continue
                    if 'pictures.dealer.com' in content_lower:
                        continue

                cnt = count_matches(content)
                if cnt > 0:
                    results['metadata']['items'].append({
                        'tag': f'<meta {name}="...">',
                        'attribute': name,
                        'content': content,
                        'matches': cnt
                    })
                    results['metadata']['matches'] += cnt
                    results['total_matches'] += cnt
                    results['metadata']['found'] = True

    # 3. Headings & 4. SEO Body Content
    if include_content:
        # Headings (H1 - H6)
        for h_tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            txt = h_tag.get_text(separator=' ', strip=True)
            cnt = count_matches(txt)
            if cnt > 0:
                results['headings']['items'].append({
                    'level': h_tag.name.upper(),
                    'text': txt,
                    'matches': cnt
                })
                results['headings']['matches'] += cnt
                results['total_matches'] += cnt
                results['headings']['found'] = True

        # Body & DDC content widgets
        body = soup.find('body')
        if body:
            # Check specific DDC widgets first for precise reporting
            ddc_widgets = body.find_all(lambda t: t.has_attr('data-widget-name') or t.has_attr('data-widget-id'))
            analyzed_tags = set()
            
            for widget in ddc_widgets:
                w_name = widget.get('data-widget-name') or widget.get('data-name') or widget.get('class') or 'widget'
                if isinstance(w_name, list): w_name = " ".join(w_name)
                
                w_text = widget.get_text(separator=' ', strip=True)
                cnt = count_matches(w_text)
                if cnt > 0:
                    inner_p = [p.get_text(separator=' ', strip=True) for p in widget.find_all(['p', 'li']) if count_matches(p.get_text()) > 0]
                    if not inner_p:
                        inner_p = [w_text[:250] + ('...' if len(w_text) > 250 else '')]
                    
                    for snippet in inner_p:
                        results['seo_content']['items'].append({
                            'widget': w_name,
                            'snippet': snippet,
                            'matches': count_matches(snippet)
                        })
                    results['seo_content']['matches'] += cnt
                    results['total_matches'] += cnt
                    results['seo_content']['found'] = True
                    analyzed_tags.add(widget)

            # Catch remaining general paragraphs / lists not inside DDC widgets
            for el in body.find_all(['p', 'li']):
                if any(parent in analyzed_tags for parent in el.parents):
                    continue
                txt = el.get_text(separator=' ', strip=True)
                cnt = count_matches(txt)
                if cnt > 0:
                    results['seo_content']['items'].append({
                        'widget': 'General Text Element (<' + el.name + '>)',
                        'snippet': txt,
                        'matches': cnt
                    })
                    results['seo_content']['matches'] += cnt
                    results['total_matches'] += cnt
                    results['seo_content']['found'] = True

    # 5. Image Alt & Title Attributes (Optional)
    if include_images:
        for img in soup.find_all('img'):
            alt = img.get('alt', '').strip()
            title = img.get('title', '').strip()
            src = img.get('src') or img.get('data-src') or ''
            
            alt_cnt = count_matches(alt)
            title_cnt = count_matches(title)
            
            if alt_cnt > 0 or title_cnt > 0:
                results['images']['items'].append({
                    'src': src,
                    'alt': alt,
                    'title': title,
                    'alt_matches': alt_cnt,
                    'title_matches': title_cnt,
                    'total': alt_cnt + title_cnt
                })
                results['images']['matches'] += (alt_cnt + title_cnt)
                results['total_matches'] += (alt_cnt + title_cnt)
                results['images']['found'] = True

    # 6. Links & Anchor texts / CTAs (Optional)
    if include_links:
        for a in soup.find_all(['a', 'button']):
            href = a.get('href', '').strip() if a.name == 'a' else ''
            txt = a.get_text(separator=' ', strip=True)
            title = a.get('title', '').strip()
            
            txt_cnt = count_matches(txt)
            href_cnt = count_matches(href)
            title_cnt = count_matches(title)
            
            if txt_cnt > 0 or href_cnt > 0 or title_cnt > 0:
                results['links']['items'].append({
                    'tag': a.name,
                    'href': href,
                    'anchor_text': txt,
                    'title': title,
                    'matches': txt_cnt + href_cnt + title_cnt
                })
                results['links']['matches'] += (txt_cnt + href_cnt + title_cnt)
                results['total_matches'] += (txt_cnt + href_cnt + title_cnt)
                results['links']['found'] = True

    return results


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory('static', path)

@app.route('/api/audit', methods=['POST'])
def api_audit():
    data = request.json or {}
    url = data.get('url', '').strip()
    keyword = data.get('keyword', '').strip()
    case_sensitive = bool(data.get('case_sensitive', False))
    include_title = bool(data.get('include_title', True))
    include_metadata = bool(data.get('include_metadata', True))
    include_content = bool(data.get('include_content', True))
    include_images = bool(data.get('include_images', False))
    include_links = bool(data.get('include_links', False))

    if not url:
        return jsonify({'error': 'Please provide a valid Target URL'}), 400
    if not keyword:
        return jsonify({'error': 'Please provide a keyword to search for'}), 400

    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    t0 = time.time()
    try:
        html, status_code = fetch_html_robust(url, timeout=25)
    except Exception as e:
        return jsonify({
            'error': f"Failed to connect to '{url}': {str(e)}"
        }), 400

    elapsed = round((time.time() - t0), 2)
    audit_data = audit_page_keywords(
        html, 
        keyword, 
        case_sensitive=case_sensitive,
        include_title=include_title,
        include_metadata=include_metadata,
        include_content=include_content,
        include_images=include_images,
        include_links=include_links
    )
    audit_data['url'] = url
    audit_data['elapsed_sec'] = elapsed
    audit_data['status_code'] = status_code

    return jsonify({
        'success': True,
        'data': audit_data
    })


@app.route('/api/audit-batch', methods=['POST'])
def api_audit_batch():
    data = request.json or {}
    urls = data.get('urls', [])
    keyword = data.get('keyword', '').strip()
    case_sensitive = bool(data.get('case_sensitive', False))
    include_title = bool(data.get('include_title', True))
    include_metadata = bool(data.get('include_metadata', True))
    include_content = bool(data.get('include_content', True))
    include_images = bool(data.get('include_images', False))
    include_links = bool(data.get('include_links', False))

    if not urls:
        return jsonify({'error': 'Please provide at least one URL'}), 400
    if not keyword:
        return jsonify({'error': 'Please provide a keyword'}), 400

    clean_urls = []
    for u in urls:
        u = u.strip()
        if not u: continue
        if not u.startswith('http://') and not u.startswith('https://'):
            u = 'https://' + u
        clean_urls.append(u)

    batch_results = []
    for u in clean_urls[:20]: # Cap batch at 20 for responsiveness
        t0 = time.time()
        try:
            html, status_code = fetch_html_robust(u, timeout=20)
            res = audit_page_keywords(
                html, 
                keyword, 
                case_sensitive=case_sensitive,
                include_title=include_title,
                include_metadata=include_metadata,
                include_content=include_content,
                include_images=include_images,
                include_links=include_links
            )
            res['url'] = u
            res['status_code'] = status_code
            res['elapsed_sec'] = round((time.time() - t0), 2)
            batch_results.append({'url': u, 'status': 'success', 'data': res})
        except Exception as err:
            batch_results.append({'url': u, 'status': 'error', 'error': str(err)})

    return jsonify({
        'success': True,
        'keyword': keyword,
        'results': batch_results
    })


if __name__ == '__main__':
    print("=====================================================")
    print(" 🔎 DDC KEYWORD & METADATA AUDITOR IS RUNNING")
    print(" Open in browser: http://127.0.0.1:5050")
    print("=====================================================")
    app.run(host='0.0.0.0', port=5050, debug=True)
