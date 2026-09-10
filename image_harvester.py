import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from image_bank_db import save_harvested_image

# -----------------------------------------------------------------------------
# TAXONOMIES: MAKES & MODELS
# -----------------------------------------------------------------------------
AUTO_MAKES = {
    'ford': ['bronco', 'f-150', 'f150', 'explorer', 'mustang', 'edge', 'escape', 'expedition', 'super duty', 'maverick', 'ranger', 'transit'],
    'jeep': ['grand cherokee', 'cherokee', 'wrangler', 'compass', 'renegade', 'gladiator', 'wagoneer', 'grand wagoneer'],
    'ram': ['1500', '2500', '3500', 'promaster'],
    'dodge': ['durango', 'charger', 'challenger', 'hornet'],
    'chrysler': ['pacifica', '300', 'voyager'],
    'chevrolet': ['silverado', 'tahoe', 'suburban', 'colorado', 'equinox', 'blazer', 'corvette', 'camaro', 'traverse', 'trailblazer', 'malibu', 'trax'],
    'gmc': ['sierra', 'yukon', 'acadia', 'terrain', 'canyon', 'hummer'],
    'toyota': ['tacoma', 'tundra', '4runner', 'highlander', 'rav4', 'camry', 'corolla', 'sequoia', 'grand highlander', 'prius'],
    'nissan': ['rogue', 'altima', 'frontier', 'pathfinder', 'titan', 'sentra', 'murano', 'kicks', 'armada'],
    'honda': ['cr-v', 'crv', 'civic', 'accord', 'pilot', 'passport', 'ridgeline', 'hr-v', 'hrv'],
    'hyundai': ['tucson', 'santa fe', 'palisade', 'elantra', 'sonata', 'kona'],
    'kia': ['telluride', 'sportage', 'sorento', 'forte', 'k5', 'carnival', 'seltos'],
    'subaru': ['outback', 'forester', 'crosstrek', 'ascent', 'impreza', 'legacy', 'wrx'],
    'buick': ['enclave', 'encore', 'envision', 'envista'],
    'cadillac': ['escalade', 'ct4', 'ct5', 'xt4', 'xt5', 'xt6', 'lyriq'],
    'lincoln': ['navigator', 'aviator', 'corsair', 'nautilus'],
}

# -----------------------------------------------------------------------------
# CATEGORY KEYWORD DICTIONARIES
# -----------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    'performance': ['engine', 'horsepower', 'hp', 'towing', 'torque', 'transmission', 'mpg', '4x4', 'awd', 'ecoboost', 'v6', 'v8', 'suspension', 'off-road', 'handling', 'payload', 'turbo', 'drivetrain', 'capability', 'towing capacity'],
    'exterior': ['wheel', 'grille', 'body', 'led', 'headlight', 'paint', 'roof', 'bumper', 'styling', 'exterior', 'design', 'tires', 'door', 'tailgate', 'fascia', 'color', 'trim line'],
    'interior': ['cabin', 'seat', 'leather', 'cargo', 'legroom', 'dashboard', 'interior', 'seating', 'steering', 'upholstery', 'console', 'panoramic', 'space', 'headroom', 'comfort'],
    'safety': ['airbag', 'blind spot', 'braking', 'lane assist', 'collision', 'adaptive cruise', 'safety', 'camera', 'sensor', 'emergency', 'monitoring', 'guard', 'warning', 'driver assist', 'shield'],
    'technology': ['touchscreen', 'uconnect', 'sync', 'infotainment', 'apple carplay', 'android auto', 'audio', 'bluetooth', 'wireless', 'navigation', 'display', 'speaker', 'wifi', 'charging', 'screen', 'sound system'],
    'trims': ['trim', 'package', 'big bend', 'outer banks', 'badlands', 'wildtrak', 'rubicon', 'sahara', 'laramie', 'bighorn', 'xlt', 'lariat', 'platinum', 'limited', 'overland', 'elevation', 'denali', 'trailhawk', 'edition']
}

EXCLUDE_PATTERNS = [
    r'\.svg$', r'logo', r'icon', r'badge', r'avatar', r'pixel', r'tracking', r'button',
    r'spinner', r'loader', r'star', r'rating', r'facebook', r'twitter', r'instagram',
    r'youtube', r'linkedin', r'pinterest', r'carfax', r'autocheck', r'dealer-logo',
    r'nav-', r'menu-', r'footer-', r'header-', r'spacer', r'blank\.gif',
    r'-ot[\.\-_]', r'-ot$', r'order[-_]?type', r'alert', r'announcement', r'ribbon',
    r'disclaimer', r'weather', r'covid', r'holiday', r'financing-banner'
]

