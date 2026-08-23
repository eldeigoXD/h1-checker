from flask import Flask, request, jsonify, send_from_directory, make_response

from flask_cors import CORS
try:
    from curl_cffi import requests
except Exception:
    import requests

from bs4 import BeautifulSoup
import os
import urllib3
import json
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from dotenv import load_dotenv
from coherence_engine import analyze_coherence, nlp_inventory_fallback
import inventory_learner
import semantic_qa
import instruction_engine
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import re

# Inventory Database helpers
INVENTORY_DB = 'inventory_patterns.json'

def load_inventory_patterns():
    if not os.path.exists(INVENTORY_DB):
        return {}
    try:
        with open(INVENTORY_DB, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_inventory_pattern(domain, page_path, filter_path):
    data = load_inventory_patterns()
    if domain not in data:
        data[domain] = {}
    
    # Only save if changed to avoid unnecessary writes
    if data[domain].get(page_path) != filter_path:
        data[domain][page_path] = filter_path
        try:
            with open(INVENTORY_DB, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving inventory pattern: {e}")

# CTA Database helpers
CTA_DB = 'cta_patterns.json'

def load_cta_patterns():
    if not os.path.exists(CTA_DB):
        return {'by_text': {}, 'by_url': {}}
    try:
        with open(CTA_DB, 'r') as f:
            data = json.load(f)
            if 'by_text' not in data: data = {'by_text': {}, 'by_url': {}}
            return data
    except:
        return {'by_text': {}, 'by_url': {}}

def save_cta_pattern(text, url):
    if not text or not url: return
    text_key = text.lower().strip()
    url_key = url.strip()
    data = load_cta_patterns()
    
    changed = False
    if data['by_text'].get(text_key) != url_key:
        data['by_text'][text_key] = url_key
        changed = True
    if data['by_url'].get(url_key) != text:
        data['by_url'][url_key] = text
        changed = True
        
    if changed:
        try:
            with open(CTA_DB, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving CTA pattern: {e}")

# Audit History helpers
HISTORY_DB = 'audit_history.json'

def load_audit_history():
    if not os.path.exists(HISTORY_DB):
        return []
    try:
        with open(HISTORY_DB, 'r') as f:
            return json.load(f)
    except:
        return []

def save_audit_history(case_id, title, path):
    if not case_id or not title or not path: return
    data = load_audit_history()
    
    # Avoid exact duplicates
    for entry in data:
        if entry.get('id') == case_id and entry.get('title') == title and entry.get('path') == path:
            return
            
    # Add new entry at the beginning
    import time
    data.insert(0, {
        'id': case_id,
        'title': title,
        'path': path,
        'timestamp': int(time.time())
    })
    
    # Optional: keep history size manageable (e.g., max 1000 items)
    data = data[:1000]
    
    try:
        with open(HISTORY_DB, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving audit history: {e}")


def parse_cta_instructions(instructions):
    """
    Parses 'Special Layout Instructions' into a list of required CTAs.
    Formats handled:
    - "New Intory (/new-inventory/index.htm)" -> text: "New Intory", url: "/new-inventory/index.htm"
    - "(View Inventory to #inventory)" -> text: "View Inventory", url: "#inventory"
    - "https://www.mikeandersondodge.net/new-inventory/index.htm" -> url: "..."
    - "/new-inventory/index.htm" -> url: "..."
    - "New Inventory" -> text: "New Inventory"
    """
    if not instructions: return []
    parsed = []
    
    # Split by newlines or commas
    initial_parts = [p.strip() for p in re.split(r'[\n,]', instructions) if p.strip()]
    
    parts = []
    for p in initial_parts:
        # Special case: If a line is just a list of URLs/paths separated by spaces
        # e.g. "/path1 /path2 http://link3"
        if ' ' in p and (p.startswith('/') or p.startswith('http')):
            sub_elements = p.split()
            # If every element looks like a URL/Path, split them
            if all(el.startswith('/') or el.startswith('http') or el.startswith('#') for el in sub_elements):
                parts.extend(sub_elements)
                continue
        parts.append(p)
    
    for part in parts:
        cta = {'text': None, 'url': None, 'original': part}
        
        # Format 1: Text (URL) -> e.g. "New Intory (/new-inventory/index.htm)"
        m1 = re.match(r'^(.*?) \((.*?)\)$', part)
        if m1:
            cta['text'] = m1.group(1).strip()
            cta['url'] = m1.group(2).strip()
            parsed.append(cta)
            continue
            
        # Format 2: (Text to URL) -> e.g. "(View Inventory to #inventory)"
        m2 = re.match(r'^\((.*?) to (.*?)\)$', part)
        if m2:
            cta['text'] = m2.group(1).strip()
            cta['url'] = m2.group(2).strip()
            parsed.append(cta)
            continue
            
        # Format 3: Just URL
        if part.startswith('/') or part.startswith('http://') or part.startswith('https://') or part.startswith('#'):
            cta['url'] = part
            parsed.append(cta)
            continue
            
        # Format 4: Text: URL -> e.g. "New Inventory: /new-inventory/index.htm"
        m3 = re.match(r'^(.*?):\s*(.*?)$', part)
        if m3:
            cta['text'] = m3.group(1).strip()
            cta['url'] = m3.group(2).strip()
            parsed.append(cta)
            continue
            
        # Format 6: Text - URL -> e.g. "Used Ford - /used-inventory/used-ford.htm"
        m4 = re.match(r'^(.*?)\s+-\s+(/.*?|https?://.*?|#.*?)$', part)
        if m4:
            cta['text'] = m4.group(1).strip()
            cta['url'] = m4.group(2).strip()
            parsed.append(cta)
            continue
            
        # Format 7: Text URL (space-separated without hyphen) -> e.g. "Pre-Owned Feature Vehicle /featured-vehicles/pre-owned.htm"
        m5 = re.match(r'^(.*?)\s+(/.*?|https?://.*?|#.*?)$', part)
        if m5:
            cta['text'] = m5.group(1).strip()
            cta['url'] = m5.group(2).strip()
            parsed.append(cta)
            continue

            
        # Format 5: Just Text
        # Ignore parts that look like descriptive instruction sentences rather than explicit CTA button labels
        p_low = part.lower().strip()
        # Words indicating this is a layout/content rule sentence, not a CTA label:
        rule_keywords = ['update', 'photos', 'add faq', 'faqs', 'include lead form', 'accordion', 'bottom of the page', 'ownership in', 'page content']
        if any(kw in p_low for kw in rule_keywords) and not ('http' in p_low or '/' in p_low or '#' in p_low):
            continue

        cta['text'] = part
        parsed.append(cta)
        
    return parsed


def get_selenium_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--log-level=3')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.page_load_strategy = 'none' 
    opts.add_argument('--ignore-certificate-errors')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver

# =====================================================================
# EXTENSIBLE BUG REGISTRY
# To add a new bug type: add one entry below, then call make_bug() where
# the detection logic lives. No other changes required.
# =====================================================================
BUG_REGISTRY = {
    'h1_missing':              {'platform': 'D',   'type': 'Critical',  'category': 'Content'},
    'h1_multiple':             {'platform': 'D',   'type': 'Failed',    'category': 'Content'},
    'h1_sr_mismatch':          {'platform': 'D',   'type': 'Failed',    'category': 'Content'},
    'title_not_found':         {'platform': 'D',   'type': 'Critical',  'category': 'Content'},
    'link_404':                {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'link_connection':         {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'anchor_broken':           {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'cta_coherence_red':       {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'cta_coherence_yellow':    {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'seo_coverage_low':        {'platform': 'D',   'type': 'Critical',  'category': 'Content'},
    'seo_coverage_low_mobile': {'platform': 'M',   'type': 'Critical',  'category': 'Content'},
    'img_no_title':            {'platform': 'D',   'type': 'Failed',    'category': 'Styling'},
    'img_no_w100':             {'platform': 'D',   'type': 'Failed',    'category': 'Styling'},
    'link_absolute':           {'platform': 'D',   'type': 'Failed',    'category': 'Link'},
    'inventory_mismatch':      {'platform': 'D',   'type': 'Failed',    'category': 'Config'},
    'inventory_manual_review': {'platform': 'D',   'type': 'Failed',    'category': 'Config'},
    'instructions_mismatch':   {'platform': 'D',   'type': 'Critical',  'category': 'Content'},
    'cta_missing':             {'platform': 'D/M', 'type': 'Failed',    'category': 'Config'},
    'cta_coherence_warn':      {'platform': 'D/M', 'type': 'Failed',    'category': 'Link'},
    'img_not_in_library':      {'platform': 'D/M', 'type': 'Failed',    'category': 'Styling'},
    'sitemap_xml_missing':     {'platform': 'D/M', 'type': 'Failed',    'category': 'Config'},
    'sitemap_html_missing':    {'platform': 'D/M', 'type': 'Failed',    'category': 'Config'},
    'lead_form_source_wrong':  {'platform': 'M/D', 'type': 'Failed',    'category': 'Form'},
}

def make_bug(bug_type: str, message: str, **extra) -> dict:
    """Create a standardized bug dict from the registry."""
    base = BUG_REGISTRY.get(bug_type, {'platform': 'M/D', 'type': 'Failed', 'category': 'General'}).copy()
    base['bug_type'] = bug_type
    base['message'] = message
    base.update(extra)  # allow caller to override platform/type/category or add selector info
    return base

app = Flask(__name__, static_folder='static')
CORS(app)

@app.route('/')
def serve_index():
    resp = make_response(send_from_directory(app.static_folder, 'index.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/<path:path>')
def serve_static(path):
    resp = make_response(send_from_directory(app.static_folder, path))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/api/history', methods=['GET'])
def get_audit_history():
    return jsonify(load_audit_history())

# =====================================================================
# LOCAL INVENTORY INFERENCE ENGINE (0 tokens, pure Python)
# Detects filter URL from URL slug + nav bar. No AI required.
# Extend MODELS / MAKES / BODY_STYLES dictionaries over time.
# =====================================================================

# Common automotive models (key = slug-friendly, value = DDC model param)
LOCAL_MODELS = {
    # Ford
    'mustang mach-e': 'Mustang%20Mach-E', 'mustang': 'Mustang', 
    'f-150': 'F-150', 'f150': 'F-150',
    'f-250sd': 'F-250SD', 'f-250 sd': 'F-250SD', 'f-250': 'F-250SD', 'f250sd': 'F-250SD', 'f250': 'F-250SD', 'super duty': 'F-250SD',
    'f-350sd': 'F-350SD', 'f-350 sd': 'F-350SD', 'f-350': 'F-350SD', 'f350sd': 'F-350SD', 'f350': 'F-350SD',
    'f-450sd': 'F-450SD', 'f-450 sd': 'F-450SD', 'f-450': 'F-450SD', 'f450sd': 'F-450SD', 'f450': 'F-450SD',
    'f-550sd': 'F-550SD', 'f-550': 'F-550SD', 'f550': 'F-550SD',
    'f-600sd': 'F-600SD', 'f-650sd': 'F-650SD', 'e-450sd': 'E-450SD',
    'bronco sport': 'Bronco%20Sport', 'bronco': 'Bronco',
    'expedition max': 'Expedition%20Max', 'expedition': 'Expedition', 
    'escape hybrid': 'Escape%20Hybrid', 'escape plug-in hybrid': 'Escape%20Plug-In%20Hybrid', 'escape': 'Escape', 
    'explorer': 'Explorer', 'edge': 'Edge', 'ranger': 'Ranger', 'maverick': 'Maverick', 
    'transit-150': 'Transit-150', 'transit-250': 'Transit-250', 'transit-350': 'Transit-350',
    'transit 150': 'Transit-150', 'transit 250': 'Transit-250', 'transit 350': 'Transit-350',
    'transit150': 'Transit-150', 'transit250': 'Transit-250', 'transit350': 'Transit-350',
    # Chevy / GMC
    'silverado 1500': 'Silverado%201500', 
    'silverado 2500 hd': 'Silverado%202500%20HD', 'silverado 2500': 'Silverado%202500%20HD',
    'silverado 3500 hd chassis cab': 'Silverado%203500%20HD%20Chassis%20Cab',
    'silverado 3500 hd': 'Silverado%203500%20HD', 'silverado 3500': 'Silverado%203500%20HD',
    'silverado 5500 hd': 'Silverado%205500%20HD', 'silverado ev': 'Silverado%20EV', 
    'silverado': 'Silverado',
    'tahoe special service vehicle': 'Tahoe%20Special%20Service%20Vehicle',
    'tahoe': 'Tahoe', 'suburban': 'Suburban',
    'equinox ev': 'Equinox%20EV', 'equinox': 'Equinox', 
    'blazer ev': 'Blazer%20EV', 'blazer': 'Blazer',
    'traverse': 'Traverse', 'trailblazer': 'Trailblazer', 'trax': 'Trax',
    'colorado': 'Colorado', 'corvette stingray': 'Corvette%20Stingray', 'corvette z06': 'Corvette%20Z06',
    'bolt': 'Bolt', 'malibu': 'Malibu',
    'express passenger': 'Express%20Passenger', 'express cargo': 'Express%20Cargo',
    'express cutaway 3500': 'Express%20Cutaway%203500', 'express cutaway 4500': 'Express%20Cutaway%204500',
    # GMC
    'sierra 1500': 'Sierra%201500', 
    'sierra 2500 hd': 'Sierra%202500%20HD', 'sierra 2500': 'Sierra%202500%20HD',
    'sierra 3500 hd chassis cab': 'Sierra%203500%20HD%20Chassis%20Cab',
    'sierra 3500 hd': 'Sierra%203500%20HD', 'sierra 3500': 'Sierra%203500%20HD',
    'sierra': 'Sierra', 
    'yukon xl': 'Yukon%20XL', 'yukon': 'Yukon',
    'acadia': 'Acadia', 'canyon': 'Canyon', 'terrain': 'Terrain',
    'hummer ev pickup': 'HUMMER%20EV%20Pickup', 'hummer ev suv': 'HUMMER%20EV%20SUV',
    'savana cargo': 'Savana%20Cargo',
    # Buick
    'enclave': 'Enclave', 'encore gx': 'Encore%20GX', 'envision': 'Envision', 'envista': 'Envista',
    # Jeep / Ram / Dodge
    'grand wagoneer': 'Grand%20Wagoneer',    'grand-wagoneer': 'Grand%20Wagoneer',
    'wagoneer': 'Wagoneer',
    # Cadillac
    'ct4-v': 'CT4-V', 'ct4': 'CT4', 'ct5-v': 'CT5-V', 'ct5': 'CT5',
    'escalade esv': 'Escalade%20ESV', 'escalade': 'Escalade',
    'lyriq': 'LYRIQ', 'optiq': 'OPTIQ', 'vistiq': 'VISTIQ',
    'xt4': 'XT4', 'xt5': 'XT5', 'xt6': 'XT6',
    'grand cherokee': 'Grand%20Cherokee', 'cherokee': 'Cherokee', 'wrangler': 'Wrangler', 'gladiator': 'Gladiator',
    'grand-cherokee': 'Grand%20Cherokee', 'compass': 'Compass', 'renegade': 'Renegade',
    'ram 1500 classic': '1500%20Classic', 'ram-1500-classic': '1500%20Classic',
    'ram 1500': '1500', 'ram-1500': '1500',
    'ram 2500': '2500', 'ram-2500': '2500',
    'ram 3500 chassis': '3500%20Chassis', 'ram-3500-chassis': '3500%20Chassis',
    'ram 3500': '3500', 'ram-3500': '3500',
    'ram 4500': '4500', 'ram 5500': '5500',
    'promaster city': 'ProMaster%20City', 'promaster': 'ProMaster',
    'charger': 'Charger', 'challenger': 'Challenger', 'durango': 'Durango',
    'pacifica': 'Pacifica', 'voyager': 'Voyager', '300': '300',
    # Toyota
    '4runner i-force max': '4Runner%20i-FORCE%20MAX', '4runner': '4Runner',
    'bz woodland': 'bZ%20Woodland', 'bz': 'bZ',
    'c-hr': 'C-HR', 'camry': 'Camry', 
    'corolla cross hybrid': 'Corolla%20Cross%20Hybrid', 'corolla cross': 'Corolla%20Cross',
    'corolla hatchback': 'Corolla%20Hatchback', 'corolla hybrid': 'Corolla%20Hybrid', 'corolla': 'Corolla',
    'crown signia': 'Crown%20Signia', 'gr supra': 'GR%20Supra', 'gr86': 'GR86',
    'grand highlander hybrid': 'Grand%20Highlander%20Hybrid', 'grand highlander': 'Grand%20Highlander',
    'highlander hybrid': 'Highlander%20Hybrid', 'highlander': 'Highlander',
    'land cruiser': 'Land%20Cruiser', 
    'prius plug-in hybrid': 'Prius%20Plug-in%20Hybrid', 'prius': 'Prius',
    'rav4 plug-in hybrid': 'RAV4%20Plug-in%20Hybrid', 'rav4 hybrid': 'RAV4%20Plug-in%20Hybrid', 'rav4': 'RAV4',
    'sequoia': 'Sequoia', 'sienna': 'Sienna', 
    'tacoma i-force max': 'Tacoma%20i-FORCE%20MAX', 'tacoma': 'Tacoma',
    'tundra i-force max': 'Tundra%20i-FORCE%20MAX', 'tundra': 'Tundra',
    'venza': 'Venza',
    # Honda
    'accord hybrid': 'Accord%20Hybrid', 'accord': 'Accord', 
    'civic hybrid': 'Civic%20Hybrid', 'civic si': 'Civic%20Si', 'civic': 'Civic', 
    'cr-v hybrid': 'CR-V%20Hybrid', 'cr-v': 'CR-V', 'crv hybrid': 'CR-V%20Hybrid', 'crv': 'CR-V',
    'hr-v': 'HR-V', 'hrv': 'HR-V', 'odyssey': 'Odyssey',
    'ridgeline': 'Ridgeline', 'passport': 'Passport', 'pilot': 'Pilot',
    'prologue': 'Prologue',
    # Hyundai
    'tucson plug-in hybrid': 'Tucson%20Plug-in%20Hybrid', 'tucson phev': 'Tucson%20Plug-in%20Hybrid',
    'tucson hybrid': 'Tucson%20Hybrid', 'tucson n': 'Tucson%20N',
    'tucson': 'Tucson',
    'santa fe plug-in hybrid': 'Santa%20Fe%20Plug-in%20Hybrid', 'santa fe phev': 'Santa%20Fe%20Plug-in%20Hybrid',
    'santa fe hybrid': 'Santa%20Fe%20Hybrid',
    'santa fe': 'Santa%20Fe',
    'elantra hybrid': 'Elantra%20Hybrid', 'elantra n': 'Elantra%20N', 'elantra': 'Elantra',
    'sonata hybrid': 'Sonata%20Hybrid', 'sonata': 'Sonata',
    'kona electric': 'Kona%20Electric', 'kona ev': 'Kona%20Electric', 'kona': 'Kona',
    'ioniq 9': 'IONIQ%209', 'ioniq 6': 'IONIQ%206', 'ioniq 5 n': 'IONIQ%205%20N',
    'ioniq 5': 'IONIQ%205', 'ioniq': 'IONIQ',
    'palisade': 'Palisade', 'nexo': 'NEXO',
    'venue': 'Venue', 'accent': 'Accent',
    # Kia
    'carnival hybrid': 'Carnival%20Hybrid', 'carnival': 'Carnival',
    'ev9': 'EV9', 'k4': 'K4', 'k5': 'K5',
    'niro ev': 'Niro%20EV', 'niro': 'Niro',
    'seltos': 'Seltos', 
    'sorento plug-in hybrid': 'Sorento%20Plug-In%20Hybrid', 'sorento phev': 'Sorento%20Plug-In%20Hybrid',
    'sorento hybrid': 'Sorento%20Hybrid', 'sorento': 'Sorento',
    'sportage plug-in hybrid': 'Sportage%20Plug-In%20Hybrid', 'sportage phev': 'Sportage%20Plug-In%20Hybrid',
    'sportage hybrid': 'Sportage%20Hybrid', 'sportage': 'Sportage',
    'telluride hybrid': 'Telluride%20Hybrid', 'telluride': 'Telluride',
    'ev6': 'EV6', 'forte': 'Forte', 'soul': 'Soul', 'stinger': 'Stinger',
    # Nissan
    'altima': 'Altima', 'rogue': 'Rogue', 'frontier': 'Frontier', 'pathfinder': 'Pathfinder',
    'sentra': 'Sentra', 'maxima': 'Maxima', 'armada': 'Armada', 'murano': 'Murano',
    # Subaru
    'outback': 'Outback', 'forester': 'Forester', 'impreza': 'Impreza',
    'crosstrek': 'Crosstrek', 'ascent': 'Ascent', 'legacy': 'Legacy', 'wrx': 'WRX',
    'brz': 'BRZ', 'solterra': 'Solterra', 'trailseeker': 'Trailseeker', 'uncharted': 'Uncharted',
    # Acura
    'adx': 'ADX', 'integra': 'Integra', 'mdx': 'MDX', 'rdx': 'RDX', 'tlx': 'TLX', 'zdx': 'ZDX',
    # Lincoln / Mercedes / BMW / Lexus / Cadillac
    'nautilus': 'Nautilus', 'corsair': 'Corsair', 'aviator': 'Aviator',
    'navigator': 'Navigator', 'mkc': 'MKC', 'mkx': 'MKX', 'mkz': 'MKZ',
    'escalade': 'Escalade', 'xt6': 'XT6', 'xt5': 'XT5', 'xt4': 'XT4', 'ct5': 'CT5', 'ct4': 'CT4',
    # Lexus
    'es 350e': 'ES%20350e', 'es': 'ES',
    'gx 550': 'GX%20550', 'gx': 'GX',
    'is 350': 'IS%20350', 'is': 'IS',
    'nx 450h plus': 'NX%20450h%20Plus', 'nx 350h': 'NX%20350h', 'nx 350': 'NX%20350', 'nx': 'NX',
    'rx 450h plus': 'RX%20450h%20Plus', 'rx 500h': 'RX%20500h', 'rx 350h': 'RX%20350h', 'rx 350': 'RX%20350', 'rx': 'RX',
    'rz 350e': 'RZ%20350e', 'rz': 'RZ',
    'tx 500h': 'TX%20500h', 'tx 350': 'TX%20350', 'tx': 'TX',
    'ux 300h': 'UX%20300h', 'ux': 'UX',
    # Luxury
    'spectre': 'Spectre', 'phantom': 'Phantom', 'ghost': 'Ghost', 'cullinan': 'Cullinan',
    # Mazda
    'cx-70 plug-in hybrid': 'CX-70%20Plug-In%20Hybrid', 'cx-70 phev': 'CX-70%20Plug-In%20Hybrid',
    'cx70 phev': 'CX-70%20Plug-In%20Hybrid', 'cx70 plug-in hybrid': 'CX-70%20Plug-In%20Hybrid',
    'cx-70 hybrid': 'CX-70%20Plug-In%20Hybrid',
    'cx-70': 'CX-70', 'cx70': 'CX-70',
    'cx-90 plug-in hybrid': 'CX-90%20Plug-In%20Hybrid', 'cx-90 phev': 'CX-90%20Plug-In%20Hybrid',
    'cx90 phev': 'CX-90%20Plug-In%20Hybrid', 'cx90 plug-in hybrid': 'CX-90%20Plug-In%20Hybrid',
    'cx-90 hybrid': 'CX-90%20Plug-In%20Hybrid',
    'cx-90': 'CX-90', 'cx90': 'CX-90',
    'cx-50 hybrid': 'CX-50%20Hybrid', 'cx50 hybrid': 'CX-50%20Hybrid', 
    'cx-50': 'CX-50', 'cx50': 'CX-50',
    'cx-5': 'CX-5', 'cx5': 'CX-5', 
    'cx-30': 'CX-30', 'cx30': 'CX-30',
    'mazda3 hatchback': 'Mazda3%20Hatchback', 'mazda3 hatch': 'Mazda3%20Hatchback',
    'mazda3 sedan': 'Mazda3%20Sedan', 'mazda3': 'Mazda3',
    'mx-5 miata rf': 'MX-5%20Miata%20RF', 'mx-5 miata': 'MX-5%20Miata', 'mx5 miata': 'MX-5%20Miata',
    'mx-5 miata': 'MX-5%20Miata', 'mx-5': 'MX-5%20Miata',
    'mazda6': 'Mazda6',
    # Genesis
    'g70': 'G70', 'g80': 'G80', 'g90': 'G90', 'gv60': 'GV60', 'gv70': 'GV70',
    'gv80': 'GV80', 'gv80 coupe': 'GV80%20Coupe',
    # Volkswagen
    'atlas cross sport': 'Atlas%20Cross%20Sport', 'atlas': 'Atlas',
    'golf gti': 'Golf%20GTI', 'golf r': 'Golf%20R', 'id. buzz': 'ID.%20Buzz',
    'id buzz': 'ID.%20Buzz', 'jetta': 'Jetta', 'taos': 'Taos', 'tiguan': 'Tiguan',
    # Volvo
    'ex30 cross country': 'EX30%20Cross%20Country', 'ex30': 'EX30',
    'ex40': 'EX40', 'ex90': 'EX90', 'v60 cross country': 'V60%20Cross%20Country',
    'xc60 plug-in hybrid': 'XC60%20plug-in%20hybrid', 'xc60': 'XC60',
    'xc90 plug-in hybrid': 'XC90%20plug-in%20hybrid', 'xc90': 'XC90',
    'xc40': 'XC40',
    # Audi
    'q3': 'Q3', 'q5': 'Q5', 'q5 sportback': 'Q5%20Sportback', 'q7': 'Q7', 'q8 e-tron': 'Q8%20e-tron', 'q8': 'Q8',
    'sq5 sportback': 'SQ5%20Sportback', 'sq5': 'SQ5', 'sq7': 'SQ7', 'sq8': 'SQ8',
    'rs q8': 'RS%20Q8', 'rs': 'RS', 's e-tron gt': 'S%20e-tron%20GT',
    'a3': 'A3', 'a5': 'A5', 'a6': 'A6', 'a8': 'A8',
    's3': 'S3', 's8': 'S8',
    # Mercedes-Benz
    'amg e 53 e': 'AMG%20E%2053%20E', 'amg e 53': 'AMG%20E%2053%20E',
    'amg cle 53': 'AMG%20CLE%2053', 'amg c 43': 'AMG%20C%2043', 'amg g 63': 'AMG%20G%2063',
    'amg gla 35': 'AMG%20GLA%2035', 'amg glb 35': 'AMG%20GLB%2035', 'amg glc 43': 'AMG%20GLC%2043',
    'amg gle 53': 'AMG%20GLE%2053', 'amg gle 63': 'AMG%20GLE%2063', 'amg gls 63': 'AMG%20GLS%2063',
    'amg gt 43 4-door': 'AMG%20GT%2043%204-Door', 'amg gt 53 4-door': 'AMG%20GT%2053%204-Door',
    'amg gt 63 4-door': 'AMG%20GT%2063%204-Door', 'amg gt 43': 'AMG%20GT%2043', 'amg gt 55': 'AMG%20GT%2055',
    'amg sl 43': 'AMG%20SL%2043', 'cla 250+ sedan': 'CLA%20250+%20Sedan', 'cla 250': 'CLA%20250',
    'cla 350 sedan': 'CLA%20350%20Sedan', 'cle 300': 'CLE%20300', 'cle 450': 'CLE%20450',
    'eqe 320+': 'EQE%20320+', 'eqs 400 suv': 'EQS%20400%20SUV', 'eqs 450+ sedan': 'EQS%20450+%20Sedan',
    'eqs 450 sedan': 'EQS%20450%20Sedan', 'eqs 550': 'EQS%20550', 'eqs 580': 'EQS%20580',
    'gla 250': 'GLA%20250', 'glb 250': 'GLB%20250', 'glc 300': 'GLC%20300', 'glc 350e': 'GLC%20350e',
    'gle 350': 'GLE%20350', 'gle 450': 'GLE%20450', 'gle 580': 'GLE%20580', 'gls 450': 'GLS%20450',
    'gls 580': 'GLS%20580', 'maybach gls 600': 'Maybach%20GLS%20600', 'maybach s 580': 'Maybach%20S%20580',
    'c-class': 'C-Class', 'e-class': 'E-Class', 'g-class': 'G-Class', 's-class': 'S-Class',
    'giulia': 'Giulia', 'stelvio': 'Stelvio', 'tonale': 'Tonale',
    # Mitsubishi
    'eclipse cross': 'Eclipse%20Cross', 'outlander sport': 'Outlander%20Sport', 'outlander': 'Outlander',
}

LOCAL_MERCEDES_CLASSES = {
    'amg': 'AMG', 'c class': 'C-Class', 'cla': 'CLA', 'cle': 'CLE', 'e class': 'E-Class',
    'eqe': 'EQE', 'eqs': 'EQS', 'g class': 'G-Class', 'gla': 'GLA', 'glb': 'GLB',
    'glc': 'GLC', 'gle': 'GLE', 'gls': 'GLS', 'maybach gls 600': 'Maybach%20GLS%20600',
    'maybach s 580': 'Maybach%20S%20580', 's class': 'S-Class'
}

LOCAL_MAKES = {
    'chevrolet': 'Chevrolet', 'chevy': 'Chevrolet',
    'ford': 'Ford', 'lincoln': 'Lincoln',
    'jeep': 'Jeep', 'dodge': 'Dodge', 'ram': 'Ram', 'chrysler': 'Chrysler',
    'toyota': 'Toyota', 'lexus': 'Lexus',
    'honda': 'Honda', 'acura': 'Acura',
    'hyundai': 'Hyundai', 'genesis': 'Genesis',
    'kia': 'Kia',
    'nissan': 'Nissan', 'infiniti': 'Infiniti',
    'subaru': 'Subaru',
    'mazda': 'Mazda',
    'gmc': 'GMC', 'buick': 'Buick', 'cadillac': 'Cadillac',
    'volkswagen': 'Volkswagen', 'vw': 'Volkswagen', 'audi': 'Audi',
    'bmw': 'BMW', 'mini': 'MINI', 'mercedes': 'Mercedes-Benz',
    'rollsroyce': 'Rolls-Royce', 'rolls-royce': 'Rolls-Royce',
    'volvo': 'Volvo', 'jaguar': 'Jaguar', 'landrover': 'Land%20Rover',
    'mitsubishi': 'Mitsubishi',
    'alfa romeo': 'Alfa%20Romeo', 'alfa': 'Alfa%20Romeo',
}

LOCAL_BODY_STYLES = {
    'truck': 'Truck', 'trucks': 'Truck', 'pickup': 'Truck',
    'suv': 'SUV', 'suvs': 'SUV', 'crossover': 'SUV',
    'sedan': 'Sedan', 'sedans': 'Sedan',
    'coupe': 'Coupe', 'coupes': 'Coupe',
    'van': 'Van', 'minivan': 'Minivan', 'vans': 'Van',
    'cargo van': 'Cargo%20Van', 'cargo-van': 'Cargo%20Van',
    'passenger van': 'Passenger%20Van', 'passenger-van': 'Passenger%20Van',
    'convertible': 'Convertible',
    'hatchback': 'Hatchback',
    'wagon': 'Wagon',
}

LOCAL_TRIMS = {
    'black label': 'Black%20Label',
    'premiere': 'Premiere',
    'reserve': 'Reserve',
    'luxury': 'Luxury',
    'platinum sport': 'Platinum%20Sport',
    'platinum': 'Platinum',
    'premium luxury': 'Premium%20Luxury',
    'sport': 'Sport',
    'v-series premium': 'V-Series%20Premium',
    'v-series': 'V-Series',
}

LOCAL_FUEL_TYPES = {
    'electric': 'Electric', 'ev': 'Electric',
    'hybrid': 'Hybrid', 'phev': 'Hybrid',
    'diesel': 'Diesel',
}

# Page type detection keywords
_NEW_KWS  = ['/new-', '/new/', '/shop/new', '/new-inventory', '/new-models', '/new-cars', '/new-vehicles', '/nuevos-']
_USED_KWS = ['/used-', '/used/', '/pre-owned', '/preowned', '/used-inventory', '/usados-', '/bargain-', '/low-mileage', '/mileage-selection', '/low-miles']
_CERT_KWS = ['/certified', '/cpo']
_ALL_KWS  = ['/all-', '/inventory/all', '/total-inventory']
_GEN_KWS  = ['/dealership/', '/serving-', '/about-', '/directions', '/compare/', '/research/', '/about/', '/areas-we-serve']

def local_inventory_inference(url: str, page_html: str, instructions: str = "") -> str | None:
    """
    Determines the inventory filter URL using ONLY local Python matching.
    Returns a relative path+query string, a SUM: command, or None if unable to determine.
    """
    from urllib.parse import urlparse, urljoin, urlunparse

    parsed = urlparse(url)
    path = parsed.path.lower()
    domain = parsed.netloc
    domain_low = domain.lower()
    
    # Remove file extension from path before creating slug
    path_no_ext = path.replace('.htm', '').replace('.html', '')
    # slug_spaces: hyphens → spaces (for matching most models like "bronco sport", "grand cherokee")
    slug_spaces = path_no_ext.replace('-', ' ').replace('_', ' ').replace('/', ' ')
    # slug_hyphens: preserve hyphens (for models like "f-150", "cr-v", "c-hr")
    # Slashes and underscores become spaces; hyphens are kept
    slug_hyphens = path_no_ext.replace('_', ' ').replace('/', ' ')
    slug = slug_spaces  # backward compat alias

    soup_nav = BeautifulSoup(page_html, 'html.parser') if page_html else None


    # --- Detect Platform: Dealer Inspire (DI) vs DDC -------------------------
    # DI uses bodyStyle= instead of normalBodyStyle=, and different nav URL patterns.
    
    # Known DDC domains that have nav URLs resembling DI patterns (city names, etc.)
    # Force these to DDC regardless of nav heuristics.
    FORCE_DDC_DOMAINS = [
        'bakerchevroletofcadillac.com',
        'bakercdjrofcadillac.com',
    ]
    is_forced_ddc = any(d in domain_low for d in FORCE_DDC_DOMAINS) or 'dealer.com' in domain_low
    if not is_forced_ddc and page_html:
        page_html_low = page_html.lower()
        if any(marker in page_html_low for marker in ['dealer.com', 'static.dealer.com', 'pictures.dealer.com', 'coxautoinc', 'ddc-', 'normalbodystyle=']):
            is_forced_ddc = True

    is_dealer_inspire = False
    if is_forced_ddc:
        is_dealer_inspire = False
        print(f"DEBUG: Platform forced to DDC for domain '{domain_low}'")
    elif page_html:
        page_html_low = page_html.lower()
        if 'dealerinspire' in page_html_low or 'dealer inspire' in page_html_low or 'di-search' in page_html_low:
            is_dealer_inspire = True


    if not is_forced_ddc and not is_dealer_inspire and soup_nav:
        # DI signature: <meta name="generator" content="Dealer Inspire">
        # Or presence of DI-specific JS/CSS markers
        gen_meta = soup_nav.find('meta', attrs={'name': 'generator'})
        if gen_meta and 'dealer inspire' in (gen_meta.get('content') or '').lower():
            is_dealer_inspire = True
        if not is_dealer_inspire:
            # Check for DI-specific HTML markers
            if (soup_nav.find(attrs={'data-di-': True}) or
                soup_nav.find(class_=lambda c: c and 'di-' in c.lower()) or
                soup_nav.find('script', src=lambda s: s and 'dealerinspire' in s.lower())):
                is_dealer_inspire = True
        if not is_dealer_inspire:
            # Check for DI-style URL patterns in nav: /new-[make]/[city].htm
            for a in soup_nav.select('nav a, header a, a[href*="/new-"], a[href*="/used-"]'):
                h = (a.get('href') or '').lower().split('?')[0]
                import re as _re_di
                if _re_di.search(r'/(new|used|certified)-(?!inventory|cars|vehicles)[a-z0-9\-]+/[a-z0-9\-]+', h):
                    is_dealer_inspire = True
                    break
    print(f"DEBUG: Platform detection - is_dealer_inspire={is_dealer_inspire}")

    # --- 1. Find real inventory paths from nav ---
    new_inv_path  = None
    used_inv_path = None
    cert_inv_path = None
    all_inv_path  = None

    if soup_nav:
        # Include semantic tags and common DDC/Dealer Inspire navigation classes
        nav_selector = 'nav a, header a, .navbar-nav a, .ws-navigation a, [data-widget-name*="navigation"] a'
        nav_paths = {'new': [], 'used': [], 'cert': [], 'all': []}
        
        for a in soup_nav.select(nav_selector):
            href = a.get('href', '') or ''
            if not href or href.startswith(('javascript', 'tel', 'mailto', '#')):
                continue
            h = href.lower().split('?')[0]
            raw = urlparse(urljoin(url, href)).path
            if not raw or raw == '/': continue
                
            # Skip obvious sub-filters or body style sub-pages in nav
            import re as _re_di
            if any(bad in h for bad in ['bargain', 'under', 'carfax', 'wholesale', 'special', '/ev.htm', '/hybrid.htm', '/sedan.htm', '/suv.htm', '/truck.htm', '/coupe.htm', '/van.htm', '/minivan.htm', '/convertible.htm', '/hatchback.htm', '/wagon.htm']): continue
            if _re_di.search(r'/(new|used|certified)-inventory/(?!index\b)[a-z0-9\-]+\.htm', h): continue  # e.g. /new-inventory/sedan.htm is a sub-filter page, not main inv path
            
            # Categorize
            if any(k in h for k in ['new-inventory', '/inventory/new', '/new-cars', '/new-vehicles']):
                nav_paths['new'].append(raw)
            elif not is_forced_ddc and _re_di.search(r'/new-(?!inventory|cars|vehicles)[a-z0-9\-]+/[a-z0-9\-]+', h) and 'research' not in h:
                # DI-style new inventory path: /new-nissan/south-burlington.htm
                # Exclude model-research/research paths
                nav_paths['new'].append(raw)
                is_dealer_inspire = True
            elif any(k in h for k in ['used-inventory', '/inventory/used', '/used-cars']) or (
                '/pre-owned' in h and '/featured-vehicles/' not in h
            ):
                nav_paths['used'].append(raw)
            elif not is_forced_ddc and _re_di.search(r'/used-(?!inventory|cars|vehicles)[a-z0-9\-]+/[a-z0-9\-]+', h):
                nav_paths['used'].append(raw)
                is_dealer_inspire = True
            elif any(k in h for k in ['certified-inventory', '/cpo', '/certified']):
                nav_paths['cert'].append(raw)
            elif not is_forced_ddc and _re_di.search(r'/certified-(?!inventory|cars|vehicles)[a-z0-9\-]+/[a-z0-9\-]+', h):
                nav_paths['cert'].append(raw)
                is_dealer_inspire = True
            elif any(k in h for k in ['all-inventory', '/inventory/all']):
                nav_paths['all'].append(raw)

        # Pick the best path for each (shortest path usually wins or index.htm)
        def _pick_best(path_list):
            import re
            if not path_list: return None
            # If Dealer Inspire is detected, prioritize DI-style paths like /new-[make]/[city].htm
            if is_dealer_inspire:
                di_paths = [p for p in path_list if re.search(r'/(new|used|certified)-(?!inventory|cars|vehicles)[a-z0-9\-]+/[a-z0-9\-]+', p.lower())]
                if di_paths:
                    return min(di_paths, key=len)
            # Strongly prefer canonical inventory paths (/new-inventory/, /used-inventory/, etc.)
            canonical = [p for p in path_list if re.search(r'/(new|used|certified|all)-inventory/', p.lower())]
            if canonical:
                # Among canonical, prefer index.htm
                indices = [p for p in canonical if 'index.htm' in p.lower()]
                if indices: return min(indices, key=len)
                return min(canonical, key=len)
            # Fallback: prefer index.htm, otherwise shortest path
            indices = [p for p in path_list if 'index.htm' in p.lower()]
            if indices: return min(indices, key=len)
            return min(path_list, key=len)

        new_inv_path  = _pick_best(nav_paths['new'])
        used_inv_path = _pick_best(nav_paths['used'])
        cert_inv_path = _pick_best(nav_paths['cert'])
        all_inv_path  = _pick_best(nav_paths['all'])

    # Fallbacks if nav parsing fails
    new_inv_path  = new_inv_path or '/new-inventory/index.htm'
    used_inv_path = used_inv_path or '/used-inventory/index.htm'
    cert_inv_path = cert_inv_path or '/certified-inventory/index.htm'
    all_inv_path  = all_inv_path or '/all-inventory/index.htm'

    # --- 2. Determine page type ---
    is_new  = any(k in path for k in _NEW_KWS) or any(y in path for y in ['2024', '2025', '2026', '2027'])
    is_used = any(k in path for k in _USED_KWS)
    is_cert = any(k in path for k in _CERT_KWS)
    is_all  = any(k in path for k in _ALL_KWS) or (is_new and is_used)
    is_gen  = any(k in path for k in _GEN_KWS)

    # Check instructions (custom rules) for explicit inventory type overriding
    if instructions:
        inst_low = instructions.lower()
        if any(kw in inst_low for kw in ['new vehicle', 'new inventory', 'new car', 'new truck', 'new bargain', 'new option']):
            is_new = True
            is_used = False
        elif any(kw in inst_low for kw in ['used vehicle', 'used inventory', 'pre-owned', 'used car', 'used truck']):
            is_used = True
            is_new = False

    # Mileage-specific pages (low-mileage, mileage-selection, etc.) → treat as used inventory
    _MILEAGE_SLUGS = ['low-mileage', 'mileage-selection', 'low-miles', 'low mileage']
    _slug_has_mileage = any(k in slug_spaces for k in _MILEAGE_SLUGS) or any(k in path for k in ['/low-mileage', '/mileage-selection', '/low-miles'])
    if _slug_has_mileage and not is_new and not is_cert and not is_all:
        is_used = True


    # If it's a model landing page but no type is specified, default to NEW
    if not is_used and not is_cert and not is_all and not is_gen:
        # Check if any model key is in the path
        if any(f"-{m.replace(' ', '-')}" in path or f"/{m.replace(' ', '-')}" in path for m in LOCAL_MODELS.keys()):
            is_new = True

    # Generic pages (directions, serving areas) → sum new + used
    if is_gen and not is_new and not is_used and not is_all:
        if '/compare/' in path or '/research/' in path:
            is_new = True # Comparison and Research pages almost always promote new inventory
        else:
            return f'SUM: {new_inv_path} | {used_inv_path}'

    if is_all:
        base_path = all_inv_path
    elif is_cert:
        base_path = cert_inv_path
    elif is_used:
        base_path = used_inv_path
    elif is_new:
        base_path = new_inv_path
    else:
        # Final fallback: if it's a specific page but we can't tell, assume NEW
        base_path = new_inv_path

    # --- 3. Extract filter from slug ---
    found_model = None
    found_make  = None
    found_body  = None

    # Identify brands the dealer likely sells from domain
    dealer_brands = []
    domain_clean = domain_low.replace('-', '').replace('_', '')
    for key, val in LOCAL_MAKES.items():
        if key in domain_clean and len(key) > 3:
            if val not in dealer_brands: dealer_brands.append(val)
    if 'vw' in domain_clean: dealer_brands.append('Volkswagen')
    if 'mg' in domain_clean: dealer_brands.append('MG')

    # Normalize for matching
    slug = f" {slug} "

    # Match fuel types first (Allow multiple)
    found_fuels = []
    for key, val in LOCAL_FUEL_TYPES.items():
        if f" {key} " in slug:
            if val not in found_fuels:
                found_fuels.append(val)

    # Match models
    model_matches = []
    # Two normalized slugs: one with spaces (normal models) and one keeping hyphens (F-150, CR-V, etc.)
    slug_norm        = f" {slug_spaces.strip()} "
    slug_norm_hyphen = f" {slug_hyphens.strip()} "
    print(f"DEBUG: Analyzing slug for models: '{slug_norm}' | hyphen-slug: '{slug_norm_hyphen}'")
    
    for key, val in sorted(LOCAL_MODELS.items(), key=lambda kv: -len(kv[0])):
        # Determine which slug to use: if the model key contains a hyphen, use the hyphen slug
        search_slug = slug_norm_hyphen if '-' in key else slug_norm
        
        match = False
        pos = -1
        if '-' in key:
            import re
            m = re.search(r'\b' + re.escape(key) + r'\b', search_slug)
            if m:
                match = True
                pos = m.start()
        else:
            pos = search_slug.find(f" {key} ")
            if pos != -1:
                match = True
                
        if match:
            # Avoid false matching of the common English word 'is' on non-Lexus pages
            if key == 'is' and 'Lexus' not in dealer_brands and 'lexus' not in slug_norm:
                continue
            # Lexus 2-letter model codes (tx, nx, rx, ux, rz, gx, lx) are also US state
            # abbreviations or common short strings. Only match them for Lexus dealers.
            _LEXUS_ONLY_KEYS = {'tx', 'nx', 'rx', 'ux', 'rz', 'gx', 'lx'}
            if key in _LEXUS_ONLY_KEYS and 'Lexus' not in dealer_brands and 'lexus' not in domain_low:
                continue
            # Block US state abbreviations that appear at the END of the slug
            # (e.g. "used-sedans-el-paso-tx" → tx is a state, not a model)
            _US_STATES = {
                'al','ak','az','ar','ca','co','ct','de','fl','ga','hi','id','il','in',
                'ia','ks','ky','la','me','md','ma','mi','mn','ms','mo','mt','ne','nv',
                'nh','nj','nm','ny','nc','nd','oh','ok','or','pa','ri','sc','sd','tn',
                'tx','ut','vt','va','wa','wv','wi','wy','dc',
            }
            if key in _US_STATES and slug_norm.strip().endswith(f' {key}'):
                continue
            # Check if this model belongs to a dealer brand
            is_dealer_model = False
            for db in dealer_brands:
                if db.lower() in key.lower():
                    is_dealer_model = True
                    break
            model_matches.append((key, val, pos, is_dealer_model))
            
    if model_matches:
        # Sort matches by length descending so we check longest matches first
        model_matches.sort(key=lambda x: -len(x[0]))
        accepted_models = []
        occupied_intervals = []
        
        for key, val, pos, is_dlr in model_matches:
            start = pos
            end = pos + len(key)
            overlap = False
            for (os, oe) in occupied_intervals:
                if max(start, os) < min(end, oe):
                    overlap = True
                    break
            if not overlap:
                accepted_models.append((key, val, pos, is_dlr))
                occupied_intervals.append((start, end))

        # Check if it's a comparison/research hub or a generic landing page
        is_hub_page = any(k in path for k in ['/compare/', '/research/'])
        
        if is_hub_page:
            # For comparison pages, prioritize DEALER models, then POSITION (first mentioned)
            dealer_models = [m for m in accepted_models if m[3]]
            if dealer_models:
                dealer_models.sort(key=lambda x: x[2])
                final_models = [dealer_models[0][1]]
            else:
                accepted_models.sort(key=lambda x: x[2])
                final_models = [accepted_models[0][1]]
        else:
            # For normal pages, we include ALL non-overlapping models found in the slug
            accepted_models.sort(key=lambda x: x[2])
            final_models = []
            for am in accepted_models:
                if am[1] not in final_models:
                    final_models.append(am[1])
            
        # --- NEW: Family Expansion (Silverado 3500 -> 3500 HD + 3500 HD Chassis Cab, etc.) ---
        families = ['Silverado 1500', 'Silverado 2500', 'Silverado 3500', 
                    'Silverado 4500', 'Silverado 5500', 'Silverado 6500',
                    'Sierra 1500', 'Sierra 2500', 'Sierra 3500',
                    'F-150', 'F-250', 'F-350', 'Ram 1500', 'Ram 2500', 'Ram 3500',
                    'Super Duty']
        
        expanded_final_models = []
        for fm in final_models:
            fm_decoded = fm.replace('%20', ' ')
            expanded_variants = []
            
            # Super Duty special case
            if 'Super Duty' in fm_decoded or 'super duty' in slug:
                expanded_variants = ['F-250SD', 'F-350SD', 'F-450SD', 'F-550SD', 'F-600SD', 'F-650SD']
            else:
                for family in families:
                    if family in fm_decoded:
                        for m_val in set(LOCAL_MODELS.values()):
                            m_val_decoded = m_val.replace('%20', ' ')
                            if family in m_val_decoded:
                                if m_val not in expanded_variants:
                                    expanded_variants.append(m_val)
                        break
            
            if expanded_variants:
                for ev in expanded_variants:
                    if ev not in expanded_final_models:
                        expanded_final_models.append(ev)
            else:
                if fm not in expanded_final_models:
                    expanded_final_models.append(fm)
                    
        found_model = '%2C'.join(expanded_final_models)

    # --- Path-folder make hint for numeric-only model slugs ---
    # Handles URLs like /used-ram/3500-attica-ny.htm or /used-chevy/1500-trucks.htm
    # where the make is in the folder and the model number is standalone in the slug.
    if not found_model:
        import re as _re_truck
        # Detect standalone truck numbers in slug (e.g. 1500, 2500, 3500, etc.)
        number_match = _re_truck.search(r'\b(1500|2500|3500|4500|5500|6500|150|250|350|450|550|600|650)\b', slug)
        if number_match:
            truck_num = number_match.group(1)
            # Check path folders for a make hint (e.g. /used-ram/, /used-chevy/)
            # Use substring match so 'ram' matches inside 'used-ram'
            path_parts = [p.lower() for p in path.split('/') if p]
            path_make_hint = None
            for part in path_parts:
                for key, val in LOCAL_MAKES.items():
                    # Exact match OR key is contained as a whole word/segment within part
                    part_clean = part.replace('-', ' ').replace('_', ' ')
                    if key == part or key == part_clean or key in part_clean.split():
                        path_make_hint = val
                        break
                if path_make_hint:
                    break
            
            if path_make_hint:
                # Build the synthesized model name: "Ram 3500", "Chevrolet 1500", etc.
                synthesized = f"{path_make_hint} {truck_num}"
                # Look up directly in LOCAL_MODELS (longest/most-specific key first)
                synth_lower = synthesized.lower()
                for key in sorted(LOCAL_MODELS.keys(), key=len, reverse=True):
                    val = LOCAL_MODELS[key]
                    if key == synth_lower or key.replace(' ', '-') == synth_lower.replace(' ', '-'):
                        found_model = val
                        if not found_make:
                            found_make = path_make_hint
                        print(f"DEBUG: Path-folder model hint matched '{synthesized}' -> {found_model}")
                        break
                # If no exact match found, use make+number directly
                if not found_model:
                    found_model = synthesized.replace(' ', '%20')
                    if not found_make:
                        found_make = path_make_hint
                    print(f"DEBUG: Path-folder model hint (no DB match): {found_model}")
                
                # Apply family expansion to path-folder found models
                # For Ram: values are number-only (e.g. '3500'), so match by key prefix
                if found_model:
                    pf_expanded = []
                    if path_make_hint == 'Ram':
                        # Find all Ram model variants that share the same truck number
                        for k, m_val in LOCAL_MODELS.items():
                            if k.startswith('ram ') or k.startswith('ram-'):
                                m_dec = m_val.replace('%20', ' ')
                                # e.g. truck_num='3500' matches '3500' and '3500 Chassis'
                                if truck_num in m_dec.split():
                                    if m_val not in pf_expanded:
                                        pf_expanded.append(m_val)
                    else:
                        # Generic family expansion by full decoded name
                        gen_families = ['Silverado 1500', 'Silverado 2500', 'Silverado 3500',
                                        'Sierra 1500', 'Sierra 2500', 'Sierra 3500',
                                        'F-150', 'F-250', 'F-350']
                        pf_model_decoded = found_model.replace('%20', ' ')
                        for family in gen_families:
                            if family.lower() in pf_model_decoded.lower():
                                for m_val in set(LOCAL_MODELS.values()):
                                    m_dec = m_val.replace('%20', ' ')
                                    if family.lower() in m_dec.lower():
                                        if m_val not in pf_expanded:
                                            pf_expanded.append(m_val)
                                break
                    if len(pf_expanded) > 1:
                        found_model = '%2C'.join(pf_expanded)
                        print(f"DEBUG: Path-folder family expansion -> {found_model}")

    # Match makes
    found_make_in_slug = False
    found_makes_in_slug = []
    print(f"DEBUG: Analyzing slug for makes: '{slug_norm}'")
    for key, val in LOCAL_MAKES.items():
        norm_key = key.replace('-', ' ').replace('_', ' ')
        if f" {norm_key} " in slug_norm:
            if val not in found_makes_in_slug:
                found_makes_in_slug.append(val)
                
    if found_makes_in_slug:
        # Prioritize brands the dealer sells
        for m in found_makes_in_slug:
            if m in dealer_brands:
                found_make = m
                found_make_in_slug = True
                break
        
        # If no dealer brand found in slug, but we are on a comparison page, 
        # check if the path itself has a brand hint (e.g. /compare/ram/)
        if not found_make and '/compare/' in path:
            parts = [p for p in path.split('/') if p]
            try:
                idx = parts.index('compare')
                if len(parts) > idx + 1:
                    potential_brand_slug = parts[idx+1]
                    for key, val in LOCAL_MAKES.items():
                        if potential_brand_slug == key:
                            found_make = val
                            found_make_in_slug = True
                            break
            except: pass
            
        if not found_make:
            # Fallback to first one found
            found_make = found_makes_in_slug[0]
            found_make_in_slug = True

    # --- NEW: Domain-based Make Inference ---
    # Only infer from domain if it's NOT a used inventory page (used is usually multi-brand)
    # OR if we explicitly found the make in the slug.
    if not found_make:
        domain_low = domain.lower()
        for key, val in LOCAL_MAKES.items():
            # Check if the make name is part of the domain (e.g. 'kia' in 'kiaofwaldorf')
            if key in domain_low and len(key) > 3: # Avoid short strings like 'vw' or 'mg'
                found_make = val
                break
        # Fallback for very short but common makes
        if not found_make:
            if 'vw' in domain_low: found_make = 'Volkswagen'
            if 'mg' in domain_low: found_make = 'MG'

    # Match body styles
    for key, val in LOCAL_BODY_STYLES.items():
        if f" {key} " in slug_norm:
            found_body = val
            break
            
    # Match trims — skip if trim word is already part of the matched model name
    # e.g. "bronco sport" has "sport" but "sport" is inside "bronco sport" → no trim
    found_trim = None
    accepted_keys = [am[0] for am in accepted_models] if 'accepted_models' in locals() and accepted_models else []
    for key, val in LOCAL_TRIMS.items():
        if f" {key} " in slug:
            if any(key in ak for ak in accepted_keys):
                continue
            # Ignore 'luxury' trim for Mercedes-Benz as it's typically used generically in URLs (e.g. luxury-suvs)
            if key == 'luxury' and found_make == 'Mercedes-Benz':
                continue
            found_trim = val
            break
            
    # --- NEW: Trim Family Expansion (V-Series -> V-Series + V-Series Premium) ---
    if found_trim:
        trim_families = ['V-Series']
        expanded_trims = []
        found_trim_decoded = found_trim.replace('%20', ' ')
        for family in trim_families:
            if family in found_trim_decoded:
                for t_val in set(LOCAL_TRIMS.values()):
                    t_val_decoded = t_val.replace('%20', ' ')
                    if family in t_val_decoded:
                        if t_val not in expanded_trims:
                            expanded_trims.append(t_val)
                break
        if expanded_trims:
            found_trim = '%2C'.join(expanded_trims)

    # --- 4. Build query params ---
    params = []
    if found_model:
        for m in found_model.split('%2C'):
            params.append(f'model={m}')
    elif found_body:
        # Prioritize model over body style if both are present in slug
        # DI uses bodyStyle=, DDC uses normalBodyStyle=
        body_param = 'bodyStyle' if is_dealer_inspire else 'normalBodyStyle'
        if 'reederchevy' in domain_low:
            body_param = 'normalBodyStyle'
        if 'bakercdjrofcadillac' in domain_low:
            body_param = 'bodyStyle'
        # DDC sites often use 'Passenger%20Van' for the generic 'Van' body type
        body_val = found_body
        if found_body == 'Van' and not is_dealer_inspire:
            body_val = 'Passenger%20Van'
        params.append(f'{body_param}={body_val}')
        
    # --- Special Dealer Override: baldhilldodgechrysler.net ---
    if 'baldhilldodgechrysler' in domain_low and found_body == 'Truck':
        if is_new or 'new' in path:
            params = [p for p in params if not (p.startswith('normalBodyStyle=') or p.startswith('bodyStyle=') or p.startswith('make='))]
            params.append('bodyStyle=Pickup')
            params.append('make=Ram')
        elif is_used or 'used' in path or 'pre-owned' in path:
            params = [p for p in params if not (p.startswith('normalBodyStyle=') or p.startswith('bodyStyle='))]
            params.append('bodyStyle=Truck%20Crew%20Cab')
            params.append('bodyStyle=Truck%20CrewMax')
            params.append('bodyStyle=Truck%20SuperCrew')

    if found_make:
        # 1. Redundancy check: if the domain already implies this make
        is_redundant = False
        domain_clean = domain_low.replace('-', '').replace('_', '')
        # Check all aliases for this brand in the domain
        for alias, m_val in LOCAL_MAKES.items():
            if m_val == found_make and alias in domain_clean:
                is_redundant = True
                break
        
        # 2. Used Inventory Multi-brand Rule:
        # If it's a used inventory page, we ONLY add the make filter if it was explicitly in the slug.
        # Otherwise, we assume it's a general used trucks/suvs page.
        if is_used and not found_make_in_slug:
            # Skip adding make= filter for used pages unless explicitly requested in URL
            pass
        elif found_make == 'Cadillac':
            # Cadillac dealers often prefer no make=Cadillac filter
            pass
        elif found_make_in_slug:
            # If explicitly in slug, ALWAYS add it (intentional)
            params.append(f'make={found_make}')
        elif not is_redundant:
            # If not in slug but also not in domain, add it
            params.append(f'make={found_make}')
        
    if found_trim:
        for t in found_trim.split('%2C'):
            params.append(f'trim={t}')
        
        # Special 'class' filter for Mercedes-Benz
        if found_make == 'Mercedes-Benz' and not found_model:
            for key, val in LOCAL_MERCEDES_CLASSES.items():
                if f" {key} " in slug:
                    params.append(f'superModel={val}')
                    break
    
    # Match Fuel Efficient request
    is_fuel_efficient = 'fuel efficient' in slug or (instructions and 'fuel efficient' in instructions.lower())
    if is_fuel_efficient:
        is_ford = (found_make == 'Ford') or ('ford' in domain_low)
        if is_ford:
            mpg_type = 'cityMpg' if instructions and 'city' in instructions.lower() else 'highwayMpg'
            mpg_val = '35'
        else:
            mpg_type = 'cityFuelEconomy' if instructions and 'city' in instructions.lower() else 'highwayFuelEconomy'
            mpg_val = '30'

        if instructions:
            import re
            mpg_match = re.search(r'(\d{2,3})\s*mpg', instructions, re.IGNORECASE)
            if mpg_match:
                mpg_val = mpg_match.group(1)
        params.append(f'{mpg_type}={mpg_val}-')

    # Match price or mileage filters (Bargain / Under X / Low Mileage / Custom Rule Price)
    is_mileage = any(k in slug for k in [' miles ', ' mile ', ' mileage ', ' low mileage', 'low-mileage', 'mileage-selection', 'low-miles'])
    inst_low = instructions.lower() if instructions else ""
    has_price_rule = any(k in slug for k in [' bargain ', ' under ']) or is_mileage or any(k in inst_low for k in ['under', 'below', 'bargain', '$'])

    if has_price_rule:
        # Default limits
        limit = '30000' if is_mileage else '20000'
        
        # Check explicit numbers in instructions (e.g. "below $30,000" or "under 30k")
        if instructions:
            import re
            pr_m = re.search(r'(?:under|below|less than|filter by|vehicles|cars|\$)\s*\$?(\d{2,3})[,\.]?(\d{3})', inst_low)
            if not pr_m:
                pr_m = re.search(r'\$?(\d{2,3})[,\.]?(\d{3})', inst_low)
            pr_k = re.search(r'\$?(\d{1,3})\s*k', inst_low)

            if pr_m:
                limit = pr_m.group(1) + pr_m.group(2)
            elif pr_k:
                limit = str(int(pr_k.group(1)) * 1000)

        if not instructions or limit == '20000':
            if ' 10k ' in slug or ' 10000 ' in slug: limit = '10000'
            elif ' 15k ' in slug or ' 15000 ' in slug: limit = '15000'
            elif ' 20k ' in slug or ' 20000 ' in slug: limit = '20000'
            elif ' 30k ' in slug or ' 30000 ' in slug: limit = '30000'
            elif ' 40k ' in slug or ' 40000 ' in slug: limit = '40000'
            elif ' 50k ' in slug or ' 50000 ' in slug: limit = '50000'

        if is_mileage:
            params.append(f'odometer=0-{limit}')
        else:
            params.append(f'internetPrice=1-{limit}')


    for f in found_fuels:
        # Avoid duplicate filtering if the model name already specifies the fuel type
        # (e.g. if model is "Tucson%20Hybrid" or "RAV4 Plug-in Hybrid", skip normalFuelType)
        if found_model:
            found_model_decoded = found_model.replace('%20', ' ').replace('%2C', ',').lower()
            if f.lower() in found_model_decoded:
                continue
        params.append(f'normalFuelType={f}')

    # Ensure base_path has a base file (only if it doesn't end with .htm or .html)
    if not (base_path.endswith('.htm') or base_path.endswith('.html')):
        base_path = base_path.rstrip('/') + '/index.htm'

    if not params:
        # If it's already an inventory index page and no specific filter found, compare with itself
        if (is_new or is_used or is_cert or is_all) and ('inventory' in path or 'index.htm' in path):
            return base_path
        return None

    return base_path + '?' + '&'.join(params)


# Keywords that indicate a special fuel/variant type
_SPECIAL_KWS = ['hybrid', 'ev', 'electric', 'plug-in', 'phev', 'e-tron', 'ioniq']

def refine_with_facets(driver, target_url, base_path):
    """
    Scrapes the base inventory page to find all available sub-models or variants 
    matching the current filter, ensuring we capture all 'Silverado' or 'F-150' types.
    """
    created_driver = False
    if not driver:
        try:
            driver = get_selenium_driver()
            created_driver = True
        except Exception as e:
            print(f"Could not spawn driver for refinement: {e}")
            return target_url
        
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(target_url)
        params = parse_qs(parsed.query)
        
        if 'model' not in params or not params['model']:
            return target_url
            
        base_model = params['model'][0] # e.g. "Silverado"
        if len(base_model) < 2: return target_url

        # 1. Rebuild refinement URL
        # IMPORTANT: Remove 'model' AND 'normalFuelType' to see ALL model checkboxes.
        # If we keep 'normalFuelType=Hybrid', some 'Accord' (non-hybrid) boxes might be hidden.
        refine_params = {k: v for k, v in params.items() if k not in ['model', 'normalFuelType']}
        refine_url = urlunparse(parsed._replace(query=urlencode(refine_params, doseq=True)))
        
        print(f"DEBUG: Refining '{base_model}' by visiting: {refine_url}")
        driver.get(refine_url)
        time.sleep(5) # Wait for DDC AJAX facets
        
        # 1.5. Expand collapsed panels to force DDC to render checkbox elements
        try:
            triggers = driver.find_elements('css selector', '.facet-list-group [aria-expanded="false"], .panel-heading [aria-expanded="false"]')
            if triggers:
                print(f"DEBUG: Found {len(triggers)} collapsed facet panels. Expanding them...")
                for trigger in triggers:
                    try:
                        driver.execute_script("arguments[0].click();", trigger)
                    except Exception as te:
                        pass
                time.sleep(3) # Wait for panel expand rendering
        except Exception as ee:
            print(f"DEBUG: Error expanding panels: {ee}")
            
        # --- Handle Redirects ---
        # If the base inventory page redirects (common in Lincoln/specific dealers),
        # we MUST apply the filters to the NEW final URL path.
        final_url = driver.current_url
        if urlparse(final_url).path != parsed.path:
            print(f"DEBUG: Redirect detected: {parsed.path} -> {urlparse(final_url).path}")
            parsed = urlparse(final_url)
        
        # 2. Find all model checkboxes
        found_variants = []
        inputs = driver.find_elements('css selector', 'input[name="model"], input[name="model_facet"], [data-facet-name="model"] input')
        
        for inp in inputs:
            val = inp.get_attribute('value')
            if not val: continue
            
            val_low = val.lower()
            base_low = base_model.lower()
            
            # Match if the variant is exactly the base_model OR starts with 'base_model ' 
            # (e.g. 'Silverado' matches 'Silverado 1500' but 'Blazer' NOT 'Trailblazer')
            is_start_match = val_low == base_low or val_low.startswith(base_low + " ")
            
            if is_start_match:
                # NEW: Avoid auto-adding 'Hybrid', 'EV', 'Plug-in' variants if the base_model didn't ask for them.
                # Using word boundaries to avoid matching 'ev' inside 'chevrolet'
                has_special = False
                for kw in _SPECIAL_KWS:
                    if f" {kw} " in f" {val_low} " or val_low.endswith(f" {kw}") or val_low.startswith(f"{kw} "):
                        has_special = True
                        break
                
                requested_special = False
                for kw in _SPECIAL_KWS:
                    if f" {kw} " in f" {base_low} " or base_low.endswith(f" {kw}") or base_low.startswith(f"{kw} "):
                        requested_special = True
                        break
                
                if has_special and not requested_special:
                    # Only add if the target_url itself contains the special keyword AS A WORD
                    # (To avoid matching 'ev' in 'chevrolet')
                    url_low = target_url.lower().replace('-', ' ').replace('_', ' ').replace('/', ' ')
                    found_in_url = False
                    for kw in _SPECIAL_KWS:
                        if f" {kw} " in f" {url_low} ":
                            found_in_url = True
                            break
                    
                    if not found_in_url:
                        continue
                
                if val not in found_variants:
                    found_variants.append(val)
        
        # 3. Always ensure the original base_model is in the list if it matches
        # This handles cases where the user wants "Accord" + "Accord Hybrid"
        if base_model not in found_variants:
            # Only add if it's a reasonably certain match
            found_variants.append(base_model)

        # 4. Rebuild the final URL (keeping the original fuel filters)
        if found_variants:
            print(f"DEBUG: Found variants for '{base_model}': {found_variants}")
            params['model'] = found_variants
            # Return relative path to avoid corrupting cross-dealer DB with absolute URLs
            return parsed.path + '?' + urlencode(params, doseq=True)
            
    except Exception as e:
        print(f"Facet refinement error: {e}")
    finally:
        if created_driver and driver:
            try:
                driver.quit()
            except:
                pass
        
    return target_url

def extract_inventory_configs(html: str):
    """
    Extracts inventory config IDs from the page HTML.

    Strategy (occurrence-based):
    - Each "listing.config.id" JSON key is ONE occurrence (may contain comma-separated values).
    - If an occurrence contains AT LEAST ONE specific config (e.g. 'auto-certified-used',
      'auto-new-cadillac-electric'), keep ALL configs from that occurrence — including any
      generic siblings (e.g. 'auto-used' paired with 'auto-certified-used' belongs together).
    - If an occurrence contains ONLY generic configs (e.g. 'auto-new,auto-used' from a
      Specials/Promos widget), it is treated as secondary-widget noise and ignored when
      a specific occurrence already exists.

    Examples:
      HTML has ONE occurrence "auto-used,auto-certified-used"
        → specific occurrence (has 'auto-certified-used') → show BOTH  ✅

      HTML has ONE occurrence "auto-new-cadillac-electric"
        AND separate occurrence "auto-new,auto-used" (Specials widget)
        → specific occurrence found → ignore purely-generic occurrence
        → show only 'auto-new-cadillac-electric'  ✅
    """
    import re
    if not html: return "", []
    site_id = ""
    site_match = re.search(r'"siteId"\s*:\s*"([^"]+)"', html)
    if site_match: site_id = site_match.group(1)

    # Configs that are considered "generic" when they appear ALONE
    _GENERIC_CONFIGS = {'auto-new', 'auto-used', 'auto-certified', 'auto-all',
                        'new', 'used', 'certified', 'all'}

    # Parse each "listing.config.id" occurrence as a group
    occurrences = []
    for m in re.findall(r'"listing\.config\.id"\s*:\s*"([^"]+)"', html):
        group = [v.strip() for v in m.split(',') if v.strip()]
        if group:
            occurrences.append(group)

    if not occurrences:
        return site_id, []

    # Classify each occurrence
    specific_occurrences = []  # has at least one non-generic config
    generic_occurrences  = []  # all configs are generic

    for group in occurrences:
        has_specific = any(c not in _GENERIC_CONFIGS for c in group)
        if has_specific:
            specific_occurrences.append(group)
        else:
            generic_occurrences.append(group)

    # Decide which occurrences to use
    source_occurrences = specific_occurrences if specific_occurrences else generic_occurrences

    # Flatten, preserving order, deduplicating
    configs = []
    for group in source_occurrences:
        for c in group:
            if c not in configs:
                configs.append(c)

    return site_id, configs



def validate_inventory(url: str, nav_links: list, initial_html: str = None, instructions: str = ""):
    """Uses provided HTML or Selenium to check inventory count and compares it with expected filter URL count."""
    import re
    driver = None
    bugs = []

    inventory_info = {
        'status': 'not_found',
        'page_count': None,
        'filter_count': None,
        'filter_url': None
    }
    
    try:
        # Determine if the current page is an inventory page
        path_lower = urlparse(url).path.lower()
        inventory_path_keywords = [
            'new-inventory', 'used-inventory', 'certified-inventory', 'all-inventory', 
            'pre-owned-inventory', 'bargain-inventory', 'inventory/new', 'inventory/used', 'inventory/all',
            '/new-cars', '/used-cars', '/certified-cars', '/pre-owned', '/cpo', '/inventory/', '/bargain'
        ]

        is_inv_path = any(k in path_lower for k in inventory_path_keywords)
        
        has_inv_widgets = False
        if initial_html:
            from bs4 import BeautifulSoup as BS
            temp_soup = BS(initial_html, 'html.parser')
            inv_elements = temp_soup.select(
                '.ddc-vehicle-card, .vehicle-card, .srp-vehicle, .inv-vehicle, .vehicle-item, .srp-item, '
                '[data-widget-name*="inventory-listing"], [data-widget-name*="inv-listing"], '
                '[data-widget-id*="inventory-listing"], .ws-inv-listing, .inventory-listing, '
                '[class*="vehicle-card"], [class*="srp-item"], [class*="inventory-item"]'
            )
            if inv_elements:
                has_inv_widgets = True
                
        has_grid = False
        has_list = False
        try:
            has_grid = temp_soup.find('ul', class_=lambda c: c and 'vehicle-card-grid' in c) is not None
            has_list = temp_soup.find('ul', class_=lambda c: c and 'vehicle-card-list' in c) is not None
        except NameError:
            pass
        inventory_info['layout'] = 'Grid' if has_grid else ('List' if has_list else 'Unknown')
        
        is_inventory_page = is_inv_path or has_inv_widgets
        
        if not is_inventory_page:
            inventory_info['status'] = 'none'
            inventory_info['source'] = 'none'
            return bugs, inventory_info
        def find_vehicle_count(driver_or_soup, html_content=None):
            def is_false_truck_count(val_str, full_txt, start_idx):
                if val_str in ['150', '250', '350', '450', '550', '600', '650', '1500', '2500', '3500', '4500', '5500', '6500']:
                    preceding = full_txt[max(0, start_idx - 35):start_idx].lower()
                    if any(w in preceding for w in ['ram', 'silverado', 'sierra', 'chevy', 'chevrolet', 'gmc', 'dodge', 'hd', 'duty', 'ford', 'f-', 'super', 'rho']):
                        return True
                return False

            # Check if we have a driver or just soup
            is_driver = hasattr(driver_or_soup, 'find_elements')
            
            # 1. Targeted Selector Fallback
            selectors = [
                ".vehicle-count", ".total-results", ".inventory-count", 
                "[data-widget-id='inventory-listing-default'] .count",
                ".totalVehicles", ".results-count", "span.count",
                "strong[aria-live='polite']", "div[aria-live='polite']"
            ]
            
            if is_driver:
                for sel in selectors:
                    try:
                        elems = driver_or_soup.find_elements('css selector', sel)
                        for el in elems:
                            txt = el.text.strip()
                            if not txt: continue
                            if " of " in txt.lower():
                                parts = re.findall(r'(\d[\d,]*)', txt)
                                if parts:
                                    val = parts[-1].replace(',', '')
                                    if val.isdigit() and int(val) > 0:
                                        if is_false_truck_count(val, txt, txt.lower().rfind(val.lower())):
                                            continue
                                        return val
                            m = re.search(r'(\d[\d,]*)', txt)
                            if m:
                                val = m.group(1).replace(',', '')
                                if val.isdigit() and int(val) > 0:
                                    if is_false_truck_count(val, txt, m.start()):
                                        continue
                                    return val
                    except: continue
            
            # 2. BS4 Scan (Works on both static HTML and Driver Source)
            raw_html = html_content if html_content else (driver_or_soup.page_source if is_driver else None)
            if raw_html:
                from bs4 import BeautifulSoup as BS
                temp_soup = BS(raw_html, 'html.parser')
                
                # Check aria-live specifically
                polite_elements = temp_soup.find_all(attrs={"aria-live": "polite"})
                for el in polite_elements:
                    txt = el.get_text(separator=' ', strip=True)
                    m = re.search(r'(\d[\d,]*)\s*(?:Vehicles?|Veh[íi]culos?)', txt, re.IGNORECASE)
                    if m:
                        val = m.group(1).replace(',', '')
                        if is_false_truck_count(val, txt, m.start()):
                            continue
                        return val

                # Check selectors in BS4
                best_val = None
                facet_fallback = None
                
                for sel in selectors:
                    found = temp_soup.select(sel)
                    for el in found:
                        is_sub_count = False
                        parent = el.parent
                        while parent:
                            classes = parent.get('class', [])
                            if any(c in ['facet-list', 'panel-body', 'facet-filters', 'facet-list-group'] for c in classes):
                                is_sub_count = True
                                break
                            parent = parent.parent
                        
                        txt = el.get_text(strip=True)
                        m = re.search(r'(\d[\d,]*)', txt)
                        if m:
                            val = m.group(1).replace(',', '')
                            if val.isdigit() and int(val) > 0:
                                parent_txt = el.parent.get_text(separator=' ', strip=True) if el.parent else txt
                                m_parent = re.search(re.escape(val), parent_txt)
                                start_idx = m_parent.start() if m_parent else 0
                                if is_false_truck_count(val, parent_txt, start_idx):
                                    continue
                                if is_sub_count:
                                    if not facet_fallback: facet_fallback = val
                                else:
                                    return val # Found main count!
                
                if facet_fallback:
                    return facet_fallback

                # 3. Global Regex Fallback (Final attempt on raw HTML)
                # Handle &nbsp; and multiple spaces
                clean_html = raw_html.replace('&nbsp;', ' ').replace('&#160;', ' ')
                for m in re.finditer(r'(\d[\d,]*)\s*(?:Vehicles?|Matches|Results|Veh[íi]culos?)', clean_html, re.IGNORECASE):
                    gv_clean = m.group(1).replace(',', '')
                    if gv_clean.isdigit() and int(gv_clean) > 0:
                        if is_false_truck_count(gv_clean, clean_html, m.start()):
                            continue
                        return gv_clean
                
                # 5. Script-based JSON/Data Extraction (DDC Internals)
                # DDC often stores counts in window.inventory or similar JS objects
                script_patterns = [
                    r'["\']inventoryCount["\']\s*:\s*(\d+)',
                    r'["\']totalVehicles["\']\s*:\s*(\d+)',
                    r'["\']totalResults["\']\s*:\s*(\d+)',
                    r'["\']count["\']\s*:\s*(\d+)',
                    r'inventory\s*=\s*\{[^}]*["\']count["\']\s*:\s*(\d+)'
                ]
                for sp in script_patterns:
                    sm = re.search(sp, raw_html)
                    if sm:
                        val = sm.group(1)
                        if val.isdigit() and int(val) > 0:
                            return val

            # 3. Regex on raw text
            texts_to_check = []
            if is_driver:
                try: texts_to_check.append(driver_or_soup.execute_script("return document.body.innerText"))
                except: pass
            if raw_html:
                try: 
                    from bs4 import BeautifulSoup as BS
                    texts_to_check.append(BS(raw_html, 'html.parser').get_text(separator=' ', strip=True))
                except: pass

            patterns = [
                r'(?<!\$)\b([\d,]+)\s*(?:Veh[íi]culos?|Vehicles?|Results?|Matches?|Matching)\b(?!\s*miles?)',
                r'\b(?:Showing|Found|Displaying)\s+([\d,]+)\b'
            ]
            for txt in texts_to_check:
                if not txt: continue
                for p in patterns:
                    for m in re.finditer(p, txt, re.IGNORECASE):
                        val = m.group(1).replace(',', '')
                        if val.isdigit() and int(val) > 0:
                            if is_false_truck_count(val, txt, m.start()):
                                continue
                            return val

            return None

        current_count = None
        local_res = None
        is_generic_dealer_page = False
        
        if initial_html:
            current_count = find_vehicle_count(None, initial_html)
            if current_count:
                print(f"DEBUG: Found count {current_count} in static HTML")
                local_res = local_inventory_inference(url, initial_html, instructions)
                is_generic_dealer_page = local_res and local_res.startswith('SUM:')

        if not current_count:
            driver = get_selenium_driver()
            driver.get(url)
            
            # Since we use page_load_strategy='none', we must wait manually for content
            print("DEBUG: Waiting for Selenium content...")
            for _ in range(10):
                time.sleep(1)
                current_count = find_vehicle_count(driver, driver.page_source)
                if current_count: break
                # If we've waited 5 seconds and still nothing, try to trigger AJAX by scrolling
                if _ == 5:
                    driver.execute_script("window.scrollTo(0, 500);")
            
            # Determine page type for inference
            local_res = local_inventory_inference(url, driver.page_source, instructions)
            is_generic_dealer_page = local_res and local_res.startswith('SUM:')
            
            if not is_generic_dealer_page:
                for attempt in range(2):
                    current_count = find_vehicle_count(driver, driver.page_source)
                    if current_count: break
                    driver.execute_script("window.scrollTo(0, 1000);")
                    time.sleep(4)
            else:
                current_count = "0"
        else:
            # We already have count, but we still need local_res for the filter
            local_res = local_inventory_inference(url, initial_html, instructions)

        if not current_count:
            inventory_info['status'] = 'not_found'
            return bugs, inventory_info
            
        inventory_info['page_count'] = current_count
        inventory_info['status'] = 'ai_inference'
        
        html_to_parse = initial_html if initial_html else (driver.page_source if driver else "")
        s_id, c_ids = extract_inventory_configs(html_to_parse)
        inventory_info['site_id'] = s_id
        inventory_info['config_ids'] = c_ids
        
        # Determine domain and path from URL
        domain = urlparse(url).netloc
        raw_path = urlparse(url).path
        page_title = ""
        try:
            if driver: 
                page_title = driver.title
            elif initial_html: 
                from bs4 import BeautifulSoup as BS
                ts = BS(initial_html, 'html.parser')
                page_title = (ts.title.string if ts.title else "") or ""
        except: pass
        
        res = None
        
        # --- Pattern DB Lookup ---
        patterns = load_inventory_patterns()
        
        # --- 1. Persistent Memory Check (Auto-learned corrections) ---
        learned_filter = inventory_learner.get_filter(url)
        if learned_filter:
            print(f"DEBUG: Memory hit for {domain}{raw_path} -> {learned_filter}")
            res = learned_filter
            inventory_info['source'] = 'manual_correction'
        else:
            cached_filter = patterns.get(domain, {}).get(raw_path)
            if cached_filter:
                print(f"DEBUG: DB hit for {domain}{raw_path} -> {cached_filter}")
                res = cached_filter
                inventory_info['source'] = 'database_hit'
            elif local_res:
                print(f"DEBUG: Local inference for {domain}{raw_path} -> {local_res}")
                if driver:
                    base_inventory_path = local_res.split('?')[0]
                    res = refine_with_facets(driver, urljoin(url, local_res), base_inventory_path)
                else:
                    res = local_res
                inventory_info['source'] = 'local_match'
            else:
                # --- NLP Fallback ---
                inventory_info['source'] = 'nlp_inference'
                learned_examples = []
                for d, paths in patterns.items():
                    for p, f in paths.items():
                        if len(learned_examples) < 8:
                            learned_examples.append(f"- {p} -> {f}")

                nlp_res = nlp_inventory_fallback(
                    url,
                    page_title,
                    nav_links,
                    learned_examples
                )
                res = nlp_res

        if not res or (not res.startswith('/') and not res.startswith('SUM:') and not res.startswith('http')):
            if '/compare/' in raw_path or '/research/' in raw_path:
                inventory_info['status'] = 'informational'
                return bugs, inventory_info
            inventory_info['status'] = 'none'
            inventory_info['source'] = 'none'
            return bugs, inventory_info

        if instructions and res and not res.startswith('SUM:'):
            # Apply explicit user instructions (e.g. "below $30,000" or "new vehicles") to override DB/cached filters
            inst_low = instructions.lower()
            import re
            pr_m = re.search(r'(\d{2,3})[,\.]?(\d{3})', inst_low)
            pr_k = re.search(r'\$?(\d{1,3})\s*k', inst_low)
            if pr_m or pr_k:
                req_price = (pr_m.group(1) + pr_m.group(2)) if pr_m else str(int(pr_k.group(1)) * 1000)
                if 'internetprice' in res.lower():
                    res = re.sub(r'internetPrice=[^&]+', f'internetPrice=1-{req_price}', res, flags=re.IGNORECASE)
                else:
                    res = res + ('&' if '?' in res else '?') + f'internetPrice=1-{req_price}'
            
            if any(kw in inst_low for kw in ['new vehicle', 'new inventory', 'new car', 'new truck', 'new bargain', 'new option']):
                res = res.replace('/used-inventory/', '/new-inventory/').replace('/bargain-inventory/', '/new-inventory/')
            elif any(kw in inst_low for kw in ['used vehicle', 'used inventory', 'pre-owned', 'used car', 'used truck']):
                res = res.replace('/new-inventory/', '/used-inventory/')

        inventory_info['filter_url'] = res
        if inventory_info.get('status') in ['not_found', 'none', None]:
            inventory_info['status'] = 'ai_inference'



        
        # 3. Fetch matched filter(s)
        total_sum = 0
        urls_to_visit = []
        
        if res.startswith('SUM:'):
            urls_to_visit = [u.strip() for u in res.replace('SUM:', '').split('|')]
        else:
            urls_to_visit = [res]

        for target_path in urls_to_visit:
            f_url = urljoin(url, target_path)
            try:
                sub_count = None
                requires_js = '?' in f_url
                
                # Try curl_cffi first if no driver or as faster alternative, AND it doesn't strictly require JS
                if not driver and not requires_js:
                    try:
                        try:
                            r = requests.get(f_url, impersonate="chrome120", timeout=15)
                        except TypeError:
                            r = requests.get(f_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, timeout=15)
                        if r.status_code == 200:
                            sub_count = find_vehicle_count(None, r.text)
                    except Exception as ce:
                        print(f"DEBUG: request failed for sub-inventory {f_url}: {ce}")

                
                # Fallback to Selenium if needed OR if JS is required
                if not sub_count:
                    if not driver:
                        driver = get_selenium_driver()
                    driver.get(f_url)
                    time.sleep(8) # DDC Wait for JS filters to apply
                    sub_count = find_vehicle_count(driver, driver.page_source)
                
                # Extract target configs
                if not driver:
                    try:
                        r = requests.get(f_url, impersonate="chrome120", timeout=15)
                        t_html = r.text
                    except:
                        t_html = ""
                else:
                    t_html = driver.page_source
                    
                t_sid, t_cids = extract_inventory_configs(t_html)
                if t_sid and not inventory_info.get('target_site_id'):
                    inventory_info['target_site_id'] = t_sid
                if 'target_config_ids' not in inventory_info:
                    inventory_info['target_config_ids'] = []
                for c in t_cids:
                    if c not in inventory_info['target_config_ids']:
                        inventory_info['target_config_ids'].append(c)
                
                if sub_count:
                    total_sum += int(sub_count)
                else:
                    print(f"DEBUG: No count found for {f_url}")
            except Exception as e:
                print(f"Error fetching sub-inventory {f_url}: {e}")
                inventory_info['status'] = 'error'
                bugs.append({
                    'type': 'inventory_manual_review',
                    'description': f'M/D | Obs | Content | Could not read inventory page: {target_path}'
                })
                return bugs, inventory_info

        filter_count = str(total_sum)
        inventory_info['filter_count'] = filter_count
        
        # Robust comparison: handle None or non-integer counts
        curr_val = 0
        try:
            if current_count:
                curr_val = int(current_count)
        except: pass

        if curr_val == 0:
            # If no vehicles on page, it's an informational/content page or just missing widget
            inventory_info['status'] = 'no_local_widget'
        elif curr_val != total_sum:
            bugs.append(make_bug('inventory_mismatch', f"Inventory filter mismatch. Expected path: '{res}'"))
            inventory_info['status'] = 'mismatch'
            inventory_learner.confirm_correction(url, False)
        else:
            inventory_info['status'] = 'match'
            inventory_learner.confirm_correction(url, True)
            # --- Auto-Learning: Save successful match (only if no prior entry exists) ---
            existing_patterns = load_inventory_patterns()
            if not existing_patterns.get(domain, {}).get(raw_path):
                save_inventory_pattern(domain, raw_path, res)
            
    except Exception as e:
        import traceback
        print("Inventory validation critical error:")
        traceback.print_exc()
        inventory_info['status'] = 'error'
        inventory_info['error_detail'] = str(e)
    finally:
        if driver:
            try: driver.quit()
            except: pass
            
    return bugs, inventory_info


def is_placeholder_url(url_str: str) -> bool:
    if not url_str or not isinstance(url_str, str):
        return True
    low = url_str.lower()
    if low.startswith('data:image/'):
        return True
    placeholder_kws = ['blank.gif', 'spacer.gif', 'pixel.gif', 'transparent.png', '1x1', 'cleardot.gif', 'empty.gif', 'shimmer']
    return any(pk in low for pk in placeholder_kws)


def extract_real_img_src(img, base_url: str) -> str:
    """Extracts real non-placeholder image URL checking data-src, data-original, srcset, src, parent links, background styles, and widget contents."""
    if not img:
        return ''
    
    candidates = [
        img.get('data-src'),
        img.get('data-original'),
        img.get('data-lazy-src'),
        img.get('data-srcset'),
        img.get('data-bg'),
        img.get('srcset'),
        img.get('src')
    ]
    
    parent = img.parent
    if parent:
        candidates.extend([
            parent.get('data-src'),
            parent.get('data-original'),
            parent.get('data-lazy-src'),
            parent.get('data-bg'),
            parent.get('href') if parent.name == 'a' and any(ext in (parent.get('href') or '').lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']) else None
        ])
        
        import re as _re3
        for el in [img, parent, parent.parent if parent else None]:
            if el and el.get('style'):
                bg_m = _re3.search(r'url\(["\']?(https?://[^"\')\s]+|//[^"\')\s]+|/[^"\')\s]+)["\']?\)', el.get('style'))
                if bg_m:
                    candidates.append(bg_m.group(1))

    widget_ancestor = img.find_parent(lambda t: t.has_attr('data-widget-name') or t.has_attr('data-name'))
    if widget_ancestor:
        for other_img in widget_ancestor.find_all('img'):
            if other_img != img:
                candidates.extend([other_img.get('data-src'), other_img.get('data-original'), other_img.get('src')])

    real_src = ''
    for cand in candidates:
        if not cand: continue
        cand_str = str(cand).strip()
        
        # If srcset format (e.g. "url1 1x, url2 2x")
        if ',' in cand_str and (' 1x' in cand_str or ' 2x' in cand_str or 'w,' in cand_str):
            cand_str = cand_str.split(',')[0].strip().split()[0].strip()

        # Fix unencoded spaces in image URL path (e.g. "Automotive Brands")
        cand_url = cand_str.replace(' ', '%20')

        if cand_url and len(cand_url) > 5 and not is_placeholder_url(cand_url):
            real_src = cand_url
            break


    if real_src:
        if real_src.startswith('//'):
            real_src = 'https:' + real_src
        elif real_src.startswith('/'):
            from urllib.parse import urlparse as _urlparse
            _parsed = _urlparse(base_url)
            real_src = f"{_parsed.scheme}://{_parsed.netloc}{real_src}"

    return real_src




def consolidate_inventory_bugs(bugs: list, inventory_info: dict, custom_rules: str, url: str, soup, page_title: str, full_page_text: str) -> list:
    """
    Ensures that ONLY ONE inventory error bug is reported when inventory is wrong.
    Formats message as: 'Wrong Inventory Config, the inventory should looks like this: {filter_url}'
    Classifies severity as 'Critical' if:
      1. Explicit order in custom_rules is breached.
      2. New vs Used incoherence.
      3. Brand/Model/Facets mismatch (e.g. Ford F-150 vs Chevy Silverado).
    Otherwise severity is 'Failed'.
    """
    if not inventory_info:
        return bugs

    inv_status = inventory_info.get('status')
    filter_url = inventory_info.get('filter_url') or ''
    page_count = inventory_info.get('page_count')
    filter_count = inventory_info.get('filter_count')

    # Identify if there is an inventory bug in the current list
    inv_bug_indices = []
    is_custom_rules_inv_failure = False

    for idx, bug in enumerate(bugs):
        b_type = bug.get('bug_type', '')
        msg = bug.get('message', '').lower()

        is_inv_bug = (
            b_type in ('inventory_mismatch', 'inventory_manual_review') or
            'inventory filter mismatch' in msg or
            'inventory mismatch' in msg or
            'wrong inventory config' in msg or
            ('rule failed' in msg and any(k in msg for k in ['inventory', 'new vehicles', 'used vehicles', 'vehicles below', 'under', 'filter by']))
        )

        if is_inv_bug:
            inv_bug_indices.append(idx)
            if 'rule failed' in msg or (custom_rules and any(k in custom_rules.lower() for k in ['inventory', 'new vehicle', 'used vehicle', 'below', 'under', 'filter by'])):
                is_custom_rules_inv_failure = True

    # Check if inventory status is mismatch/error
    has_inv_mismatch = (inv_status in ['mismatch', 'error']) or (page_count is not None and filter_count is not None and str(page_count) != str(filter_count))

    if not inv_bug_indices and not has_inv_mismatch:
        return bugs

    # Determine Severity (Critical vs Failed)
    is_critical = False

    # Case A: Explicit order in custom_rules
    if is_custom_rules_inv_failure or (custom_rules and any(k in custom_rules.lower() for k in ['inventory', 'new vehicle', 'used vehicle', 'vehicles below', 'under', 'filter by'])):
        is_critical = True

    url_low = url.lower()
    title_low = page_title.lower() if page_title else ""
    filter_url_low = filter_url.lower()

    # Case B: New vs Used incoherence
    page_is_new = 'new' in url_low or 'new' in title_low or 'new-inventory' in url_low
    page_is_used = 'used' in url_low or 'pre-owned' in url_low or 'used' in title_low or 'used-inventory' in url_low

    filter_is_new = 'new-inventory' in filter_url_low or ('new' in filter_url_low and 'used' not in filter_url_low)
    filter_is_used = 'used-inventory' in filter_url_low or 'pre-owned' in filter_url_low or ('used' in filter_url_low and 'new' not in filter_url_low)

    if (page_is_new and filter_is_used) or (page_is_used and filter_is_new):
        is_critical = True

    # Case C: Brand / Model / Facets mismatch (e.g. Ford F-150 vs Chevy Silverado)
    page_brand = None
    for brand_key in ['ford', 'chevrolet', 'chevy', 'ram', 'dodge', 'jeep', 'chrysler', 'toyota', 'honda', 'nissan', 'gmc', 'buick', 'cadillac', 'hyundai', 'kia', 'subaru']:
        if brand_key in url_low or brand_key in title_low:
            page_brand = brand_key
            break

    target_brand = None
    for brand_key in ['ford', 'chevrolet', 'chevy', 'ram', 'dodge', 'jeep', 'chrysler', 'toyota', 'honda', 'nissan', 'gmc', 'buick', 'cadillac', 'hyundai', 'kia', 'subaru']:
        if brand_key in filter_url_low:
            target_brand = brand_key
            break

    if page_brand and target_brand and (page_brand != target_brand) and not (page_brand in ['chevrolet', 'chevy'] and target_brand in ['chevrolet', 'chevy']):
        is_critical = True

    # Check facets for competing models
    if soup:
        facet_text = ""
        for facet_el in soup.select('.facet-list, .srp-facets, .refine-inventory, [data-widget-name*="facet"], [data-widget-name*="refine"]'):
            facet_text += " " + facet_el.get_text(separator=' ', strip=True).lower()
        
        if facet_text:
            conflicting_models = {
                'f-150': ['silverado', 'sierra', 'ram 1500', 'tundra'],
                'silverado': ['f-150', 'sierra', 'ram 1500', 'tundra'],
                'ram 1500': ['f-150', 'silverado', 'sierra', 'tundra']
            }
            for m_key, bad_models in conflicting_models.items():
                if (m_key in url_low or m_key in title_low) and any(bm in facet_text for bm in bad_models):
                    is_critical = True
                    break

    # Construct single inventory bug message as requested by user
    single_message = f"Wrong Inventory Config, the inventory should look like this: {filter_url}" if filter_url else "Wrong Inventory Config."


    severity_type = 'Critical' if is_critical else 'Failed'

    single_bug = {
        'platform': 'D',
        'type': severity_type,
        'category': 'Config',
        'bug_type': 'inventory_mismatch',
        'message': single_message
    }

    # Filter out ALL old inventory bugs from the list, and insert the single consolidated bug
    new_bugs = [b for idx, b in enumerate(bugs) if idx not in inv_bug_indices]
    new_bugs.append(single_bug)

    return new_bugs




def run_page_audit(url: str, soup, response, response_time_ms: float) -> dict:
    """
    Runs a static-HTML page audit across 4 categories.
    No external APIs needed — pure Python + BeautifulSoup.
    
    Returns:
        {
          "score": int 0-100,
          "categories": {
            "performance": [...checks],
            "seo": [...checks],
            "accessibility": [...checks],
            "best_practices": [...checks],
          }
        }
    """
    import re as _re

    checks = {
        "performance": [],
        "seo": [],
        "accessibility": [],
        "best_practices": [],
    }

    def _check(category, name, status, message, detail=None):
        """status: 'pass' | 'warn' | 'fail'"""
        checks[category].append({
            "name": name,
            "status": status,
            "message": message,
            "detail": detail or "",
        })

    html = response.text
    page_size_kb = round(len(html.encode('utf-8')) / 1024, 1)
    
    # ══════════════════════════════════════════
    # PERFORMANCE
    # ══════════════════════════════════════════

    # Response time
    if response_time_ms < 800:
        _check("performance", "Response Time", "pass", f"Fast response: {response_time_ms:.0f} ms")
    elif response_time_ms < 2000:
        _check("performance", "Response Time", "warn", f"Moderate response time: {response_time_ms:.0f} ms. Consider server-side caching.")
    else:
        _check("performance", "Response Time", "fail", f"Slow response: {response_time_ms:.0f} ms. May hurt Core Web Vitals.")

    # Page size
    if page_size_kb < 500:
        _check("performance", "Page Size", "pass", f"Page HTML is {page_size_kb} KB — well optimised.")
    elif page_size_kb < 1500:
        _check("performance", "Page Size", "warn", f"Page HTML is {page_size_kb} KB — consider reducing inline CSS/JS.")
    else:
        _check("performance", "Page Size", "fail", f"Page HTML is {page_size_kb} KB — very large. Review inline scripts and styles.")

    # Render-blocking scripts in <head>
    head = soup.find('head')
    blocking_scripts = 0
    if head:
        for s in head.find_all('script', src=True):
            if not s.get('defer') and not s.get('async') and not s.get('type') == 'module':
                blocking_scripts += 1
    if blocking_scripts == 0:
        _check("performance", "Render-Blocking Scripts", "pass", "No render-blocking scripts detected in <head>.")
    elif blocking_scripts <= 3:
        _check("performance", "Render-Blocking Scripts", "warn", f"{blocking_scripts} render-blocking script(s) in <head> without defer/async. May delay page render.")
    else:
        _check("performance", "Render-Blocking Scripts", "fail", f"{blocking_scripts} render-blocking scripts in <head>. Add defer or async attributes.")

    # Images without lazy loading
    all_imgs = soup.find_all('img')
    imgs_without_lazy = [i for i in all_imgs if not i.get('loading') and not i.get('data-src')]
    # Ignore tracking pixels and very small images
    real_imgs_without_lazy = [i for i in imgs_without_lazy if i.get('src', '').startswith(('http', '//')) and i.get('src', '') != '']
    if len(real_imgs_without_lazy) == 0:
        _check("performance", "Lazy Loading", "pass", "All images have lazy loading or are deferred.")
    elif len(real_imgs_without_lazy) <= 3:
        _check("performance", "Lazy Loading", "warn", f"{len(real_imgs_without_lazy)} image(s) missing loading='lazy'. May delay initial render on slower connections.")
    else:
        _check("performance", "Lazy Loading", "fail", f"{len(real_imgs_without_lazy)} images missing loading='lazy'. Add this attribute to off-screen images.")

    # Images without explicit width/height (CLS risk)
    imgs_no_dims = [i for i in all_imgs if (not i.get('width') and not i.get('height')) and i.get('src', '').startswith(('http', '//'))]
    if len(imgs_no_dims) == 0:
        _check("performance", "Image Dimensions (CLS)", "pass", "All images have explicit width/height — good for layout stability.")
    elif len(imgs_no_dims) <= 4:
        _check("performance", "Image Dimensions (CLS)", "warn", f"{len(imgs_no_dims)} image(s) lack explicit width/height. May cause Cumulative Layout Shift (CLS).", detail=f"Count: {len(imgs_no_dims)}")
    else:
        _check("performance", "Image Dimensions (CLS)", "fail", f"{len(imgs_no_dims)} images lack width/height. CLS issue — could hurt Core Web Vitals score.")

    # ══════════════════════════════════════════
    # SEO
    # ══════════════════════════════════════════

    # Title tag
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        t = title_tag.string.strip()
        tlen = len(t)
        if 30 <= tlen <= 65:
            _check("seo", "Title Tag", "pass", f"Title tag is {tlen} chars — optimal length.", detail=t[:70])
        elif tlen < 30:
            _check("seo", "Title Tag", "warn", f"Title tag is only {tlen} chars — too short. Aim for 30-65 chars.", detail=t[:70])
        else:
            _check("seo", "Title Tag", "warn", f"Title tag is {tlen} chars — may be truncated in SERPs. Aim for 30-65 chars.", detail=t[:70])
    else:
        _check("seo", "Title Tag", "fail", "No <title> tag found. Required for SEO.")

    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        desc = meta_desc['content'].strip()
        dlen = len(desc)
        if 50 <= dlen <= 160:
            _check("seo", "Meta Description", "pass", f"Meta description is {dlen} chars — good length.", detail=desc[:100])
        elif dlen < 50:
            _check("seo", "Meta Description", "warn", f"Meta description too short ({dlen} chars). Aim for 50-160 chars.", detail=desc[:100])
        else:
            _check("seo", "Meta Description", "warn", f"Meta description too long ({dlen} chars) — may be truncated in SERPs.", detail=desc[:100])
    else:
        _check("seo", "Meta Description", "fail", "No meta description found. Important for click-through rates in search results.")

    # Canonical tag
    canonical = soup.find('link', attrs={'rel': 'canonical'})
    if canonical and canonical.get('href'):
        _check("seo", "Canonical Tag", "pass", f"Canonical tag present.", detail=canonical['href'][:80])
    else:
        _check("seo", "Canonical Tag", "warn", "No canonical tag found. Consider adding one to prevent duplicate content issues.")

    # Open Graph tags
    og_title = soup.find('meta', attrs={'property': 'og:title'})
    og_desc  = soup.find('meta', attrs={'property': 'og:description'})
    og_image = soup.find('meta', attrs={'property': 'og:image'})
    og_count = sum(1 for x in [og_title, og_desc, og_image] if x)
    if og_count == 3:
        _check("seo", "Open Graph Tags", "pass", "og:title, og:description and og:image are all present.")
    elif og_count > 0:
        missing = [n for n, x in [('og:title', og_title), ('og:description', og_desc), ('og:image', og_image)] if not x]
        _check("seo", "Open Graph Tags", "warn", f"Some OG tags missing: {', '.join(missing)}. Important for social media sharing.")
    else:
        _check("seo", "Open Graph Tags", "warn", "No Open Graph tags found. Recommended for rich social media previews.")

    # H1 count (basic check)
    h1s = soup.find_all('h1')
    if len(h1s) == 1:
        _check("seo", "H1 Tag", "pass", "Exactly one H1 tag found — correct structure.")
    elif len(h1s) == 0:
        _check("seo", "H1 Tag", "fail", "No H1 tag found. Every page should have exactly one H1.")
    else:
        _check("seo", "H1 Tag", "warn", f"{len(h1s)} H1 tags found. Best practice is one H1 per page.")

    # Robots meta
    robots_meta = soup.find('meta', attrs={'name': 'robots'})
    if robots_meta:
        content = (robots_meta.get('content') or '').lower()
        if 'noindex' in content:
            _check("seo", "Robots Meta", "fail", f"Page is set to NOINDEX. Search engines will not index this page.", detail=content)
        else:
            _check("seo", "Robots Meta", "pass", f"Robots meta present and indexable.", detail=content)
    else:
        _check("seo", "Robots Meta", "pass", "No robots meta tag — page is indexable by default.")

    # Breadcrumbs
    has_schema = bool(soup.find(attrs={'itemtype': _re.compile(r'BreadcrumbList', _re.I)}))
    has_class = bool(soup.select('.breadcrumb, .breadcrumbs, [class*="breadcrumb"], .ws-breadcrumbs'))
    if has_schema or has_class:
        _check("seo", "Breadcrumbs", "pass", "Breadcrumbs detected (Schema.org or Semantic classes).")
    else:
        _check("seo", "Breadcrumbs", "warn", "No breadcrumbs detected. Consider adding them for better UX and SEO crawlability.")

    # ══════════════════════════════════════════
    # ACCESSIBILITY
    # ══════════════════════════════════════════

    # Lang attribute
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        _check("accessibility", "Language Attribute", "pass", f"<html lang='{html_tag['lang']}'> is set correctly.")
    else:
        _check("accessibility", "Language Attribute", "fail", "Missing lang attribute on <html>. Required for screen readers.")

    # Images missing alt text
    imgs_no_alt = [i for i in all_imgs if i.get('alt') is None and not i.get('role') == 'presentation' and not i.get('hidden')]
    # Filter out tracking pixels
    real_imgs_no_alt = [i for i in imgs_no_alt if i.get('src', '').startswith(('http', '//'))]
    if len(real_imgs_no_alt) == 0:
        _check("accessibility", "Image Alt Text", "pass", "All visible images have alt text.")
    elif len(real_imgs_no_alt) <= 3:
        _check("accessibility", "Image Alt Text", "warn", f"{len(real_imgs_no_alt)} image(s) missing alt text. Add descriptive alt attributes.")
    else:
        _check("accessibility", "Image Alt Text", "fail", f"{len(real_imgs_no_alt)} images missing alt text. This is a critical accessibility issue.")

    # Heading hierarchy (no H3 before H2, etc.)
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    heading_levels = [int(h.name[1]) for h in headings]
    heading_jump = False
    for i in range(1, len(heading_levels)):
        if heading_levels[i] > heading_levels[i-1] + 1:
            heading_jump = True
            break
    if not heading_jump:
        _check("accessibility", "Heading Hierarchy", "pass", "Heading levels flow correctly without skipping levels.")
    else:
        _check("accessibility", "Heading Hierarchy", "warn", "Heading levels skip (e.g. H2 → H4 without H3). This may confuse screen readers.")

    # ARIA landmarks (main, nav)
    has_main = bool(soup.find('main') or soup.find(attrs={'role': 'main'}))
    has_nav  = bool(soup.find('nav')  or soup.find(attrs={'role': 'navigation'}))
    if has_main and has_nav:
        _check("accessibility", "ARIA Landmarks", "pass", "<main> and <nav> landmark elements found.")
    elif has_main or has_nav:
        _check("accessibility", "ARIA Landmarks", "warn", "Only partial ARIA landmarks. Both <main> and <nav> are recommended.")
    else:
        _check("accessibility", "ARIA Landmarks", "warn", "No ARIA landmark elements (<main>, <nav>) found. Helps screen reader navigation.")

    # Form labels
    inputs = soup.find_all('input', {'type': lambda t: t not in ['hidden', 'submit', 'button', None]})
    unlabelled = 0
    for inp in inputs:
        inp_id = inp.get('id')
        has_label = bool(inp.get('aria-label') or inp.get('aria-labelledby') or inp.get('placeholder'))
        if not has_label and inp_id:
            has_label = bool(soup.find('label', attrs={'for': inp_id}))
        if not has_label:
            unlabelled += 1
    if unlabelled == 0:
        _check("accessibility", "Form Labels", "pass", "All form inputs appear to have labels or aria-labels.")
    else:
        _check("accessibility", "Form Labels", "warn", f"{unlabelled} form input(s) may be missing labels. Add <label> or aria-label.")

    # ══════════════════════════════════════════
    # BEST PRACTICES
    # ══════════════════════════════════════════

    # HTTPS
    if url.startswith('https://'):
        _check("best_practices", "HTTPS", "pass", "Page is served over HTTPS.")
    else:
        _check("best_practices", "HTTPS", "fail", "Page is served over HTTP. HTTPS is required for security and SEO.")

    # Viewport meta
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if viewport and 'width' in (viewport.get('content') or ''):
        _check("best_practices", "Viewport Meta", "pass", "Viewport meta tag is present — mobile responsive.", detail=viewport.get('content', ''))
    else:
        _check("best_practices", "Viewport Meta", "fail", "No viewport meta tag. Page may not render correctly on mobile.")

    # Charset
    charset_tag = soup.find('meta', charset=True) or soup.find('meta', attrs={'http-equiv': 'Content-Type'})
    if charset_tag:
        _check("best_practices", "Charset Declaration", "pass", "Charset is declared.")
    else:
        _check("best_practices", "Charset Declaration", "warn", "No charset meta tag found. Browsers may misinterpret character encoding.")

    # Favicon
    favicon = soup.find('link', attrs={'rel': lambda r: r and 'icon' in str(r).lower()})
    if favicon:
        _check("best_practices", "Favicon", "pass", "Favicon link tag found.")
    else:
        _check("best_practices", "Favicon", "warn", "No favicon found. Recommended for brand recognition.")

    # Inline styles overuse
    inline_style_count = len(soup.find_all(style=True))
    if inline_style_count < 20:
        _check("best_practices", "Inline Styles", "pass", f"Minimal inline styles ({inline_style_count} elements). Good separation of concerns.")
    elif inline_style_count < 60:
        _check("best_practices", "Inline Styles", "warn", f"{inline_style_count} elements use inline styles. Consider moving to external CSS.")
    else:
        _check("best_practices", "Inline Styles", "fail", f"{inline_style_count} elements use inline styles. Heavy inline styling reduces maintainability and caching.")

    # External scripts count
    external_scripts = soup.find_all('script', src=True)
    ext_count = len(external_scripts)
    if ext_count <= 8:
        _check("best_practices", "External Scripts", "pass", f"{ext_count} external scripts — manageable count.")
    elif ext_count <= 20:
        _check("best_practices", "External Scripts", "warn", f"{ext_count} external scripts. Many HTTP requests can slow page load.")
    else:
        _check("best_practices", "External Scripts", "fail", f"{ext_count} external scripts. Consider bundling or deferring non-critical scripts.")

    # Calculate overall score
    all_checks = [c for cats in checks.values() for c in cats]
    total = len(all_checks)
    passes = sum(1 for c in all_checks if c['status'] == 'pass')
    warns  = sum(1 for c in all_checks if c['status'] == 'warn')
    # Score: pass=full, warn=half, fail=0
    score = round(((passes + warns * 0.5) / total) * 100) if total else 0

    return {
        "score": score,
        "total_checks": total,
        "passes": passes,
        "warns": warns,
        "fails": total - passes - warns,
        "categories": checks
    }


def verify_custom_rules(custom_rules_text: str, soup, inventory_info: dict) -> list:
    """
    Evaluates layout and inventory configuration rules provided in the Custom Rules field.
    Returns a list of evaluation dicts: {'original': text, 'status': 'success'|'error'|'manual_review', 'found_text': optional detail}
    """
    if not custom_rules_text: return []
    evaluations = []
    
    # Split by newlines, bullet points, or semicolons/sentence endings (preserving numbers like $30,000)
    import re
    cleaned = custom_rules_text.replace('•', '\n')
    # Split on newlines, bullets, or semicolons, or sentence periods followed by a capital letter (not inside numbers)
    raw_lines = re.split(r'[\n;]|(?<=[a-zA-Z])\.\s+(?=[A-Z])', cleaned)
    lines = []
    for l in raw_lines:
        line_str = l.strip()
        if len(line_str) > 2:
            lines.append(line_str)
    if not lines:
        lines = [custom_rules_text.strip()]
    
    for rule in lines:
        rule_lower = rule.lower()
        res = {'original': rule, 'status': 'error', 'found_text': ''}
        
        # 1. Breadcrumbs
        if 'breadcrumb' in rule_lower:
            has_schema = bool(soup.find(attrs={'itemtype': lambda x: x and 'BreadcrumbList' in x})) if soup else False
            has_class = bool(soup.find(attrs={'class': lambda x: x and 'breadcrumb' in x.lower()})) if soup else False
            has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'breadcrumb' in x.lower()})) if soup else False
            if has_schema or has_class or has_widget:
                res['status'] = 'success'
                res['found_text'] = 'Breadcrumbs component found on page.'
            else:
                res['status'] = 'error'
                
        # 2. Hero Image
        elif 'hero image' in rule_lower or 'hero' in rule_lower:
            has_hero = bool(soup.find(attrs={'class': lambda x: x and 'hero' in x.lower()})) if soup else False
            has_hero_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'hero' in x.lower()})) if soup else False
            if has_hero or has_hero_widget:
                res['status'] = 'success'
                res['found_text'] = 'Hero component detected via classes/widgets.'
            else:
                res['status'] = 'manual_review'

        # 3. Content w/ Image Right/Left or Imagery / Images
        elif 'imagery' in rule_lower or 'images' in rule_lower:
            has_imgs = bool(soup.find_all('img')) if soup else False
            if has_imgs:
                res['status'] = 'success'
                res['found_text'] = 'Content sections containing images/imagery detected.'
            else:
                res['status'] = 'manual_review'
                res['found_text'] = 'Verify image content in page sections.'

        elif 'content w/ image' in rule_lower or 'content with image' in rule_lower:
            has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and ('content-image' in x.lower() or 'content with image' in x.lower())})) if soup else False
            if has_widget:
                res['status'] = 'success'
                res['found_text'] = 'Content w/ Image widget detected.'
            else:
                res['status'] = 'error'
                
        # 4. Accordion / FAQ
        elif 'accordion' in rule_lower or 'faq' in rule_lower:
            has_acc = bool(soup.find(attrs={'class': lambda x: x and 'accordion' in x.lower()})) if soup else False
            has_faq_widget = bool(soup.find(attrs={'class': lambda x: x and 'faq' in x.lower()})) if soup else False
            
            # Check for plain HTML FAQ headers (e.g. <h2>Frequently Asked Questions</h2>)
            has_faq_header = False
            if soup:
                for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    h_txt = h.get_text().lower()
                    if any(kw in h_txt for kw in ['faq', 'frequently asked questions', 'questions about', 'common questions']):
                        has_faq_header = True
                        break

            if 'accordion' in rule_lower:
                if has_acc:
                    res['status'] = 'success'
                    res['found_text'] = 'Accordion widget detected for FAQ section.'
                elif has_faq_widget or has_faq_header:
                    res['status'] = 'manual_review'
                    res['found_text'] = 'FAQ section found as plain text/HTML, but requested specifically as accordion widget.'
                else:
                    res['status'] = 'error'
                    res['found_text'] = 'No Accordion or FAQ section found.'
            else:
                if has_acc or has_faq_widget or has_faq_header:
                    res['status'] = 'success'
                    res['found_text'] = 'FAQ section detected (Accordion or HTML text).'
                else:
                    res['status'] = 'error'
                    res['found_text'] = 'No FAQ section found.'

        # 5. Lead / Contact Form
        elif 'form' in rule_lower or 'lead' in rule_lower or 'contact' in rule_lower:
            has_form = bool(soup.find('form')) if soup else False
            has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and ('form' in x.lower() or 'lead' in x.lower() or 'contact' in x.lower())})) if soup else False
            has_class = bool(soup.find(attrs={'class': lambda x: x and ('form' in x.lower() or 'lead' in x.lower() or 'contact' in x.lower())})) if soup else False
            if has_form or has_widget or has_class:
                res['status'] = 'success'
                res['found_text'] = 'Lead/Contact form detected on page.'
            else:
                res['status'] = 'error'
                res['found_text'] = 'No Lead/Contact form found on page.'

        # 6. Inventory Config
        elif 'inventory' in rule_lower or 'vehicle' in rule_lower or 'under' in rule_lower or 'below' in rule_lower or '$' in rule_lower:
            if inventory_info:
                p_cnt = inventory_info.get('page_count')
                f_cnt = inventory_info.get('filter_count')
                inv_status = inventory_info.get('status')
                inferred_url = inventory_info.get('filter_url') or ''

                is_mismatch = (inv_status == 'mismatch') or (p_cnt is not None and f_cnt is not None and str(p_cnt) != str(f_cnt))
                if is_mismatch:
                    res['status'] = 'error'
                    res['found_text'] = f"Inventory Mismatch: Current page shows {p_cnt} vehicles, but requested target filter ({inferred_url}) has {f_cnt} vehicles."
                else:

                    inferred_url_low = inferred_url.lower()
                    pr_m = re.search(r'(\d{2,3})[,\.]?(\d{3})', rule_lower)
                    req_price = None
                    if pr_m:
                        req_price = pr_m.group(1) + pr_m.group(2)
                    else:
                        pr_k = re.search(r'\$?(\d{1,3})\s*k', rule_lower)
                        if pr_k:
                            req_price = str(int(pr_k.group(1)) * 1000)

                    match_price = True
                    if req_price:
                        match_price = (req_price in inferred_url_low or f"1-{req_price}" in inferred_url_low or f"0-{req_price}" in inferred_url_low)

                    req_new = any(kw in rule_lower for kw in ['new', 'nuevos'])
                    req_used = any(kw in rule_lower for kw in ['used', 'pre-owned', 'preowned', 'usados'])

                    match_type = True
                    if req_new:
                        match_type = ('new-inventory' in inferred_url_low or 'new' in inferred_url_low)
                    elif req_used:
                        match_type = ('used-inventory' in inferred_url_low or 'used' in inferred_url_low)

                    if match_price and match_type:
                        res['status'] = 'success'
                        res['found_text'] = f"Inventory filter matches requested config ({inferred_url})."
                    else:
                        res['status'] = 'error'
                        res['found_text'] = f"Filter mismatch: Expected config matching rule, but found {inferred_url or 'generic inventory'}."
            else:
                res['status'] = 'manual_review'

                
        # 7. Grid / List Layout
        elif 'grid' in rule_lower or 'list' in rule_lower:
            want_grid = 'grid' in rule_lower
            want_list = 'list' in rule_lower
            actual_layout = inventory_info.get('layout', 'Unknown') if inventory_info else 'Unknown'
            
            if want_grid and (actual_layout == 'Grid' or actual_layout == 'Unknown'):
                res['status'] = 'success'
                res['found_text'] = 'Inventory layout set to Grid view.'
            elif want_list and actual_layout == 'List':
                res['status'] = 'success'
                res['found_text'] = 'Inventory layout set to List view.'
            elif want_grid and actual_layout != 'Grid' and actual_layout != 'Unknown':
                res['status'] = 'error'
                res['found_text'] = f"Requested Grid view, but found {actual_layout} view."
            elif want_list and actual_layout != 'List' and actual_layout != 'Unknown':
                res['status'] = 'error'
                res['found_text'] = f"Requested List view, but found {actual_layout} view."
            else:
                res['status'] = 'manual_review'
                
        else:
            res['status'] = 'manual_review'
            
        evaluations.append(res)
        
    return evaluations


