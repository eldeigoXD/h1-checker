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
    r'nav-', r'menu-', r'footer-', r'header-', r'spacer', r'blank\.gif'
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
    """Filters out icons, tracking pixels, logos, header/footer images, and inventory thumbnails."""
    if not src or src.startswith('data:'):
        return True
    
    src_low = src.lower()
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, src_low):
            return True
            
    if tag:
        # Check parent container tags
        p = tag
        depth = 0
        while p and depth < 6:
            tag_name = p.name.lower() if p.name else ''
            classes = ' '.join(p.get('class', [])).lower()
            widget_name = (p.get('data-widget-name', '') or p.get('data-name', '')).lower()
            
            # Skip nav, header, footer, inventory cards
            if tag_name in ['nav', 'header', 'footer']:
                return True
            if any(k in classes for k in ['navigation', 'header-logo', 'footer-logo', 'social-icons', 'vehicle-card', 'inventory-item', 'results-list', 'specials-card']):
                return True
            if any(k in widget_name for k in ['nav', 'header', 'footer', 'inventory-listing', 'specials']):
                return True
                
            p = p.parent
            depth += 1
            
    return False

def extract_surrounding_context(tag):
    """Extracts section title, alt text, and nearby paragraph text around an image tag."""
    alt_text = tag.get('alt', '') or tag.get('title', '')
    
    section_title = ''
    surrounding_text = ''
    
    # Check parent container up to 5 levels
    parent = tag.parent
    depth = 0
    while parent and depth < 5:
        # Find nearest heading
        headings = parent.find_all(['h1', 'h2', 'h3', 'h4', 'h5'], limit=3)
        if headings and not section_title:
            section_title = ' | '.join(h.get_text(strip=True) for h in headings if h.get_text(strip=True))
            
        # Get paragraph or text content
        p_texts = [p.get_text(strip=True) for p in parent.find_all('p', limit=3) if len(p.get_text(strip=True)) > 15]
        if p_texts:
            surrounding_text = ' '.join(p_texts[:2])
            
        if section_title and surrounding_text:
            break
        parent = parent.parent
        depth += 1
        
    return alt_text.strip(), section_title.strip(), surrounding_text.strip()

def harvest_page_images(url, soup, page_title="", h1_text="", html_raw="", case_id=""):
    """
    Extracts all main content images from a page, infers Make/Model/Condition and Category,
    and indexes them into the local Image Bank database.
    """
    if not soup:
        return {'status': 'skipped', 'harvested_count': 0}

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
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if not src:
            continue
            
        full_src = urljoin(url, src.strip())
        if full_src in seen_urls or is_excluded_image(full_src, img):
            continue
            
        seen_urls.add(full_src)
        alt_text, section_title, surrounding_text = extract_surrounding_context(img)
        category = classify_category(surrounding_text, alt_text, section_title)
        
        asset_id = save_harvested_image(
            image_url=full_src,
            make=make,
            model=model,
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
            harvested.append({
                'id': asset_id,
                'url': full_src,
                'make': make,
                'model': model,
                'condition': condition,
                'category': category
            })

    # Process CSS background-image containers
    bg_elements = soup.find_all(style=re.compile(r'background-image', re.I))
    for el in bg_elements:
        style = el.get('style', '')
        urls_found = re.findall(r'url\(["\']?(https?://[^"\')\s]+|//[^"\')\s]+|/[^"\')\s]+)["\']?\)', style)
        for bg_url in urls_found:
            full_src = urljoin(url, bg_url.strip())
            if full_src in seen_urls or is_excluded_image(full_src, el):
                continue
                
            seen_urls.add(full_src)
            alt_text, section_title, surrounding_text = extract_surrounding_context(el)
            category = classify_category(surrounding_text, alt_text, section_title)
            
            asset_id = save_harvested_image(
                image_url=full_src,
                make=make,
                model=model,
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
                harvested.append({
                    'id': asset_id,
                    'url': full_src,
                    'make': make,
                    'model': model,
                    'condition': condition,
                    'category': category
                })

    return {
        'status': 'success',
        'harvested_count': len(harvested),
        'make': make,
        'model': model,
        'condition': condition,
        'harvested_items': harvested
    }
