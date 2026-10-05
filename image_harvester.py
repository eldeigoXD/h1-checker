import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from image_bank_db import save_harvested_image
from reclassify_image_bank import classify_metadata, AUTO_TAXONOMY, CATEGORY_RULES, YEAR_REGEX, is_junk_asset

# Expose backward-compatible variables
AUTO_MAKES = {k.lower(): [m[0].lower() for m in v['models']] for k, v in AUTO_TAXONOMY.items()}
CATEGORY_KEYWORDS = CATEGORY_RULES

def is_excluded_image(src, tag=None):
    """Filters out icons, tracking pixels, logos, header/footer images, alert banners, and ribbons."""
    if not src or src.startswith('data:'):
        return True
    
    if is_junk_asset(src):
        return True
    
    src_low = src.lower()
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, src_low):
            return True
            
    if tag:
        # Check explicit dimensions if present (e.g. 2000x80 alert ribbons)
        try:
            w_str = tag.get('width')
            h_str = tag.get('height')
            if w_str and h_str:
                w = float(re.sub(r'[^\d.]', '', str(w_str)))
                h = float(re.sub(r'[^\d.]', '', str(h_str)))
                if h > 0 and (w / h > 3.8 or (w >= 500 and h <= 120)):
                    return True
        except Exception:
            pass

        # Check parent container tags
        p = tag
        depth = 0
        while p and depth < 7:
            tag_name = p.name.lower() if p.name else ''
            classes = ' '.join(p.get('class', [])).lower()
            widget_name = (p.get('data-widget-name', '') or p.get('data-name', '')).lower()
            
            # Skip nav, header, footer, alert ribbons, inventory cards
            if tag_name in ['nav', 'header', 'footer']:
                return True
            if any(k in classes or k in widget_name for k in EXCLUDE_CONTAINER_KEYWORDS):
                return True
                
            p = p.parent
            depth += 1
            
    return False

def extract_surrounding_context(tag):
    """Extracts section title, alt text, and nearby paragraph text around an image tag."""
    alt_text = tag.get('alt', '') or tag.get('title', '')
    
    section_title = ''
    surrounding_text = ''
    
    # Check parent container up to 6 levels
    parent = tag.parent
    depth = 0
    while parent and depth < 6:
        # Find nearest heading
        headings = parent.find_all(['h1', 'h2', 'h3', 'h4', 'h5'], limit=3)
        if headings and not section_title:
            section_title = ' | '.join(h.get_text(strip=True) for h in headings if h.get_text(strip=True))
            
        # Get paragraph or text content
        p_texts = [p.get_text(strip=True) for p in parent.find_all('p', limit=3) if len(p.get_text(strip=True)) > 15]
        if p_texts and not surrounding_text:
            surrounding_text = ' '.join(p_texts[:2])
            
        if section_title and surrounding_text:
            break
        parent = parent.parent
        depth += 1
        
    return alt_text.strip(), section_title.strip(), surrounding_text.strip()

def check_target_container(tag):
    """Checks if the tag is inside an accordion, tabbed-content, content-centered, or content-background widget."""
    p = tag
    depth = 0
    while p and depth < 7:
        classes = ' '.join(p.get('class', [])).lower()
        widget = (p.get('data-widget-name', '') or p.get('data-name', '')).lower()
        if any(tgt in classes or tgt in widget for tgt in TARGET_CONTAINER_KEYWORDS):
            return True
        p = p.parent
        depth += 1
    return False