def run_media_audit(url, html_raw, soup):
    """
    Analyzes content images to ensure they are hosted in the dealer's pictures.dealer.com account.
    """
    media_audit = {'status': 'skipped', 'dealer_id': None, 'offending_images': [], 'analyzed_images': [], 'bugs': []}
    try:
        import re as _re2
        from urllib.parse import urljoin
        
        # 1. Auto-detect dealer account ID (3 reliable signals)
        dealer_id = None
        
        # Signal A: "accountId":"..." in scripts (Most reliable explicit config)
        _ids_a = _re2.findall(r'"accountId"\s*:\s*"([^"]+)"', html_raw)
        if _ids_a:
            dealer_id = _ids_a[0]

        # Signal B: data-account-id attribute (Very reliable explicit config)
        if not dealer_id:
            _ids_b = _re2.findall(r'data-account-id=["\']([^"\']+)["\']', html_raw)
            if _ids_b:
                dealer_id = _ids_b[0]
                
        # Signal C: pictures.dealer.com/{letter}/{id}/ (Fallback inference)
        if not dealer_id:
            _ids_c = _re2.findall(r'pictures\.dealer\.com/[a-z]/([^/"\'&\s>]+)/', html_raw)
            if _ids_c:
                # Exclude known shared OEM asset directories if possible
                _ids_c = [i for i in _ids_c if i.lower() not in ['mnao', 'global', 'shared']]
                if _ids_c:
                    dealer_id = max(set(_ids_c), key=_ids_c.count)

        if dealer_id:
            media_audit['dealer_id'] = dealer_id
            print(f"DEBUG: Media Audit - dealer_id detected: {dealer_id}")

            # 2. Widgets to EXCLUDE from image audit
            MEDIA_SKIP_WIDGETS = [
                'ws-inv-', 'inventory-listing', 'inventory-search',
                'ws-specials', 'specials-listing', 'specials-widget',
                'navigation', 'ws-navigation', 'header-default',
            ]

            def _is_excluded_widget(tag):
                """Returns True if the tag is inside an excluded widget."""
                p = tag
                while p:
                    wn = p.get('data-widget-name', p.get('data-widget-id', p.get('data-name', ''))) or ''
                    wn = wn.lower()
                    if any(skip in wn for skip in MEDIA_SKIP_WIDGETS):
                        return True
                    # Also skip nav and header tags
                    if p.name in ['nav', 'header']:
                        return True
                    p = p.parent
                return False

            def _extract_img_srcs(tag):
                """Extract all image URLs from an element (img src, data-src, background-image CSS)."""
                srcs = set()
                src = tag.get('src', '')
                if src and not src.startswith('data:') and len(src) > 5:
                    srcs.add(src)
                data_src = tag.get('data-src', '')
                if data_src and not data_src.startswith('data:') and len(data_src) > 5:
                    srcs.add(data_src)
                # background-image in inline style
                style = tag.get('style', '')
                bg_urls = _re2.findall(r'url\(["\']?(https?://[^"\')\s]+|//[^"\')\s]+)["\']?\)', style)
                for bg in bg_urls:
                    if not bg.startswith('data:'):
                        srcs.add(bg)
                # data-responsive-image-bg
                bg2 = tag.get('data-bg', '') or tag.get('data-lazy-src', '')
                if bg2 and not bg2.startswith('data:'):
                    srcs.add(bg2)
                return srcs

            offending = []
            analyzed_images = []

            # Scan all img tags
            for img_tag in soup.find_all('img'):
                if _is_excluded_widget(img_tag):
                    continue
                img_classes = img_tag.get('class') or []
                if any(c in img_classes for c in ['ddc-loader']):
                    continue
                    
                widget_name = (img_tag.get('data-widget-name') or 
                               img_tag.parent.get('data-widget-name') or 
                               img_tag.parent.get('data-name') or 'Unknown widget')
                               
                for src in _extract_img_srcs(img_tag):
                    if src and not src.startswith('data:'):
                        # Skip 1x1 tracking pixels or hidden images
                        w = img_tag.get('width', '')
                        h = img_tag.get('height', '')
                        if (w == '1' and h == '1') or 'facebook.com/tr' in src or 'googleadservices.com' in src:
                            continue
                            
                        clean_src = src.split('?')[0]
                        # Skip provider logos (e.g. DDC white logo) that aren't dealer content
                        if '.svg' in clean_src.lower() and 'logo' in clean_src.lower():
                            continue
                            
                        full_src = urljoin(url, clean_src)
                        analyzed_images.append({'src': full_src, 'type': 'img', 'widget': widget_name})
                        
                    # Only check pictures.dealer.com images — skip other CDNs and local paths
                    if 'pictures.dealer.com' in src or 'dealer.com' in src:
                        src_lower = src.lower()
                        if 'dbcreative' in src_lower or 'automotive brands' in src_lower or 'automotive%20brands' in src_lower or 'dealer.com/ddc/' in src_lower or 'static.dealer.com' in src_lower or 'ad-choices' in src_lower:
                            # Skip OEM brand images, static third-party logos (like ad-choices), and default DDC stock images which are not dealer-specific media library content
                            pass
                        elif dealer_id not in src:
                            offending.append({
                                'src': src.split('?')[0],  # strip query params for display
                                'type': 'img',
                                'widget': widget_name
                            })

            # Scan all elements with background-image inline styles
            for el in soup.find_all(style=_re2.compile(r'pictures\.dealer\.com', _re2.I)):
                if _is_excluded_widget(el):
                    continue
                wn = el.get('data-name', el.get('data-widget-name', el.get('data-widget-id', 'Background element')))
                for src in _extract_img_srcs(el):
                    if src and not src.startswith('data:'):
                        analyzed_images.append({'src': src.split('?')[0], 'type': 'background', 'widget': wn})
                        
                    if 'pictures.dealer.com' in src or 'dealer.com' in src:
                        src_lower = src.lower()
                        if 'dbcreative' in src_lower or 'automotive brands' in src_lower or 'automotive%20brands' in src_lower or 'dealer.com/ddc/' in src_lower:
                            # Skip OEM brand images and default DDC stock images which are not dealer-specific media library content
                            pass
                        elif dealer_id not in src:
                            offending.append({
                                'src': src.split('?')[0],
                                'type': 'background',
                                'widget': wn
                            })

            # Deduplicate
            seen_srcs = set()
            unique_offending = []
            for o in offending:
                if o['src'] not in seen_srcs:
                    seen_srcs.add(o['src'])
                    unique_offending.append(o)
                    
            seen_analyzed = set()
            unique_analyzed = []
            for a in analyzed_images:
                if a['src'] not in seen_analyzed:
                    seen_analyzed.add(a['src'])
                    unique_analyzed.append(a)

            media_audit['offending_images'] = unique_offending
            media_audit['analyzed_images'] = unique_analyzed
            media_audit['status'] = 'pass' if not unique_offending else 'fail'
            
            if unique_offending:
                for off in unique_offending:
                    off_src = off['src']
                    if off_src.startswith('//'): off_src = 'https:' + off_src
                    media_audit['bugs'].append({
                        'platform': 'D/M',
                        'type': 'Observed',
                        'category': 'Styling',
                        'bug_type': 'img_not_in_library',
                        'message': f"Image '{off_src}' is not in the Dealer's Media Library. Please review and re-upload if needed.",
                        'screenshot_link': off_src,
                        'img': off_src
                    })

                
            print(f"DEBUG: Media Audit - {len(unique_offending)} offending images found out of {len(unique_analyzed)} analyzed.")
        else:
            media_audit['status'] = 'no_id'
            print("DEBUG: Media Audit - could not detect dealer_id, skipping audit")
    except Exception as e:
        print(f"Media Audit Error: {e}")
        media_audit['status'] = 'error'
        
    return media_audit