EXCLUDE_CONTAINER_KEYWORDS = [
    'alert', 'banner', 'announcement', 'order-type', 'ws-alert',
    'header', 'nav', 'footer', 'social-icons', 'results-list',
    'inventory-item', 'vehicle-card', 'specials-card', 'disclaimer'
]

TARGET_CONTAINER_KEYWORDS = [
    'accordion', 'tabbed', 'content-centered', 'content-default',
    'content-background', 'content-with-image', 'content-w-image',
    'media-object', 'content-grid', 'page-section', 'ws-accordion',
    'ws-tabbed-content', 'ws-content-centered'
]

def infer_make_model_condition(url, page_title, h1_text):
    """Detects vehicle Make, Model, and Condition (New/Used) from URL, Title, and H1."""
    text_corpus = f"{url} {page_title} {h1_text}".lower()
    
    # 1. Condition
    condition = 'general'
    if any(k in text_corpus for k in ['/used-', 'used ', 'pre-owned', 'certified used', 'preowned']):
        condition = 'used'
    elif any(k in text_corpus for k in ['/new-', 'new ', 'brand new']):
        condition = 'new'

    # 2. Make & Model
    found_make = 'unknown'
    found_model = 'unknown'
    
    for make, models in AUTO_MAKES.items():
        if make in text_corpus:
            found_make = make.title()
            for m in models:
                if m in text_corpus:
                    found_model = m.title()
                    break
            break
            
    # Fallback model search if make not explicitly found
    if found_make == 'unknown':
        for make, models in AUTO_MAKES.items():
            for m in models:
                if f" {m} " in text_corpus or f"/{m}-" in text_corpus or f"-{m}." in text_corpus:
                    found_make = make.title()
                    found_model = m.title()
                    break
            if found_make != 'unknown':
                break

    return found_make, found_model, condition

def refine_asset_make_model(image_url, page_make, page_model):
    """Refines vehicle Make and Model by inspecting the image URL and filename."""
    found_make = page_make
    found_model = page_model
    src_clean = image_url.lower()

    if found_make != 'unknown' and found_make.lower() in AUTO_MAKES:
        if found_model == 'unknown':
            for m in AUTO_MAKES[found_make.lower()]:
                if f"/{m}/" in src_clean or f"-{m}-" in src_clean or f"_{m}_" in src_clean or f"/{m}." in src_clean or f"-{m}." in src_clean or f"/{m}-" in src_clean:
                    found_model = m.title()
                    break
    elif found_make == 'unknown':
        for mk, models in AUTO_MAKES.items():
            for m in models:
                if f"/{m}/" in src_clean or f"-{m}-" in src_clean or f"_{m}_" in src_clean or f"/{m}." in src_clean:
                    found_make = mk.title()
                    found_model = m.title()
                    break
            if found_make != 'unknown':
                break

    return found_make, found_model

def classify_category(surrounding_text, alt_text, section_title):
    """Scores surrounding text against category keyword dictionaries to determine asset category."""
    combined = f"{section_title} {alt_text} {surrounding_text}".lower()
    
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                # Give higher weight if keyword is in heading or alt text
                weight = 3 if (kw in section_title.lower() or kw in alt_text.lower()) else 1
                scores[cat] += weight

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] > 0:
        return best_cat
    return 'general'

def is_excluded_image(src, tag=None):
    """Filters out icons, tracking pixels, logos, header/footer images, alert banners, and ribbons."""
    if not src or src.startswith('data:'):
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
        category = classify_category(surrounding_text, alt_text, section_title)
        asset_make, asset_model = refine_asset_make_model(full_src, make, model)
        
        asset_id = save_harvested_image(
            image_url=full_src,
            make=asset_make,
            model=asset_model,
            condition=condition,
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
                'make': asset_make,
                'model': asset_model,
                'condition': condition,
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
            category = classify_category(surrounding_text, alt_text, section_title)
            asset_make, asset_model = refine_asset_make_model(full_src, make, model)
            
            asset_id = save_harvested_image(
                image_url=full_src,
                make=asset_make,
                model=asset_model,
                condition=condition,
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
                    'make': asset_make,
                    'model': asset_model,
                    'condition': condition,
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