def harvest_page_images(url, soup, page_title="", h1_text="", html_raw="", case_id=""):
    """
    Extracts all main content images from a page, infers Make/Model/Condition and Category,
    and indexes them into the local Image Bank database.
    Focuses on vehicle imagery used alongside text in LP sections: accordion, tabbed-content,
    content-centered, content-background, etc. Filters out alert banners and ribbons.
    """
    if not soup:
        return {'status': 'skipped', 'harvested_count': 0, 'harvested_assets': [], 'harvested_items': []}

    make, model, condition = infer_make_model_condition(url, page_title, h1_text)
    
    # Extract dealer account ID if present
    dealer_id = ""
    dealer_match = re.search(r'pictures\.dealer\.com/[a-z]/([^/"\'&\s>]+)/', html_raw)
    if dealer_match:
        dealer_id = dealer_match.group(1)

    harvested = []
    seen_urls = set()

    # Process <img> tags
    img_tags = soup.find_all('img')
    for img in img_tags:
        candidates = [
            img.get('data-src'),
            img.get('data-lazy-src'),
            img.get('data-original'),
            img.get('data-highres'),
            img.get('data-lazy'),
            img.get('src')
        ]
        src = None
        for c in candidates:
            if c and not str(c).strip().startswith('data:'):
                src = str(c).strip()
                break

        if not src:
            continue
            
        full_src = urljoin(url, src)
        if full_src in seen_urls or is_excluded_image(full_src, img):
            continue

        alt_text, section_title, surrounding_text = extract_surrounding_context(img)
        in_target_container = check_target_container(img)
        has_meaningful_text = len(surrounding_text) >= 25 or len(section_title) >= 10

        # Only harvest images that are accompanied by LP text or belong to content widgets
        if not (in_target_container or has_meaningful_text):
            continue

        seen_urls.add(full_src)
        asset_year, asset_make, asset_model, asset_condition, category = classify_metadata(
            image_url=full_src,
            surrounding_text=surrounding_text,
            alt_text=alt_text,
            section_title=section_title,
            page_url=url,
            page_title=page_title,
            h1_text=h1_text,
            dealer_id=dealer_id
        )
        
        asset_id = save_harvested_image(
            image_url=full_src,
            year=asset_year,
            make=asset_make,
            model=asset_model,
            condition=asset_condition,
            category=category,
            surrounding_text=surrounding_text,
            alt_text=alt_text,
            section_title=section_title,
            dealer_id=dealer_id,
            page_url=url,
            case_id=case_id
        )
        if asset_id:
            asset_obj = {
                'id': asset_id,
                'image_url': full_src,
                'url': full_src,
                'year': asset_year,
                'make': asset_make,
                'model': asset_model,
                'condition': asset_condition,
                'category': category,
                'alt_text': alt_text,
                'section_title': section_title,
                'surrounding_text': surrounding_text
            }
            harvested.append(asset_obj)

    # Process CSS background-image containers
    bg_elements = soup.find_all(style=re.compile(r'background-image', re.I))
    for el in bg_elements:
        style = el.get('style', '')
        urls_found = re.findall(r'url\(["\']?(https?://[^"\')\s]+|//[^"\')\s]+|/[^"\')\s]+)["\']?\)', style)
        for bg_url in urls_found:
            if bg_url.startswith('data:'):
                continue
            full_src = urljoin(url, bg_url.strip())
            if full_src in seen_urls or is_excluded_image(full_src, el):
                continue

            alt_text, section_title, surrounding_text = extract_surrounding_context(el)
            in_target_container = check_target_container(el)
            has_meaningful_text = len(surrounding_text) >= 25 or len(section_title) >= 10

            if not (in_target_container or has_meaningful_text):
                continue
                
            seen_urls.add(full_src)
            asset_year, asset_make, asset_model, asset_condition, category = classify_metadata(
                image_url=full_src,
                surrounding_text=surrounding_text,
                alt_text=alt_text,
                section_title=section_title,
                page_url=url,
                page_title=page_title,
                h1_text=h1_text,
                dealer_id=dealer_id
            )
            
            asset_id = save_harvested_image(
                image_url=full_src,
                year=asset_year,
                make=asset_make,
                model=asset_model,
                condition=asset_condition,
                category=category,
                surrounding_text=surrounding_text,
                alt_text=alt_text,
                section_title=section_title,
                dealer_id=dealer_id,
                page_url=url,
                case_id=case_id
            )
            if asset_id:
                asset_obj = {
                    'id': asset_id,
                    'image_url': full_src,
                    'url': full_src,
                    'year': asset_year,
                    'make': asset_make,
                    'model': asset_model,
                    'condition': asset_condition,
                    'category': category,
                    'alt_text': alt_text,
                    'section_title': section_title,
                    'surrounding_text': surrounding_text
                }
                harvested.append(asset_obj)

    return {
        'status': 'success',
        'harvested_count': len(harvested),
        'make': make,
        'model': model,
        'condition': condition,
        'harvested_assets': harvested,
        'harvested_items': harvested
    }