def validate_sitemap(url: str) -> dict:
    """
    Validates whether the given page URL is listed in:
      1. The XML sitemap  (/sitemap.xml)  — checks for a <loc> matching the full URL.
         Handles sitemap indexes automatically by fetching nested sitemaps.
      2. The HTML sitemap (/sitemap.htm) — checks for an <a href> containing the page path.
         Falls back to other sitemap URLs if sitemap.htm is not found.

    Returns a dict with keys:
        xml_found   : bool | None
        xml_url     : str  (the sitemap XML URL checked)
        html_found  : bool | None
        html_url    : str  (the sitemap HTML URL checked)
        error       : str | None
    """
    info = {
        'xml_found': None,
        'xml_url': None,
        'html_found': None,
        'html_url': None,
        'error': None,
    }
    try:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        page_path = parsed.path.rstrip('/')
        page_full_url = f"{base}{parsed.path}"  # without query / fragment

        # ── 1. XML Sitemap ─────────────────────────────────────────────────────
        # Sub-sitemaps fetcher helper
        def check_xml_sitemap_text(xml_text, target):
            # Extract all <loc> URLs from the sitemap
            loc_urls = re.findall(r'<loc>\s*(.*?)\s*</loc>', xml_text, re.IGNORECASE)
            # Normalize target URL: remove scheme, www, trailing slash, and lowercase
            norm_target = re.sub(r'^https?://(www\.)?', '', target.lower()).rstrip('/')
            for loc in loc_urls:
                # Normalize each loc similarly
                norm_loc = re.sub(r'^https?://(www\.)?', '', loc.lower()).rstrip('/')
                if norm_loc == norm_target:
                    return True
            return False

        canonical_xml_url = f"{base}/sitemap.xml"
        info['xml_url'] = canonical_xml_url  # Always show the standard URL to the user

        xml_candidates = [
            canonical_xml_url,
            f"{base.replace('http://', 'https://')}/sitemap.xml",
            f"{base.replace('https://', 'https://www.')}/sitemap.xml" if 'www.' not in base else None,
            f"{base}/sitemap_index.xml"
        ]
        xml_candidates = [c for c in xml_candidates if c]  # remove None
        xml_candidates = list(dict.fromkeys(xml_candidates))  # remove duplicates
        xml_found = False

        # Iterate over possible XML sitemap URLs until one succeeds
        for candidate in xml_candidates:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                xml_resp = requests.get(candidate, impersonate='chrome', timeout=15, headers=headers, verify=False)
                if xml_resp.status_code == 200:
                    xml_text = xml_resp.text
                    # Check for sitemap index
                    sitemap_locs = re.findall(r'<sitemap>.*?<loc>\s*(.*?)\s*</loc>.*?</sitemap>', xml_text, re.DOTALL | re.IGNORECASE)
                    if sitemap_locs:
                        # Prioritize sub-sitemaps containing relevant keywords
                        keywords = ['page', 'inventory', 'detail', 'vehicle', 'new', 'used', 'sitemap']
                        prioritized = []
                        others = []
                        for loc in sitemap_locs:
                            low = loc.lower()
                            if any(k in low for k in keywords):
                                prioritized.append(loc)
                            else:
                                others.append(loc)
                        sub_sitemaps = (prioritized + others)[:8]
                        # Scan sub-sitemaps concurrently
                        def scan_sub(url):
                            try:
                                r = requests.get(url, impersonate='chrome', timeout=10, headers=headers, verify=False)
                                if r.status_code == 200:
                                    return check_xml_sitemap_text(r.text, page_full_url)
                            except Exception as e:
                                print(f"DEBUG: Failed to fetch sub-sitemap {url}: {e}")
                            return False
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            futures = {executor.submit(scan_sub, s): s for s in sub_sitemaps}
                            for fut in as_completed(futures):
                                if fut.result():
                                    xml_found = True
                                    break
                        if xml_found:
                            break
                    else:
                        # Simple XML sitemap
                        xml_found = check_xml_sitemap_text(xml_text, page_full_url)
                        if xml_found:
                            break
                else:
                    print(f"DEBUG: XML sitemap {candidate} returned status {xml_resp.status_code}")
            except Exception as e:
                print(f"DEBUG: Error fetching XML sitemap {candidate}: {e}")
        info['xml_found'] = xml_found


        # ── 2. HTML Sitemap ────────────────────────────────────────────────────
        # Common HTML sitemap URLs
        html_urls = [
            f"{base}/sitemap.htm",
            f"{base}/sitemap.html",
            f"{base}/sitemap/",
            f"{base}/sitemap/index.htm",
            f"{base}/sitemap/index.html"
        ]
        
        html_found = False
        html_url_used = html_urls[0]
        
        for candidate_url in html_urls:
            try:
                html_resp = requests.get(candidate_url, impersonate='chrome', timeout=15, verify=False)
                if html_resp.status_code == 200:
                    html_url_used = candidate_url
                    sm_soup = BeautifulSoup(html_resp.text, 'html.parser')
                    target_path_norm = page_path.lower().rstrip('/')
                    
                    for a in sm_soup.find_all('a', href=True):
                        href = a['href'].strip()
                        href_path = urlparse(href).path.lower().rstrip('/')
                        if href_path == target_path_norm:
                            html_found = True
                            break
                    
                    if html_found:
                        break
            except Exception as he:
                print(f"DEBUG: HTML sitemap fetch failed for {candidate_url}: {he}")
                
        info['html_url'] = html_url_used
        info['html_found'] = html_found

    except Exception as e:
        info['error'] = f'Sitemap validation error: {e}'

    return info


def check_lead_form_source(soup, page_title: str, h1_text: str = '') -> dict:
    """
    Detects if the page has a lead form (any <form> element with a submit button or input).
    If found, looks for the hidden 'source' input and validates its value.
    
    Returns:
        {
            'has_form': bool,
            'source_value': str | None,     # raw value found in the hidden input
            'status': 'ok' | 'wrong' | 'missing' | 'no_form',
            'expected': str | None,          # what the value should ideally be
        }
    """
    result = {
        'has_form': False,
        'source_value': None,
        'status': 'no_form',
        'expected': None,
    }
    
    try:
        # Consider any non-trivial form (has at least one input or button)
        forms = soup.find_all('form')
        real_forms = []
        for f in forms:
            # Skip search bar / nav forms (usually have no hidden source)
            if f.find(['input', 'textarea', 'select']) and (
                f.find('input', {'type': 'hidden', 'name': 'source'}) or
                f.find('input', {'name': 'source'}) or
                f.find('button', {'type': 'submit'}) or
                f.find('input', {'type': 'submit'})
            ):
                real_forms.append(f)
        
        if not real_forms:
            # Try any form at all that has inputs as a fallback
            real_forms = [f for f in forms if f.find('input')]
        
        if not real_forms:
            result['status'] = 'no_form'
            return result
        
        result['has_form'] = True
        
        # Find the hidden 'source' input across all found forms
        source_input = None
        for f in real_forms:
            src = f.find('input', {'name': 'source'})
            if src:
                source_input = src
                break
        
        if not source_input:
            result['status'] = 'missing'
            return result
        
        source_value = (source_input.get('value') or '').strip()
        result['source_value'] = source_value
        
        # Build the expected ideal value
        SUFFIX = 'Dealer.Com Website'
        title_clean = page_title.strip() if page_title else ''
        if title_clean:
            result['expected'] = f"{title_clean} - {SUFFIX}"
        else:
            result['expected'] = SUFFIX
        
        # Validate:
        import difflib
        
        source_val_low = source_value.lower()
        title_clean_low = title_clean.lower()
        
        is_match = False
        
        # 1. Must contain the suffix
        if SUFFIX.lower() in source_val_low:
            # 2. Extract the title part from the source
            source_title = source_val_low.replace(f"- {SUFFIX.lower()}", "").replace(SUFFIX.lower(), "").strip()
            
            # Remove common separators from actual page title to get the core part
            core_title = title_clean_low.split('|')[0].strip()
            core_title = core_title.split('-')[0].strip()
            
            core_h1 = h1_text.lower().strip() if h1_text else ''
            
            # Fuzzy match: 
            # - If source title is in page title or vice versa
            if source_title and (source_title in title_clean_low or core_title in source_title or (core_h1 and (source_title in core_h1 or core_h1 in source_title))):
                is_match = True
            else:
                import re
                def get_words(text):
                    return set(re.sub(r'[^a-z0-9\s]', '', text).split())
                
                src_words = get_words(source_title)
                core_words = get_words(title_clean_low)
                h1_words = get_words(core_h1) if core_h1 else set()
                
                if src_words:
                    match_title = len(src_words.intersection(core_words)) / len(src_words) >= 0.85
                    match_h1 = len(src_words.intersection(h1_words)) / len(src_words) >= 0.85 if h1_words else False
                    if match_title or match_h1:
                        is_match = True
                        
                if not is_match:
                    # - Or if sequence matcher ratio is high enough (>0.85)
                    ratio1 = difflib.SequenceMatcher(None, source_title, core_title).ratio()
                    ratio2 = difflib.SequenceMatcher(None, source_title, core_h1).ratio() if core_h1 else 0
                    if max(ratio1, ratio2) > 0.85:
                        is_match = True
                
        # Check for default fallback source values (e.g. "General Dealer.com Website")
        if 'general dealer.com website' in source_val_low or 'general dealer.com' in source_val_low:
            is_match = True

        if is_match:
            result['status'] = 'ok'
        else:
            result['status'] = 'wrong'
    
    except Exception as e:
        print(f"Lead Form Source Check Error: {e}")
        result['status'] = 'error'
    
    return result

@app.route('/api/save-correction', methods=['POST'])
def api_save_correction():
    data = request.json or {}
    url = data.get('url')
    filter_url = data.get('filter_url')
    if not url or not filter_url:
        return jsonify({'status': 'error', 'message': 'Missing url or filter_url'}), 400
    
    try:
        record = inventory_learner.save_correction(url, filter_url, source='manual_correction')
        return jsonify({'status': 'ok', 'record': record})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/extract-h1', methods=['GET', 'POST'])
def extract_h1():
    url = None
    expected_title = ''
    expected_content = ''
    special_instructions = ''
    custom_rules = ''
    case_id = ''

    if request.method == 'POST':
        data = request.json or {}
        url = data.get('url')
        expected_title = data.get('expected_title', '').strip()
        expected_content = data.get('expected_content', '').strip()
        special_instructions = data.get('special_instructions', '').strip()
        custom_rules = data.get('custom_rules', '').strip()
        case_id = data.get('case_number', '').strip()
    else:
        url = request.args.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    try:
        session = requests.Session(impersonate='chrome', verify=False)
        _t0 = time.time()
        response = session.get(url, timeout=30)
        _response_time_ms = (time.time() - _t0) * 1000
        
        if response.status_code >= 400:
            return jsonify({
                'success': False,
                'error': f'Failed to fetch content (HTTP Code: {response.status_code})'
            }), 400
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Full page text — no character limit (used for SEO coverage check)
        full_page_text = soup.get_text(separator=' ', strip=True)
        
        page_title_tag = soup.find('title')
        page_title = page_title_tag.string.strip() if page_title_tag and page_title_tag.string else ''
        
        # Limited version for AI prompts (coherence, etc.) to stay within token limits
        main_text = full_page_text[:5000]

        # Page Audit (runs early since it only needs soup + response)
        try:
            page_audit = run_page_audit(url, soup, response, _response_time_ms)
        except Exception as _e:
            print(f"Page audit error: {_e}")
            page_audit = {'score': None, 'total_checks': 0, 'passes': 0, 'warns': 0, 'fails': 0, 'categories': {}}
        
        # 1. H1 Processing
        h1_tags_raw = soup.find_all('h1')
        h1_tags = []
        ignored_but_displayed_h1s = []
        for h1 in h1_tags_raw:
            # Ignore false H1s frequently used as popup banners
            if h1.get('role') == 'heading' and h1.get('aria-level') == '2': continue
            
            # Ignore specific inventory widget H1 from bug validation but keep for display
            if h1.find('span', id='results-count') and h1.find('span', id='singular'):
                ignored_but_displayed_h1s.append(h1)
                continue
                
            h1_tags.append(h1)
            
        results = [str(tag) for tag in (h1_tags + ignored_but_displayed_h1s)]
        
        h1_count = len(h1_tags)
        h1_valid = True
        h1_error_msg = None
        
        if h1_count == 0:
            h1_valid = False
            h1_error_msg = "No H1 tags found. There must be at least one."
        elif h1_count > 2:
            h1_valid = False
            h1_error_msg = f"Found {h1_count} H1 tags. Maximum allowed is 1 (or 2 if one is 'sr-only')."
        elif h1_count == 2:
            text1 = h1_tags[0].get_text(separator=' ', strip=True)
            text2 = h1_tags[1].get_text(separator=' ', strip=True)
            classes1 = h1_tags[0].get('class', [])
            classes2 = h1_tags[1].get('class', [])
            
            has_sr_only = 'sr-only' in classes1 or 'sr-only' in classes2
            texts_match = (text1 == text2)
            
            if not has_sr_only:
                h1_valid = False
                h1_error_msg = "There are 2 H1 tags, but neither has the 'sr-only' class. This is only allowed for screen-reader accessibility."
            elif not texts_match:
                h1_valid = False
                h1_error_msg = f"There are 2 H1 tags, but their inner texts do not match ('{text1[:30]}...' vs '{text2[:30]}...')."
                
        # Title Match Logic
        title_match_result = None
        if expected_title:
            title_match_status = 'not_found'
            target = expected_title.lower()
            import difflib
            for h1 in h1_tags:
                h1_text = h1.get_text(separator=' ', strip=True).lower()
                if h1_text == target or difflib.SequenceMatcher(None, h1_text, target).ratio() >= 0.95:
                    title_match_status = 'success'
                    break
            title_match_result = {'status': title_match_status}
        elif request.method == 'POST':
            title_match_result = {'status': 'no_input'}
                
        # -------- LINKS VALIDATION --------
        # Collect all valid anchor targets (IDs and names) from the FULL page first.
        # This prevents false positives if the target is in the header/footer.
        all_ids = [tag.get('id') for tag in soup.find_all(id=True) if tag.get('id')]
        all_names = [tag.get('name') for tag in soup.find_all('a', attrs={'name': True}) if tag.get('name')]
        valid_anchor_targets = set(all_ids + all_names)

        ddc_wrapper = soup.find('div', class_='ddc-wrapper')
        if ddc_wrapper:
            main_zone = ddc_wrapper.find('div', class_='main')
            search_dom = main_zone if main_zone else ddc_wrapper
        else:
            from bs4 import BeautifulSoup as _BS
            search_dom = _BS(str(soup), 'html.parser')
            for cls in ['page-header', 'ddc-footer', 'content-disclaimer', 'credit', 'ws-navigation', 'navigation-default']:
                for el in search_dom.find_all(class_=cls):
                    el.decompose()
        
        a_tags = search_dom.find_all('a', href=True)
        
        def is_hidden_or_header(tag):
            if not tag: return False
            for parent in [tag] + list(tag.parents):
                if parent.name in ['header', 'footer', 'nav']: return True
                classes = parent.get('class') or []
                if any(c in classes for c in ['hide', 'd-none', 'hidden', 'header-default', 'content-disclaimer', 'ws-navigation']):
                    return True
            return False
            
        def get_widget_name(tag):
            for parent in tag.parents:
                if parent.has_attr('data-widget-name'): return parent['data-widget-name']
                if parent.has_attr('data-widget-id'): return parent['data-widget-id']
                classes = parent.get('class') or []
                if 'widget' in classes: return "Widget " + str(classes[0])
            return "Main Content"

        broken_anchors = []
        popup_links = []
        absolute_internal_links = []
        cta_config_bugs = []
        internal_links_to_check = set()
        base_netloc = urlparse(url).netloc
        
        filtered_a_tags_count = 0
        
        # Pre-detect breadcrumbs on the page (needed for the # link rule below)
        _page_has_breadcrumbs = bool(
            soup.find(attrs={'itemtype': lambda x: x and 'BreadcrumbList' in x}) or
            soup.find(class_=lambda c: c and 'breadcrumb' in ' '.join(c).lower())
        )
        _hash_only_seen = 0  # counter of bare # links allowed when breadcrumbs present

        for a in a_tags:
            href = a.get('href', '').strip()
            
            # ---------------- CTA LINK AUDIT RULES ----------------
            if not href or href == '#':
                _empty_widget = get_widget_name(a)
                # Ignore accordion toggles/headers that act as collapse trigger rather than CTA link
                is_accordion_toggle = False
                if 'accordion' in _empty_widget.lower():
                    classes = [c.lower() for c in (a.get('class') or [])]
                    if any(k in c for k in ['toggle', 'title', 'header', 'trigger', 'heading', 'collapsed'] for c in classes):
                        is_accordion_toggle = True
                    elif a.has_attr('data-toggle') or a.has_attr('aria-expanded') or a.has_attr('aria-controls'):
                        is_accordion_toggle = True
                    elif href.startswith('#collapse') or href.startswith('#widget'):
                        is_accordion_toggle = True
                    elif a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b']):
                        is_accordion_toggle = True
                    else:
                        parent_classes = []
                        for p in list(a.parents)[:3]:
                            parent_classes.extend([c.lower() for c in (p.get('class') or [])])
                        if any(k in c for k in ['header', 'heading', 'toggle', 'title'] for c in parent_classes):
                            is_accordion_toggle = True
                        elif not a.find_parent(class_='accordion-body') and not a.find_parent(class_='panel-body'):
                            is_accordion_toggle = True

                # Ignore breadcrumbs — but only allow ONE bare '#' per page when breadcrumbs exist
                is_breadcrumb = False
                if 'breadcrumb' in _empty_widget.lower():
                    is_breadcrumb = True
                else:
                    parent_bc = a.find_parent(attrs={'itemtype': lambda x: x and 'BreadcrumbList' in x})
                    if parent_bc: is_breadcrumb = True

                if is_breadcrumb or is_accordion_toggle or 'ws-inv-listing' in _empty_widget.lower() or 'inventory-listing' in _empty_widget.lower() or 'model-selector' in _empty_widget.lower():
                    continue

                # Bare '#' outside breadcrumb/accordion context:
                # If the page HAS breadcrumbs, allow exactly one (it's the active breadcrumb item)
                if href == '#' and _page_has_breadcrumbs and _hash_only_seen == 0:
                    _hash_only_seen += 1
                    continue  # First bare '#' is forgiven when breadcrumbs exist

                # Include text and widget so the user can locate the element
                _empty_text = a.get_text(strip=True)[:50] or '[No text / Icon]'
                cta_config_bugs.append({
                    'platform': 'D/M',
                    'type': 'Failed',
                    'category': 'Config',
                    'message': f"Empty or missing link destination on element \"{_empty_text}\" (Widget: {_empty_widget}). Button/Link does not go anywhere."
                })
                continue
                
            if 'composer/views/wysiwyg' in href or 'preview=true' in href or 'draft=true' in href:
                cta_config_bugs.append({'platform': 'D/M', 'type': 'Critical', 'category': 'Config', 'message': f"Backend CMS link exposed on frontend! '{href}'. This is a severe configuration leak."})
                
            if href.startswith('http://'):
                cta_config_bugs.append({'platform': 'D/M', 'type': 'Observed', 'category': 'Link', 'message': f"Insecure HTTP link found: '{href}'. Update to https:// for security and SEO."})
            # ------------------------------------------------------

            if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                continue
                
            if is_hidden_or_header(a): continue
            
            filtered_a_tags_count += 1
            w_name = get_widget_name(a)
            text = a.get_text(strip=True)[:50] or 'No text (Icon/Button)'
            
            # Popups / Dialogs (Skip anchor validation for these)
            if 'dialog' in (a.get('class') or []) or href.startswith('#?') or 'parentPageAlias' in href:
                target = a.get('data-el', href)
                popup_links.append({'text': text, 'target': target, 'widget': w_name})
                continue
                
            # Anchors Validation
            if href.startswith('#'):
                anchor_id = href[1:]
                if anchor_id:
                    if anchor_id not in valid_anchor_targets:
                        broken_anchors.append({
                            'text': text, 'href': href, 'widget': w_name,
                            'error': f"ID '{anchor_id}' does not exist in Landing"
                        })
                continue
            
            full_link = urljoin(url, href)
            parsed_link = urlparse(full_link)
            
            if parsed_link.netloc == base_netloc and parsed_link.path == urlparse(url).path and parsed_link.fragment:
                anchor_id = parsed_link.fragment
                if anchor_id not in valid_anchor_targets:
                    broken_anchors.append({
                        'text': text, 'href': href, 'widget': w_name,
                        'error': f"ID '{anchor_id}' does not exist in Landing"
                    })
                continue
            
            if parsed_link.netloc == base_netloc and parsed_link.scheme in ['http', 'https']:
                # Bug detection: Internal links should be relative
                if href.startswith(('http://', 'https://')):
                    # Extract relative path for the suggestion
                    rel_path = parsed_link.path
                    if not rel_path or rel_path == '/':
                        rel_path = '/index.htm'
                    if parsed_link.query:
                        rel_path += '?' + parsed_link.query
                        
                    absolute_internal_links.append({
                        'text': text, 
                        'href': href, 
                        'rel_path': rel_path,
                        'widget': w_name
                    })
                    
                clean_url = parsed_link._replace(fragment="").geturl()
                is_btn = 'btn' in (a.get('class') or [])
                internal_links_to_check.add((clean_url, text, w_name, 'button' if is_btn else 'text'))
                
        limit_links = list(internal_links_to_check)[:50]
        broken_links = []
        valid_links = []
        
        if limit_links:
            def check_link(link_tuple):
                lnk, txt, wname, ltype = link_tuple
                try:
                    resp = session.head(lnk, timeout=5, allow_redirects=True)
                    if resp.status_code == 404 or resp.status_code >= 500:
                        return {'type': 'broken', 'href': lnk, 'text': txt, 'widget': wname, 'status': resp.status_code}
                    else:
                        return {'type': 'valid', 'href': lnk, 'text': txt, 'widget': wname, 'link_type': ltype}
                except Exception as e:
                    # Timeout or Connection Error is almost always WAF/bot-protection. 
                    # A real broken link will return a fast 404. We treat timeouts/connection errors as valid for now to avoid false positives.
                    return {'type': 'valid', 'href': lnk, 'text': txt, 'widget': wname, 'link_type': ltype}
            
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = {executor.submit(check_link, lnk): lnk for lnk in limit_links}
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        if res['type'] == 'broken':
                            broken_links.append(res)
                        else:
                            res.pop('type', None) # Remove 'type' key to match valid_links shape expected by frontend (type/link_type mapping is slightly messy, let's fix it)
                            valid_link_obj = {'href': res['href'], 'text': res['text'], 'widget': res['widget'], 'type': res['link_type']}
                            valid_links.append(valid_link_obj)
        
        unique_broken_anchors = {f"{a['href']}-{a['error']}": a for a in broken_anchors}.values()
        
        # -------- INITIALIZATIONS --------
        bugs = []
        coherence_score = None
        coherence_explanation = "Add your GEMINI_API_KEY to see semantic analysis."
        coherence_warnings = []
        seo_coverage = None
        special_instructions_bugs = []
        missing_ctas_list = []
        rules_evaluation = None
        inventory_validation_bugs = []
        inventory_info = {'status': 'skipped'}
        
        # -------- CTA VALIDATION (Deterministic & Learning) --------
        parsed_instructions = parse_cta_instructions(special_instructions)
        cta_db = load_cta_patterns()
        cta_evaluations = []
        
        # -------- CUSTOM LAYOUT RULES VALIDATION --------
        # Moved below inventory validation so inventory_info is populated
        
        if parsed_instructions:
            for inst in parsed_instructions:
                target_text = inst['text']
                target_url = inst['url']
                
                # Prediction logic if missing text or url
                if target_text and not target_url:
                    target_url = cta_db['by_text'].get(target_text.lower())
                elif target_url and not target_text:
                    target_text = cta_db['by_url'].get(target_url)
                
                found_match = False
                matched_a = None
                coherence_issue = None

                for a in a_tags:
                    a_text = a.get_text(strip=True)
                    a_href = a.get('href', '').strip()
                    if not a_href: continue

                    match_text = False
                    match_url  = False

                    if target_text and target_text.lower() == a_text.lower():
                        match_text = True

                    if target_url:
                        # Flexible URL matching: compare paths
                        t_parsed = urlparse(target_url)
                        t_path = t_parsed.path.lower().rstrip('/')
                        t_fragment = t_parsed.fragment.lower()
                        a_parsed = urlparse(a_href)
                        a_path = a_parsed.path.lower().rstrip('/')
                        a_fragment = a_parsed.fragment.lower()
                        if not t_path: t_path = '/'
                        if not a_path: a_path = '/'

                        # Homepage normalization
                        is_home_t = (t_path in ('/', '/index.htm'))
                        is_home_a = (a_path in ('/', '/index.htm'))

                        if (is_home_t and is_home_a) or t_path == a_path or a_href.endswith(target_url) or a_href == target_url:
                            match_url = True
                        
                        # Same-page anchor: target URL points to current page path + #anchor
                        # In this case look for an element with that id on the page, not a link to it
                        if not match_url and t_fragment:
                            cur_path = urlparse(url).path.lower().rstrip('/')
                            if t_path == cur_path or not t_path or t_path == '/':
                                # Check if fragment exists as id on page
                                if soup.find(id=t_fragment) or soup.find(id=t_fragment.replace('-', '_')):
                                    match_url = True  # anchor exists on page → treat as fulfilled

                    # KEY RULE: If a URL was given, the PATH is the only authority.
                    if inst['url'] and match_url:
                        found_match = True
                        matched_a = a
                        # Check for typos in the requested instruction itself
                        req_url = inst['url']
                        if req_url and '.' in req_url:
                            ext = req_url.split('.')[-1].lower()
                            if ext in ['ht', 'h', 'htmll']:
                                special_instructions_bugs.append(
                                    make_bug('instructions_mismatch', f"Requested URL '{req_url}' appears to have a typo (e.g. .ht instead of .htm). Please verify.")
                                )
                                
                        if a_text and len(a_text) > 3:
                            dest_path_low = urlparse(a_href).path.lower()
                            txt_low = a_text.lower()
                            # Examples of incoherence: 'Schedule Service' -> /new-inventory/
                            # or 'Buy Now' -> /contact-us/
                            COHERENCE_PAIRS = [
                                (['new', 'new car', 'new vehicle', 'new truck'], 'used-inventory'),
                                (['used', 'pre-owned', 'preowned'], 'new-inventory'),
                                (['service', 'oil change', 'maintenance', 'repair'], ['new-inventory', 'used-inventory', 'finance']),
                                (['finance', 'loan', 'apply', 'credit'], ['service', 'parts']),
                            ]
                            for text_hints, bad_paths in COHERENCE_PAIRS:
                                bad_paths = [bad_paths] if isinstance(bad_paths, str) else bad_paths
                                if any(h in txt_low for h in text_hints):
                                    if any(bp in dest_path_low for bp in bad_paths):
                                        coherence_issue = f"Anchor text '{a_text[:40]}' appears semantically incoherent with destination '{a_href}'."
                                        break
                        break
                    # If ONLY text was given (no URL), match by text
                    elif inst['text'] and not inst['url'] and match_text:
                        found_match = True
                        matched_a = a
                        break

                if found_match and matched_a:
                    l_text = matched_a.get_text(strip=True)
                    l_href = matched_a.get('href', '').strip()
                    save_cta_pattern(l_text, l_href)
                    result = {
                        'original': inst['original'],
                        'status': 'success',
                        'found_text': l_text,
                        'found_href': l_href
                    }
                    if coherence_issue:
                        # Pass the CTA (path found) but add a coherence warning
                        result['coherence_warning'] = coherence_issue
                        special_instructions_bugs.append(
                            make_bug('instructions_mismatch',
                                     f"CTA path found but text may be incoherent: {coherence_issue}")
                        )
                    cta_evaluations.append(result)
                else:
                    # Bug: path not found on the page at all
                    hint = ''
                    if inst['url']:
                        hint = f" ({inst['url']})"
                    missing_ctas_list.append(f"'{inst['original']}'{hint}")
                    cta_evaluations.append({
                        'original': inst['original'],
                        'status': 'error'
                    })
                    
        if missing_ctas_list:
            ctas_str = ', '.join(missing_ctas_list)
            if len(ctas_str) > 150: ctas_str = ctas_str[:147] + '...'
            special_instructions_bugs.append(make_bug('cta_missing', f"Requested CTAs are missing from the page: {ctas_str}"))

        # ── LOCAL NLP COHERENCE (replaces Gemini unified AI call) ─────────────
        try:
            coherence_result = analyze_coherence(url, expected_title or (h1_tags[0].get_text(strip=True) if h1_tags else ''), full_page_text)
            coherence_score = coherence_result.get('score', 100)  # already 0-100
            coherence_explanation = coherence_result.get('explanation', '')
            
            # --- NEW: DEEP SEMANTIC CHECK (LLM + Entity Matching) ---
            try:
                import memory_engine
                rag_context = memory_engine.build_rag_context(url, custom_rules)
            except Exception:
                rag_context = ""
                
            deep_semantic = semantic_qa.run_semantic_check(
                url=url, 
                h1=h1_tags[0].get_text(strip=True) if h1_tags else '', 
                page_text=full_page_text, 
                page_title=page_title,
                rag_context=rag_context,
                run_llm=True
            )
            
            coherence_warnings = []
            
            if deep_semantic.get('combined_verdict') in ('warning', 'bug'):
                for issue in deep_semantic.get('combined_issues', []):
                    level = 'red' if deep_semantic['combined_verdict'] == 'bug' else 'yellow'
                    coherence_warnings.append({
                        'text': 'Page Content', 'href': url, 'reason': f"Semantic Mismatch: {issue}", 'level': level
                    })
                
                if deep_semantic.get('combined_verdict') == 'bug':
                    coherence_score = min(coherence_score, 40)
                    coherence_explanation = f"Semantic Bug Detected. {coherence_explanation}"
                else:
                    coherence_score = min(coherence_score, 75)
            
            # --- NEW: DETAILED CTA COHERENCE ---
            # 1. Infer Site Brand(s) for context — multi-brand dealers supported
            main_brand = None
            allowed_brands = set()  # All brands the dealer is allowed to mention
            domain_low = urlparse(url).netloc.lower()
            domain_core = re.sub(r'\.(com|net|org|co|us|ca|au|uk|io)$', '', domain_low)
            domain_core = re.sub(r'^(www|m|mobile)\.', '', domain_core)

            # Known multi-brand group shortcuts in domain names
            MULTI_BRAND_GROUPS = {
                'cdjr':   ['Chrysler', 'Dodge', 'Jeep', 'Ram'],
                'cdj':    ['Chrysler', 'Dodge', 'Jeep'],
                'cjdr':   ['Chrysler', 'Jeep', 'Dodge', 'Ram'],
                'chryslerdodgejeep': ['Chrysler', 'Dodge', 'Jeep'],
                'fca':    ['Chrysler', 'Dodge', 'Jeep', 'Ram', 'Fiat', 'Alfa Romeo'],
                'gmg':    ['Chevrolet', 'GMC'],
                'gmc':    ['GMC', 'Buick'],
                'buickgmc': ['Buick', 'GMC'],
                'chevygmc': ['Chevrolet', 'GMC'],
                'fordlincoln': ['Ford', 'Lincoln'],
                'lincolnford': ['Ford', 'Lincoln'],
                'hondaacura': ['Honda', 'Acura'],
                'toyotalexus': ['Toyota', 'Lexus'],
            }

            for grp_key, grp_brands in MULTI_BRAND_GROUPS.items():
                if grp_key in domain_core.replace('-', '').replace('_', ''):
                    allowed_brands.update(grp_brands)

            for key, val in LOCAL_MAKES.items():
                if len(key) <= 3:
                    continue
                domain_tokens = re.split(r'[-_]|(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])', domain_core)
                key_found = False
                for token in domain_tokens:
                    if token == key:
                        key_found = True
                        break
                    if 'of' in token:
                        parts = token.split('of')
                        if key in parts:
                            key_found = True
                            break
                if not key_found:
                    if key == 'ford' and domain_core.endswith(('wexford', 'oxford', 'bradford', 'bedford', 'stanford', 'hartford')):
                        key_found = False
                    elif domain_core.startswith(key) or domain_core.endswith(key):
                        key_found = True

                if key_found:
                    allowed_brands.add(val)
                    if not main_brand:
                        main_brand = val

            if not main_brand and 'vw' in domain_low:
                main_brand = 'Volkswagen'
                allowed_brands.add('Volkswagen')
            if not allowed_brands and main_brand:
                allowed_brands.add(main_brand)

            print(f"DEBUG: Brand detection - domain='{domain_core}', main_brand='{main_brand}', allowed_brands={allowed_brands}")
            
            # Count bare '#' links for the breadcrumb rule
            hash_only_links_count = 0
            
            # 2. Scan all analyzed links for inconsistencies
            for lnk, txt, wname, ltype in limit_links:
                txt_low = txt.lower()
                lnk_low = lnk.lower()
                
                # A. Typos check
                typos = {'inventroy': 'inventory', 'specail': 'special', 'fiannce': 'finance', 'shcedule': 'schedule'}
                for t, correct in typos.items():
                    if t in txt_low:
                        coherence_warnings.append({
                            'text': txt, 'href': lnk, 'reason': f"Typo detected: '{t}' instead of '{correct}'", 'level': 'red'
                        })
                
                # B. Brand Mismatch — only flag brands NOT in the dealer's allowed_brands set
                if allowed_brands:
                    other_brands = [b for b in set(LOCAL_MAKES.values()) if b not in allowed_brands and len(b) > 3]
                    for ob in other_brands:
                        ob_low = ob.lower()
                        if re.search(rf'\b{re.escape(ob_low)}\b', txt_low):
                            if 'vs' in txt_low or 'compare' in txt_low or 'competitor' in txt_low:
                                continue
                            coherence_warnings.append({
                                'text': txt, 'href': lnk, 'reason': f"Brand Mismatch: Found '{ob}' on a {main_brand} page.", 'level': 'red'
                            })

                # C. Type Discrepancy (New text -> Used URL)
                if 'new' in txt_low and 'used-inventory' in lnk_low and 'new-inventory' not in lnk_low:
                    coherence_warnings.append({
                        'text': txt, 'href': lnk, 'reason': "Incoherent: 'New' text points to Used inventory.", 'level': 'yellow'
                    })
                if 'used' in txt_low and 'new-inventory' in lnk_low and 'used-inventory' not in lnk_low:
                    coherence_warnings.append({
                        'text': txt, 'href': lnk, 'reason': "Incoherent: 'Used' text points to New inventory.", 'level': 'yellow'
                    })
                
                # D. Breadcrumb coherence (Special check)
                if 'breadcrumb' in wname.lower():
                    # If breadcrumb mentions a brand different from main_brand
                    if main_brand:
                        for ob in set(LOCAL_MAKES.values()):
                            if ob != main_brand and ob.lower() in txt_low:
                                coherence_warnings.append({
                                    'text': txt, 'href': lnk, 'reason': f"Incoherent Breadcrumb: Mentioning '{ob}' in a {main_brand} site structure.", 'level': 'red'
                                })
            
        except Exception as e:
            coherence_explanation = f"NLP coherence error: {str(e)}"
            print(f"NLP coherence error: {e}")
        # ──────────────────────────────────────────────────────────────────────

        # Inventory Validation (uses local engine + NLP as last resort)
        try:
            nav_selector = 'nav a, header a, .navbar-nav a, .ws-navigation a, [data-widget-name*="navigation"] a'
            nav_links_raw = soup.select(nav_selector)
            nav_links = [{"text": a.get_text(strip=True), "href": a.get('href')} for a in nav_links_raw if a.get('href') and not a['href'].startswith(('javascript', 'tel', 'mailto'))][:25]
            combined_instructions = f"{special_instructions}\n{custom_rules}".strip()
            inventory_validation_bugs, inventory_info = validate_inventory(url, nav_links, response.text, combined_instructions)
        except Exception as e:

            import traceback
            print("Inventory logic error:")
            traceback.print_exc()
            inventory_info['status'] = 'error'

        # -------- CUSTOM LAYOUT RULES VALIDATION --------
        # Only use custom_rules for layout instruction parsing
        combined_rules = custom_rules.strip()

        # Calculate SEO coverage early if expected_content is provided so we can use it to verify content-update rules
        temp_seo_coverage = None
        if expected_content:
            import re as _re_seo
            def _norm_temp(text):
                return _re_seo.sub(r'[^a-z0-9]', '', text.lower())
            
            from bs4 import BeautifulSoup as _BS_temp
            temp_soup = _BS_temp(expected_content, 'html.parser')
            for br in temp_soup.find_all("br"):
                br.replace_with("\n")
            raw_c = temp_soup.get_text(separator='|||', strip=True)
            temp_chunks = [b.strip() for b in raw_c.split('|||') if len(b.strip()) >= 10]
            if temp_chunks:
                norm_p = _norm_temp(full_page_text)
                f_count = sum(1 for c in temp_chunks if _norm_temp(c) in norm_p)
                temp_seo_coverage = int((f_count / len(temp_chunks)) * 100)

        inst_engine_result = instruction_engine.evaluate_instructions(combined_rules, soup, full_page_text, seo_coverage=temp_seo_coverage, inventory_info=inventory_info)

        
        if inst_engine_result.get("fallback"):
            # Fallback to legacy regex engine if Ollama is down
            custom_layout_evaluations = verify_custom_rules(combined_rules, soup, inventory_info)
            cr_lower = combined_rules.lower()
            inventory_info["requires_layout_ui"] = any(k in cr_lower for k in ['grid', 'list', 'layout'])
            inventory_info["requires_breadcrumb_ui"] = 'breadcrumb' in cr_lower
        else:
            custom_layout_evaluations = inst_engine_result.get("evaluations", [])
            inventory_info["requires_layout_ui"] = inst_engine_result.get("requires_layout_ui", False)
            inventory_info["requires_breadcrumb_ui"] = inst_engine_result.get("requires_breadcrumb_ui", False)
            
        for evaluation in custom_layout_evaluations:
            if evaluation['status'] == 'error':
                reason = evaluation.get('reason') or f"Could not verify '{evaluation['original']}'"
                special_instructions_bugs.append(make_bug(
                    'instructions_mismatch',
                    f"Rule Failed: {reason} (Rule: '{evaluation['original']}')"
                ))
            elif evaluation['status'] == 'manual_review':
                reason = evaluation.get('reason') or f"Manual Verification Needed for Rule: '{evaluation['original']}'"
                special_instructions_bugs.append(make_bug(
                    'inventory_manual_review',
                    f"Manual Review: {reason}"
                ))

        chunks = []

        # -------- DETERMINISTIC SEO COVERAGE (pure Python, no AI) --------
        if expected_content and seo_coverage is None:
            import re as _re
            from bs4 import BeautifulSoup as _BS2

            def _norm(text):
                """Lowercase + strip all non-alphanumeric chars for robust matching."""
                return _re.sub(r'[^a-z0-9]', '', text.lower())

            from difflib import SequenceMatcher
            def get_highlighted_chunk(chunk, sentences_list):
                chunk_words = set(chunk.lower().split())
                best_match = None
                best_score = 0
                if chunk_words and sentences_list:
                    for s in sentences_list:
                        s_words = set(s.lower().split())
                        if not s_words: continue
                        overlap = len(chunk_words.intersection(s_words))
                        score = overlap / len(chunk_words)
                        if score > best_score:
                            best_score = score
                            best_match = s
                if not best_match or best_score < 0.2:
                    return [{'text': chunk, 'status': 'missing'}]
                
                a = chunk.split()
                b = best_match.split()
                sm = SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b])
                result = []
                for opcode, a0, a1, b0, b1 in sm.get_opcodes():
                    if opcode == 'equal':
                        result.append({'text': " ".join(a[a0:a1]), 'status': 'found'})
                    elif opcode in ('delete', 'replace'):
                        if a0 != a1:
                            result.append({'text': " ".join(a[a0:a1]), 'status': 'missing'})
                return result

            # Parse expected HTML into clean plain text segments per block element
            exp_soup = _BS2(expected_content, 'html.parser')
            # Use a more intelligent separator to handle inline tags (<b>, <i>, etc)
            # without splitting words, but still separating block elements.
            for br in exp_soup.find_all("br"):
                br.replace_with("\n")
                
            raw_chunks = exp_soup.get_text(separator='|||', strip=True)
            chunks = []
            for block in raw_chunks.split('|||'):
                block = block.strip()
                if not block: continue
                
                # If the block is long, split it into sentences to be more resilient to small changes
                if len(block) > 150:
                    # Split by sentence enders (. ! ?) followed by space
                    sentences = _re.split(r'(?<=[.!?])\s+', block)
                    for s in sentences:
                        s = s.strip()
                        if len(s) >= 10:
                            chunks.append(s)
                else:
                    if len(block) >= 10:
                        chunks.append(block)

            if not chunks:
                seo_coverage = 0
                seo_missing_chunks = []
            else:
                # Normalize the FULL page text
                norm_page = _norm(full_page_text)
                page_sentences = [s.strip() for s in _re.split(r'(?<=[.!?\n])\s+', full_page_text) if len(s.strip()) > 10]
                
                found_count = 0
                seo_missing_chunks = []
                for chunk in chunks:
                    if _norm(chunk) in norm_page:
                        found_count += 1
                    else:
                        seo_missing_chunks.append(get_highlighted_chunk(chunk, page_sentences))

                seo_coverage = int((found_count / len(chunks)) * 100)

        # -------- MOBILE SEO COVERAGE --------
        seo_coverage_mobile = None
        seo_missing_chunks_mobile = []
        if expected_content and chunks:
            try:
                # Robust mobile URL construction
                parsed_url = urlparse(url)
                from urllib.parse import parse_qsl, urlencode, urlunparse
                query_params = parse_qsl(parsed_url.query)
                # DDC standard mobile renderer flag
                query_params.append(('_renderer', 'mobile'))
                new_query = urlencode(query_params)
                mobile_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))

                time.sleep(1.0)
                mobile_resp = None
                try:
                    # Simple fetch with the mobile renderer flag - usually sufficient for DDC
                    mobile_resp = session.get(mobile_url, timeout=15)
                except Exception as me:
                    print(f"DEBUG: Mobile fetch failed: {me}")
                
                if mobile_resp and mobile_resp.status_code < 400:
                    mobile_soup = BeautifulSoup(mobile_resp.text, 'html.parser')
                    mobile_full_text = mobile_soup.get_text(separator=' ', strip=True)
                    norm_mobile = _norm(mobile_full_text)
                    mobile_page_sentences = [s.strip() for s in _re.split(r'(?<=[.!?\n])\s+', mobile_full_text) if len(s.strip()) > 10]
                    found_mobile = 0
                    for chunk in chunks:
                        if _norm(chunk) in norm_mobile:
                            found_mobile += 1
                        else:
                            seo_missing_chunks_mobile.append(get_highlighted_chunk(chunk, mobile_page_sentences))
                    seo_coverage_mobile = int((found_mobile / len(chunks)) * 100)

                    # Flag mobile missing content as a Critical bug
                    if seo_coverage_mobile < 80 and seo_coverage_mobile >= 0:
                        bugs.append(make_bug('seo_coverage_low_mobile', 'M | Critical | Content | Content is missing on mobile view'))
            except Exception as e:
                print(f"Mobile coverage error: {e}")


        # -------- IMAGE WIDGET VALIDATION --------
        image_issues = []
        # Find standalone image widgets
        # Skip certain widgets that auto-handle titles or are specific headers (Hero)
        SKIP_WIDGET_KWS = ['content-w-image', 'content-50-50', 'content-with-image', 'offset-vehicle-hero', 'js-hero-content']
        
        # Search for elements that look like widgets
        for widget in search_dom.find_all(lambda t: t.has_attr('data-widget-name') or t.has_attr('data-name')):
            w_name = widget.get('data-widget-name', widget.get('data-name', '')).lower()
            
            # Skip if it's a known exempted widget type
            if any(skip in w_name for skip in SKIP_WIDGET_KWS):
                continue
            
            # Only analyze widgets that are primarily images
            if 'image' not in w_name:
                continue
                
            for img in widget.find_all('img'):
                # Also skip specific img classes mentioned by user
                img_classes = img.get('class') or []
                if any(c in ['dynamic-resize', 'img-responsive'] for c in img_classes):
                    continue

                problems = []
                title_val = img.get('title', '').strip()
                alt_val = img.get('alt', '').strip()
                
                if not title_val and not alt_val:
                    problems.append('missing title and alt attributes')
                elif not title_val and len(alt_val) < 5:
                    problems.append('missing title, and alt attribute is too short (should be descriptive like Make/Model)')
                
                if 'w-100' not in img_classes:
                    problems.append('missing w-100 class')
                
                if problems:
                    raw_src = extract_real_img_src(img, url)
                    if not raw_src:
                        import re as _re_widget
                        urls = _re_widget.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp|gif)', str(widget), _re_widget.I)
                        for u in urls:
                            if not is_placeholder_url(u):
                                raw_src = u.replace(' ', '%20')
                                break
                    image_issues.append({
                        'src': raw_src,
                        'widget': w_name,
                        'problems': problems
                    })



        # -------- MEDIA LIBRARY AUDIT (Dual Space) --------
        # -------- MEDIA LIBRARY AUDIT (Dual Space) --------
        media_audit_desktop = run_media_audit(url, response.text, soup)
        
        media_audit_mobile = {'status': 'skipped', 'dealer_id': None, 'offending_images': [], 'analyzed_images': [], 'bugs': []}
        try:
            mobile_url = url + ('&' if '?' in url else '?') + '_renderer=mobile'
            response_mobile = session.get(mobile_url, timeout=30)
            if response_mobile.status_code == 200:
                soup_mobile = BeautifulSoup(response_mobile.text, 'html.parser')
                media_audit_mobile = run_media_audit(mobile_url, response_mobile.text, soup_mobile)
        except Exception as e:
            print(f"Mobile Media Audit Error: {e}")
            media_audit_mobile['status'] = 'error'

        # Collect bugs from audits
        for b in media_audit_desktop['bugs']: bugs.append(b)
        for b in media_audit_mobile['bugs']: bugs.append(b)
        
        media_audit = media_audit_desktop # Legacy for any old UI parts

        # -------- CONSOLIDATED BUG AGGREGATION --------
        # Note: bugs list is initialized at the top and never wiped.

        # Consolidated H1 & Title issues
        title_missing = (title_match_result and title_match_result.get('status') == 'not_found')
        
        if h1_count == 0:
            bugs.append({'platform': 'D/M', 'type': 'Failed', 'category': 'Layout', 'message': 'No H1 tag found on the page.'})
        elif h1_count > 1:
            if title_missing:
                bugs.append({'platform': 'D/M', 'type': 'Failed', 'category': 'Layout', 'message': f"Multiple incorrect H1 tags found. Expected only one H1 matching: '{expected_title}'"})
            else:
                if not h1_valid:
                    bugs.append({'platform': 'D/M', 'type': 'Failed', 'category': 'Layout', 'message': 'Multiple H1 tags found. Only one H1 is allowed per page.'})
        else:
            if title_missing:
                bugs.append({'platform': 'D/M', 'type': 'Failed', 'category': 'Content', 'message': f"H1 mismatch. Page H1 does not match the expected task title: '{expected_title}'"})
            elif not h1_valid and h1_error_msg:
                bugs.append({'platform': 'D/M', 'type': 'Failed', 'category': 'Layout', 'message': h1_error_msg})

        # Broken 404 links
        broken_link_texts = []
        for bl in broken_links:
            text = bl.get('text', '')
            # Skip common legal footer links that might fail due to tracking/scripts
            if any(k in text.lower() for k in ['privacy policy', 'terms and conditi', 'terms of service']):
                continue
            broken_link_texts.append(text[:30] or bl['href'])
            
        if broken_link_texts:
            texts_str = ', '.join(broken_link_texts)
            if len(texts_str) > 150: texts_str = texts_str[:147] + '...'
            bugs.append(make_bug('link_broken', f"Broken Links (404/Error) found for CTAs: {texts_str}. Targets are not reachable.", platform='M/D'))

        # Broken anchors
        for ba in unique_broken_anchors:
            text = ba.get('text', '')[:40]
            bugs.append(make_bug('link_anchor', f"Broken Anchor Link: '{text}'. The ID '{ba['href']}' does not exist on this page.", platform='M/D'))

        # Absolute internal links
        # Exclude legal/privacy links inside lead forms — these are always hardcoded absolute
        _LEGAL_TEXTS = {'privacy policy', 'privacy', 'terms', 'terms of service',
                        'terms & conditions', 'terms and conditions', 'disclaimer',
                        'cookie policy', 'legal'}
        _LEAD_FORM_WIDGETS = {'lead', 'form', 'contact', 'modal', 'popup', 'overlay',
                              'trade', 'finance', 'credit', 'apply'}

        def _is_legal_link(link_entry):
            txt_low = link_entry.get('text', '').lower()
            href_low = link_entry.get('href', '').lower()
            wgt_low = link_entry.get('widget', '').lower()
            is_legal_txt = any(lt in txt_low for lt in _LEGAL_TEXTS) or any(lt in href_low for lt in ['privacy', 'terms', 'disclaimer'])
            # Exclude legal/privacy policy links generally, or if in lead form/footer widgets
            return is_legal_txt

        abs_link_names = []
        for abs_lnk in absolute_internal_links:
            if _is_legal_link(abs_lnk):
                continue  # skip Privacy Policy / Terms / Legal links
            abs_link_names.append(abs_lnk.get('text', '')[:30] or abs_lnk.get('href', ''))
            
        if abs_link_names:
            texts_str = ', '.join(abs_link_names)
            if len(texts_str) > 150: texts_str = texts_str[:147] + '...'
            bugs.append(make_bug('link_absolute', f"Absolute paths used instead of relative for CTAs: {texts_str}"))

        # Coherence and Semantic Issues
        red_issues = []
        yellow_issues = []
        for cw in coherence_warnings:
            reason = cw.get('reason', 'Label does not match destination URL.')
            reason = reason.replace('Semantic Mismatch: ', '').strip()
            
            if cw.get('text') and cw.get('text') != 'Page Content':
                text = cw.get('text', '')[:40].strip()
                reason = f"Link '{text}': {reason}"
                
            if cw.get('level') == 'red':
                red_issues.append(reason)
            else:
                yellow_issues.append(reason)
                
        if red_issues:
            issues_str = " • ".join(red_issues)
            if len(issues_str) > 300: issues_str = issues_str[:297] + "..."
            bugs.append({'platform': 'M/D', 'type': 'Failed', 'category': 'Content', 'message': f"Page Coherence Issues: {issues_str}"})
            
        if yellow_issues:
            issues_str = " • ".join(yellow_issues)
            if len(issues_str) > 300: issues_str = issues_str[:297] + "..."
            bugs.append({'platform': 'M/D', 'type': 'Observed', 'category': 'Content', 'message': f"Semantic Observations: {issues_str}"})

        # SEO coverage low
        if seo_coverage is not None and seo_coverage != -1 and seo_coverage < 60:
            bugs.append({'platform': 'D/M', 'type': 'Critical', 'category': 'Content', 'message': f'SEO content coverage is only {seo_coverage}%. Content may be missing or incorrect.'})

        # Enrich image_issues with real image URLs from media_audit analyzed images if static src was empty
        if 'media_audit_desktop' in locals() and media_audit_desktop.get('analyzed_images'):
            for img_issue in image_issues:
                if not img_issue.get('src') or is_placeholder_url(img_issue.get('src')):
                    w_name = (img_issue.get('widget') or '').lower()
                    for a_img in media_audit_desktop['analyzed_images']:
                        a_w = (a_img.get('widget') or '').lower()
                        a_src = a_img.get('src') or ''
                        if a_src and not is_placeholder_url(a_src):
                            if w_name in a_w or a_w in w_name or 'image' in a_w:
                                img_issue['src'] = a_src.replace(' ', '%20')
                                break

        # Image widget issues
        for img_issue in image_issues:

            w_name = img_issue['widget']
            img_url = img_issue.get('src') or ''
            src_str = f" ({img_url})" if img_url else ""
            
            for prob in img_issue['problems']:
                cat = 'Content' if 'title' in prob else 'Styling'
                btype = 'Failed' if 'title' in prob else 'Observed'
                
                if 'w-100' in prob:
                    msg_body = f"Image is not properly configured: Please add the 'w-100' class to widget '{w_name}'."
                elif 'short' in prob:
                    msg_body = f"Image is not properly configured: Please add a descriptive title/alt attribute to widget '{w_name}'."
                else:
                    msg_body = f"Image is not properly configured: Please add title and alt attributes to widget '{w_name}'."

                bugs.append({
                    'platform': 'D/M', 
                    'type': btype, 
                    'category': cat, 
                    'message': f"{msg_body}{src_str}",
                    'screenshot_link': img_url,
                    'img': img_url
                })



        # CTA Config Bugs
        if cta_config_bugs:
            bugs.extend(cta_config_bugs)

        # Inventory validation bugs
        if inventory_validation_bugs:
            bugs.extend(inventory_validation_bugs)

        # Special instructions bugs
        if 'special_instructions_bugs' in locals() and special_instructions_bugs:
            bugs.extend(special_instructions_bugs)

        # Consolidate duplicate inventory bugs into EXACTLY ONE report with formatted message & severity
        bugs = consolidate_inventory_bugs(bugs, inventory_info, custom_rules, url, soup, page_title, full_page_text)

            
        # -------- SITEMAP VALIDATION --------
        sitemap_info = {'xml_found': None, 'html_found': None, 'xml_url': None, 'html_url': None}
        try:
            sitemap_info = validate_sitemap(url)
            xml_missing = sitemap_info.get('xml_found') == False
            html_missing = sitemap_info.get('html_found') == False
            
            if xml_missing and html_missing:
                bugs.append(make_bug('sitemap_xml_missing', f"Page URL is missing from the XML/ HTML sitemap", platform='D/M'))
            elif xml_missing:
                bugs.append(make_bug('sitemap_xml_missing', f"Page URL is missing from the XML sitemap", platform='D/M'))
            elif html_missing:
                bugs.append(make_bug('sitemap_html_missing', f"Page URL is missing from the HTML sitemap", platform='D/M'))
        except Exception as e:
            print(f"Sitemap validation error: {e}")

        # -------- BREADCRUMBS VALIDATION --------
        has_breadcrumbs = False
        if soup.select('nav[aria-label="breadcrumb"], .breadcrumb, ul.breadcrumbs, [itemtype*="schema.org/BreadcrumbList"]'):
            has_breadcrumbs = True
        breadcrumbs_info = {'present': has_breadcrumbs}

        # -------- LEAD FORM SOURCE VALIDATION --------
        # (page_title is already extracted early in extract_h1)
        
        # Extract primary H1 text
        h1_str = ''
        if h1_tags:
            h1_str = h1_tags[0].get_text(separator=' ', strip=True)
            
        lead_form_info = check_lead_form_source(soup, page_title, h1_str)
        if lead_form_info.get('status') == 'wrong':
            bugs.append(make_bug('lead_form_source_wrong',
                f"'Lead Form' source is wrong. Current value: \"{lead_form_info.get('source_value', '')}\". "
                f"Expected it to match the Page Title or H1.",
                category='Form', platform='D/M'))

        # Filter ignored broken link bugs (e.g., Privacy Policy 404 in contact-form)
        filtered_bugs = []
        for b in bugs:
            msg = b.get('message', '')
            if ('Privacy Policy' in msg) and ('contact-form' in msg) and b.get('type') == 'Issue' and b.get('category') == 'Link':
                continue
            filtered_bugs.append(b)
        bugs = filtered_bugs

        try:
            parsed_url_path = urlparse(url).path
            save_audit_history(case_id, page_title, parsed_url_path)
        except Exception as e:
            print(f"History Engine error: {e}")

        try:
            import memory_engine
            memory_engine.store_qa_case(
                case_id=case_id or f"temp-{int(time.time())}",
                url=url,
                bugs=bugs,
                instructions=custom_rules,
                inventory_filter=inventory_info.get('filter_url', ''),
                page_title=page_title,
                h1_text=h1_tags[0].get_text(strip=True) if h1_tags else ''
            )
        except Exception as e:
            print(f"Memory Engine error: {e}")

        return jsonify({
            'success': True,
            'count': h1_count,
            'h1_snippets': results,
            'h1_valid': h1_valid,
            'h1_error_msg': h1_error_msg,
            'coherence_score': coherence_score,
            'coherence_explanation': coherence_explanation,
            
            'broken_links': list(broken_links),
            'broken_anchors': list(unique_broken_anchors),
            'valid_links': valid_links,
            'popup_links': popup_links,
            'coherence_warnings': coherence_warnings,
            'title_match': title_match_result,
            'seo_coverage': seo_coverage,
            'seo_missing_chunks': locals().get('seo_missing_chunks', []),
            'seo_coverage_mobile': locals().get('seo_coverage_mobile', None),
            'seo_missing_chunks_mobile': locals().get('seo_missing_chunks_mobile', []),
            'image_issues': image_issues,
            'media_audit': media_audit,
            'media_audit_desktop': media_audit_desktop,
            'media_audit_mobile': media_audit_mobile,
            'page_audit': page_audit,
            'inventory_info': inventory_info,
            'sitemap_info': sitemap_info,
            'lead_form_info': lead_form_info,
            'breadcrumbs_info': breadcrumbs_info,
            'rules_evaluation': rules_evaluation,
            'cta_evaluations': locals().get('cta_evaluations', []),
            'custom_layout_evaluations': locals().get('custom_layout_evaluations', []),
            'bugs': bugs,
            'url': url,
            'case_id': case_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500

def capture_bug_screenshots(bugs, url):
    """Use Selenium to screenshot bug elements and highlight them in red."""
    import uuid
    driver = None
    try:
        driver = get_selenium_driver()
        driver.set_window_size(1280, 800)
        driver.get(url)
        time.sleep(3) # Wait for rendering
        
        screenshot_dir = os.path.join(app.static_folder, 'pdf_screenshots')
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            
        for bug in bugs:
            # We only capture visual bugs
            btype = bug.get('bug_type', '')
            selector = None
            msg = bug.get('message', '')
            
            if btype in ['link_404', 'anchor_broken', 'cta_coherence_red', 'cta_coherence_yellow', 'link_absolute']:
                # msg format: "URL leads to a non-existing page: "{bl["text"][:40]}""
                # Let's extract the text or href to locate it.
                # Since href is lost in message, we just evaluate the string roughly.
                # A safer approach for future is adding 'selector' to make_bug.
                # For now, let's search DOM for a tags containing the text snippet.
                match = re.search(r'\"(.+?)\"', msg)
                if match:
                    val = match.group(1).replace("'", "\\'")
                    selector = f"//a[contains(text(), '{val}')] | //a[contains(@href, '{val}')]"
            elif btype in ['img_no_title', 'img_no_w100']:
                match = re.search(r'\"(.+?)\"', msg)
                if match:
                    val = match.group(1).replace("'", "\\'")
                    # Usually w_name tells us the widget containing it
                    selector = f"//div[contains(@class, '{val}')]//img | //div[contains(@data-widget-name, '{val}')]//img | //img[contains(@src, '{val}')]"
            elif btype == 'h1_multiple':
                selector = "//h1[2]" # Example: screenshot the offending H1

            if selector:
                try:
                    elems = driver.find_elements('xpath', selector)
                    if elems:
                        elem = elems[0]
                        
                        # Scroll to it
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.5)
                        
                        # Red highlight
                        driver.execute_script("arguments[0].style.boxShadow = 'inset 0 0 0 5px red';", elem)
                        driver.execute_script("arguments[0].style.outline = '4px solid red';", elem)
                        
                        # Screenshot
                        fname = f"bug_{uuid.uuid4().hex[:8]}.png"
                        fpath = os.path.join(screenshot_dir, fname)
                        elem.screenshot(fpath)
                        
                    # Remove highlight so next screenshot is clean
                        driver.execute_script("arguments[0].style.boxShadow = '';", elem)
                        driver.execute_script("arguments[0].style.outline = '';", elem)
                        
                        bug['screenshot_path'] = fpath
                except Exception as e:
                    pass
    except Exception as e:
        print("Screenshot error:", str(e))
    finally:
        if driver:
            try: driver.quit()
            except: pass


@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate a PDF bug report from scan results."""
    from fpdf import FPDF
    from flask import make_response
    import datetime
    try:
        from curl_cffi import requests as _req
    except Exception:
        import requests as _req

    from bs4 import BeautifulSoup as _BS
    import tempfile
    import os

    data = request.json or {}
    bugs = data.get('bugs', [])
    scan_url = data.get('url', 'Unknown URL')
    case_number = data.get('case_number', '').strip()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # ---- Header ----
    title_text = f"QA Bug Report: {case_number}" if case_number else "QA Bug Report"
    pdf.set_fill_color(30, 30, 46)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 15, title_text, ln=1, fill=True, align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    # Use multi_cell for the URL to prevent it from overflowing the page width, explicitly align Left
    pdf.multi_cell(0, 8, f'URL: {scan_url}', align='L')
    pdf.cell(0, 8, f'Date: {now}', ln=1, align='C')
    pdf.ln(10)

    def resolve_image_url(url):
        if not url: return ''
        url = url.strip().replace(' ', '%20')
        if 'prnt.sc' in url:
            try:
                r = _req.get(url, impersonate='chrome', timeout=10)
                if r.status_code == 200:
                    s = _BS(r.text, 'html.parser')
                    img = s.find('img', {'id': 'screenshot-image'})
                    if img and img.get('src'):
                        src = img['src'].strip().replace(' ', '%20')
                        if src.startswith('//'): src = 'https:' + src
                        return src
            except: pass
        return url


    for i, bug in enumerate(bugs, 1):
        # Bug Fields
        platform = bug.get('platform', 'M/D')
        btype    = bug.get('type', 'Failed')
        cat      = bug.get('category', 'General')
        msg      = bug.get('message', '')
        
        safe_msg = msg.encode('latin-1', 'replace').decode('latin-1')
        safe_platform = platform.encode('latin-1', 'replace').decode('latin-1')
        safe_btype = btype.encode('latin-1', 'replace').decode('latin-1')
        safe_cat = cat.encode('latin-1', 'replace').decode('latin-1')
        
        # Bug Number
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(30, 30, 30)
        pdf.write(7, f"{i}. ")
        
        # Platform Tag
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(120, 120, 120)
        pdf.write(7, f"[{safe_platform}]  ")
        
        # Type Tag (Colored)
        if safe_btype == 'Critical': pdf.set_text_color(220, 38, 38)
        elif safe_btype == 'Failed': pdf.set_text_color(239, 68, 68)
        else: pdf.set_text_color(234, 179, 8)
        pdf.write(7, f"{safe_btype} ")
        
        # Category Tag (Blue)
        pdf.set_text_color(59, 130, 246)
        pdf.write(7, f"| {safe_cat}: ")
        
        # Reset color and add line break before message
        pdf.ln(7)
        
        # Bug Message
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(40, 40, 40)
        # Add a slight left margin for the message, explicitly align Left
        pdf.set_x(20)
        pdf.multi_cell(0, 6, safe_msg, align='L')
        
        # Image Attachment / Link Section in PDF
        screenshot_link_raw = bug.get('screenshot_link', '') or bug.get('img', '') or ''
        
        # Fallback: extract image URL from safe_msg if link field was empty
        if not screenshot_link_raw and safe_msg:
            m_match = re.search(r'https?://[^\s\)\'\"]+(?:\.jpg|\.png|\.webp|\.gif|\.jpeg|pictures\.dealer\.com[^\s\)\'\"]*)', safe_msg, re.I)
            if m_match:
                screenshot_link_raw = m_match.group(0)

        if screenshot_link_raw and not is_placeholder_url(screenshot_link_raw):
            links = [l.strip() for l in screenshot_link_raw.split(',') if l.strip() and not is_placeholder_url(l.strip())]
            for link in links:
                if link.startswith('//'): link = 'https:' + link
                direct_url = resolve_image_url(link)
                
                if direct_url and direct_url.startswith('http') and not is_placeholder_url(direct_url):
                    pdf.ln(3)
                    pdf.set_font('Helvetica', 'B', 9)
                    pdf.set_text_color(100, 116, 139)
                    pdf.set_x(20)
                    pdf.write(5, 'Image Link: ')
                    
                    pdf.set_font('Helvetica', 'U', 9)
                    pdf.set_text_color(37, 99, 235)
                    pdf.multi_cell(0, 5, direct_url, link=direct_url, align='L')
                    pdf.set_text_color(0, 0, 0)
                    
                    try:
                        img_resp = _req.get(direct_url, impersonate='chrome', timeout=15, verify=False)
                        if img_resp.status_code == 200 and len(img_resp.content) > 200:
                            sfx = '.png'
                            if '.jpg' in direct_url.lower() or '.jpeg' in direct_url.lower(): sfx = '.jpg'
                            elif '.webp' in direct_url.lower(): sfx = '.webp'
                            
                            with tempfile.NamedTemporaryFile(delete=False, suffix=sfx) as tmp:
                                tmp.write(img_resp.content)
                                tmp_path = tmp.name
                            
                            # Render CENTERED thumbnail in PDF: width = 75mm (~7.5cm width)
                            img_w = 75
                            center_x = (pdf.w - img_w) / 2
                            pdf.ln(2)
                            pdf.set_x(center_x)
                            pdf.image(tmp_path, w=img_w)
                            pdf.ln(5)

                            try: os.unlink(tmp_path)
                            except: pass
                    except Exception as e:
                        print(f"PDF Image Embed Error: {e}")

        
        pdf.ln(6)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(15, pdf.get_y(), pdf.w - 15, pdf.get_y()) # Separator line
        pdf.ln(8)

    # ---- Footer ----
    pdf.ln(15)
    pdf.set_font('Helvetica', 'I', 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, 'Generated by: Diego Torrez', ln=1, align='C')
    pdf.cell(0, 6, 'MS Team - Coderoad', ln=1, align='C')

    filename = f"{case_number}.pdf" if case_number else "Bug-Report.pdf"
    
    # fpdf2 output() returns bytearray by default
    pdf_bytes = bytes(pdf.output())
    
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(debug=True, port=5000)

