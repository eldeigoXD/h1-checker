"""
reclassify_image_bank.py
========================
One-click migration and reclassification script for the Image Bank.
Processes all existing harvested images in image_bank.db, extracting:
- Year (2015-2030)
- Make (Ford, Chevrolet, GMC, Jeep, Ram, Toyota, Subaru, etc.)
- Model (Bronco, F-150, Silverado, Terrain, Crosstrek, etc.)
- Category (Lifestyle, Service & Parts, Performance, Interior, Exterior, Technology, Safety, Trims, General)
- Condition (New, Used, General)
Without losing any existing records, use counts, or timestamps.
Removes obsolete tracking pixels / junk assets if present.
"""

import os
import sqlite3
import re
from datetime import datetime

# -----------------------------------------------------------------------------
# AUTOMOTIVE TAXONOMY: MAKES & CANONICAL MODELS
# -----------------------------------------------------------------------------
AUTO_TAXONOMY = {
    'Ford': {
        'aliases': ['ford', 'fordfd'],
        'models': [
            ('Mustang Mach-E', ['mustang mach-e', 'mach-e', 'mache']),
            ('Mustang', ['mustang']),
            ('Bronco Sport', ['bronco sport', 'bronco-sport']),
            ('Bronco', ['bronco']),
            ('F-150 Lightning', ['f-150 lightning', 'f150 lightning', 'lightning']),
            ('F-150', ['f-150', 'f150', 'f 150']),
            ('F-250 Super Duty', ['f-250 super duty', 'f-250', 'f250', 'f 250']),
            ('F-350 Super Duty', ['f-350 super duty', 'f-350', 'f350', 'f 350']),
            ('Super Duty', ['super duty', 'superduty']),
            ('Explorer', ['explorer']),
            ('Expedition Max', ['expedition max', 'expedition-max']),
            ('Expedition', ['expedition']),
            ('Edge', ['edge']),
            ('Escape', ['escape']),
            ('Maverick', ['maverick']),
            ('Ranger', ['ranger']),
            ('Transit Connect', ['transit connect']),
            ('Transit', ['transit', 'e-transit']),
        ]
    },
    'Chevrolet': {
        'aliases': ['chevrolet', 'chevy', 'chev'],
        'models': [
            ('Silverado 3500 HD', ['silverado 3500', 'silverado3500', '3500 hd', '3500hd']),
            ('Silverado 2500 HD', ['silverado 2500', 'silverado2500', '2500 hd', '2500hd']),
            ('Silverado 1500', ['silverado 1500', 'silverado1500']),
            ('Silverado EV', ['silverado ev', 'silveradoev']),
            ('Silverado', ['silverado']),
            ('Tahoe', ['tahoe']),
            ('Suburban', ['suburban']),
            ('Colorado', ['colorado']),
            ('Corvette', ['corvette', 'stingray', 'z06', 'e-ray', 'eray']),
            ('Camaro', ['camaro']),
            ('Equinox EV', ['equinox ev', 'equinoxev']),
            ('Equinox', ['equinox']),
            ('Blazer EV', ['blazer ev', 'blazerev']),
            ('Blazer', ['blazer']),
            ('Traverse', ['traverse']),
            ('Trailblazer', ['trailblazer', 'trail blazer']),
            ('Trax', ['trax']),
            ('Malibu', ['malibu']),
            ('Bolt EV', ['bolt ev', 'bolt']),
        ]
    },
    'GMC': {
        'aliases': ['gmc', 'gmcgm'],
        'models': [
            ('Sierra 3500 HD', ['sierra 3500', 'sierra3500', 'sierra 3500hd']),
            ('Sierra 2500 HD', ['sierra 2500', 'sierra2500', 'sierra 2500hd']),
            ('Sierra 1500', ['sierra 1500', 'sierra1500', 'sierra-1500']),
            ('Sierra EV', ['sierra ev', 'sierraev']),
            ('Sierra', ['sierra']),
            ('Yukon XL', ['yukon xl', 'yukon-xl']),
            ('Yukon', ['yukon']),
            ('Acadia', ['acadia']),
            ('Terrain', ['terrain']),
            ('Canyon', ['canyon']),
            ('Hummer EV', ['hummer ev', 'hummer']),
        ]
    },
    'Jeep': {
        'aliases': ['jeep'],
        'models': [
            ('Grand Wagoneer L', ['grand wagoneer l']),
            ('Grand Wagoneer', ['grand wagoneer']),
            ('Wagoneer L', ['wagoneer l']),
            ('Wagoneer', ['wagoneer']),
            ('Grand Cherokee 4xe', ['grand cherokee 4xe', 'cherokee 4xe']),
            ('Grand Cherokee L', ['grand cherokee l', 'grand-cherokee-l']),
            ('Grand Cherokee', ['grand cherokee', 'grand-cherokee']),
            ('Cherokee', ['cherokee']),
            ('Wrangler 4xe', ['wrangler 4xe']),
            ('Wrangler', ['wrangler']),
            ('Gladiator', ['gladiator']),
            ('Compass', ['compass']),
            ('Renegade', ['renegade']),
        ]
    },
    'Ram': {
        'aliases': ['ram', 'ramtrucks'],
        'models': [
            ('Ram 3500', ['ram 3500', 'ram3500', '3500']),
            ('Ram 2500', ['ram 2500', 'ram2500', '2500']),
            ('Ram 1500 Classic', ['1500 classic', 'ram 1500 classic']),
            ('Ram 1500', ['ram 1500', 'ram1500', '1500']),
            ('ProMaster City', ['promaster city', 'promastercity']),
            ('ProMaster', ['promaster']),
            ('TRX', ['trx', 'ram trx']),
        ]
    },
    'Dodge': {
        'aliases': ['dodge'],
        'models': [
            ('Durango', ['durango']),
            ('Charger Daytona', ['charger daytona', 'daytona']),
            ('Charger', ['charger']),
            ('Challenger', ['challenger']),
            ('Hornet', ['hornet']),
        ]
    },
    'Chrysler': {
        'aliases': ['chrysler'],
        'models': [
            ('Pacifica Hybrid', ['pacifica hybrid']),
            ('Pacifica', ['pacifica']),
            ('300', ['chrysler 300', '300c', '300s']),
            ('Voyager', ['voyager']),
        ]
    },
    'Toyota': {
        'aliases': ['toyota'],
        'models': [
            ('Grand Highlander Hybrid', ['grand highlander hybrid']),
            ('Grand Highlander', ['grand highlander', 'grand-highlander']),
            ('Highlander Hybrid', ['highlander hybrid']),
            ('Highlander', ['highlander']),
            ('Tacoma', ['tacoma']),
            ('Tundra', ['tundra']),
            ('4Runner', ['4runner', '4-runner']),
            ('RAV4 Prime', ['rav4 prime', 'rav 4 prime']),
            ('RAV4 Hybrid', ['rav4 hybrid', 'rav 4 hybrid']),
            ('RAV4', ['rav4', 'rav-4', 'rav 4']),
            ('Land Cruiser', ['land cruiser', 'landcruiser']),
            ('Sequoia', ['sequoia']),
            ('Camry Hybrid', ['camry hybrid']),
            ('Camry', ['camry']),
            ('Corolla Cross', ['corolla cross', 'corolla-cross']),
            ('Corolla', ['corolla']),
            ('Prius Prime', ['prius prime']),
            ('Prius', ['prius']),
            ('Crown Signia', ['crown signia']),
            ('Crown', ['toyota crown', 'crown']),
            ('Sienna', ['sienna']),
            ('Venza', ['venza']),
            ('bZ4X', ['bz4x', 'bz4']),
            ('GR86', ['gr86', 'gr 86']),
            ('GR Supra', ['supra', 'gr supra']),
        ]
    },
    'Honda': {
        'aliases': ['honda'],
        'models': [
            ('CR-V Hybrid', ['cr-v hybrid', 'crv hybrid']),
            ('CR-V', ['cr-v', 'crv', 'cr v']),
            ('Civic Type R', ['civic type r', 'type r']),
            ('Civic', ['civic']),
            ('Accord Hybrid', ['accord hybrid']),
            ('Accord', ['accord']),
            ('Pilot', ['pilot']),
            ('Passport', ['passport']),
            ('Ridgeline', ['ridgeline']),
            ('HR-V', ['hr-v', 'hrv', 'hr v']),
            ('Prologue', ['prologue']),
            ('Odyssey', ['odyssey']),
        ]
    },
    'Subaru': {
        'aliases': ['subaru', 'subarusoa', 'sne'],
        'models': [
            ('Outback', ['outback']),
            ('Forester', ['forester']),
            ('Crosstrek Hybrid', ['crosstrek hybrid', 'crosstrekhybrid']),
            ('Crosstrek', ['crosstrek']),
            ('Ascent', ['ascent']),
            ('Solterra', ['solterra']),
            ('Impreza', ['impreza']),
            ('Legacy', ['legacy']),
            ('WRX', ['wrx', 'wrx sti']),
            ('BRZ', ['brz']),
        ]
    },
    'Hyundai': {
        'aliases': ['hyundai'],
        'models': [
            ('Palisade', ['palisade']),
            ('Santa Fe Hybrid', ['santa fe hybrid', 'santafe hybrid']),
            ('Santa Fe', ['santa fe', 'santafe', 'santa-fe']),
            ('Tucson Hybrid', ['tucson hybrid']),
            ('Tucson', ['tucson']),
            ('Kona Electric', ['kona electric', 'kona ev']),
            ('Kona', ['kona']),
            ('Ioniq 5', ['ioniq 5', 'ioniq5']),
            ('Ioniq 6', ['ioniq 6', 'ioniq6']),
            ('Elantra', ['elantra']),
            ('Sonata', ['sonata']),
            ('Santa Cruz', ['santa cruz', 'santacruz']),
            ('Venue', ['venue']),
        ]
    },
    'Kia': {
        'aliases': ['kia'],
        'models': [
            ('Telluride', ['telluride']),
            ('Sportage Hybrid', ['sportage hybrid']),
            ('Sportage', ['sportage']),
            ('Sorento Hybrid', ['sorento hybrid']),
            ('Sorento', ['sorento']),
            ('Carnival', ['carnival']),
            ('EV9', ['ev9', 'ev-9']),
            ('EV6', ['ev6', 'ev-6']),
            ('Seltos', ['seltos']),
            ('Forte', ['forte']),
            ('K5', ['kia k5', 'k5']),
            ('K4', ['kia k4', 'k4']),
            ('Soul', ['soul']),
            ('Niro', ['niro']),
        ]
    },
    'Nissan': {
        'aliases': ['nissan'],
        'models': [
            ('Rogue', ['rogue']),
            ('Pathfinder', ['pathfinder']),
            ('Frontier', ['frontier']),
            ('Altima', ['altima']),
            ('Sentra', ['sentra']),
            ('Ariya', ['ariya']),
            ('Armada', ['armada']),
            ('Murano', ['murano']),
            ('Kicks', ['kicks']),
            ('Titan', ['titan']),
            ('Versa', ['versa']),
            ('Z', ['nissan z', '370z', '400z']),
        ]
    },
    'Buick': {
        'aliases': ['buick'],
        'models': [
            ('Enclave', ['enclave']),
            ('Encore GX', ['encore gx', 'encore-gx']),
            ('Encore', ['encore']),
            ('Envision', ['envision']),
            ('Envista', ['envista']),
        ]
    },
    'Cadillac': {
        'aliases': ['cadillac'],
        'models': [
            ('Escalade ESV', ['escalade esv', 'escalade-esv']),
            ('Escalade IQ', ['escalade iq', 'escalade-iq']),
            ('Escalade', ['escalade']),
            ('Lyriq', ['lyriq']),
            ('Celestiq', ['celestiq']),
            ('Optiq', ['optiq']),
            ('Vistiq', ['vistiq']),
            ('XT4', ['xt4']),
            ('XT5', ['xt5']),
            ('XT6', ['xt6']),
            ('CT4', ['ct4']),
            ('CT5', ['ct5']),
        ]
    },
    'Lincoln': {
        'aliases': ['lincoln'],
        'models': [
            ('Navigator L', ['navigator l']),
            ('Navigator', ['navigator']),
            ('Aviator', ['aviator']),
            ('Corsair', ['corsair']),
            ('Nautilus', ['nautilus']),
        ]
    },
    'Mercedes-Benz': {
        'aliases': ['mercedes-benz', 'mercedes', 'mercedesbenz', 'mb'],
        'models': [
            ('G-Class', ['g-class', 'g-wagon', 'g550', 'g63']),
            ('GLS', ['gls-class', 'gls450', 'gls580', 'gls']),
            ('GLE', ['gle-class', 'gle350', 'gle450', 'gle53', 'gle']),
            ('GLC', ['glc-class', 'glc300', 'glc43', 'glc']),
            ('GLB', ['glb-class', 'glb250', 'glb']),
            ('GLA', ['gla-class', 'gla250', 'gla']),
            ('S-Class', ['s-class', 's500', 's580']),
            ('E-Class', ['e-class', 'e350', 'e450']),
            ('C-Class', ['c-class', 'c300', 'c43']),
            ('CLA', ['cla-class', 'cla250', 'cla']),
            ('EQE', ['eqe']),
            ('EQS', ['eqs']),
            ('Sprinter', ['sprinter']),
        ]
    },
    'BMW': {
        'aliases': ['bmw'],
        'models': [
            ('X7', ['x7', 'bmw x7']),
            ('X5', ['x5', 'bmw x5']),
            ('X3', ['x3', 'bmw x3']),
            ('X1', ['x1', 'bmw x1']),
            ('X4', ['x4', 'bmw x4']),
            ('X6', ['x6', 'bmw x6']),
            ('3 Series', ['3 series', '330i', 'm340i', 'm3']),
            ('4 Series', ['4 series', '430i', 'm440i', 'm4']),
            ('5 Series', ['5 series', '530i', '540i', 'm5']),
            ('7 Series', ['7 series', '740i', '760i', 'i7']),
            ('i4', ['bmw i4', 'i4']),
            ('iX', ['bmw ix', 'ix']),
        ]
    },
    'Volvo': {
        'aliases': ['volvo', 'vcna'],
        'models': [
            ('XC90', ['xc90', 'xc 90']),
            ('XC60', ['xc60', 'xc 60']),
            ('XC40', ['xc40', 'xc 40']),
            ('EX90', ['ex90', 'ex 90']),
            ('EX30', ['ex30', 'ex 30']),
            ('S60', ['s60']),
            ('S90', ['s90']),
            ('V60', ['v60']),
            ('V90', ['v90']),
        ]
    },
    'Mazda': {
        'aliases': ['mazda'],
        'models': [
            ('CX-90', ['cx-90', 'cx90']),
            ('CX-70', ['cx-70', 'cx70']),
            ('CX-50', ['cx-50', 'cx50']),
            ('CX-5', ['cx-5', 'cx5']),
            ('CX-30', ['cx-30', 'cx30']),
            ('Mazda3', ['mazda3', 'mazda 3']),
            ('Miata', ['miata', 'mx-5', 'mx5']),
        ]
    },
    'Volkswagen': {
        'aliases': ['volkswagen', 'vw'],
        'models': [
            ('Atlas Cross Sport', ['atlas cross sport', 'atlas-cross-sport']),
            ('Atlas', ['atlas']),
            ('Tiguan', ['tiguan']),
            ('Taos', ['taos']),
            ('ID.4', ['id.4', 'id4']),
            ('ID.Buzz', ['id.buzz', 'idbuzz']),
            ('Jetta', ['jetta']),
            ('Golf GTI', ['golf gti', 'gti']),
            ('Golf R', ['golf r']),
        ]
    },
    'Acura': {
        'aliases': ['acura'],
        'models': [
            ('MDX', ['mdx']),
            ('RDX', ['rdx']),
            ('Integra', ['integra']),
            ('TLX', ['tlx']),
            ('ZDX', ['zdx']),
        ]
    }
}

YEAR_REGEX = re.compile(r'\b(201\d|202\d|2030)\b')

CATEGORY_RULES = {
    'service': [
        'oil change', 'tire rotation', 'service center', 'certified service', 'brake service', 'brake repair',
        'wheel alignment', 'battery replacement', 'transmission service', 'maintenance', 'technician', 'technicians',
        'auto repair', 'fixed ops', 'parts department', 'oem parts', 'genuine accessories', 'filter replacement',
        'inspection', 'express lane', 'multi-point inspection', 'collision center', 'body shop', 'schedule service',
        'repair shop', 'certified technician', 'auto service', 'mechanic', 'routine maintenance', 'wiper blade',
        'brake pads', 'brake inspection', 'tire balance', 'coolant flush', 'spark plug', 'service specials',
        'service-0', 'service-1', 'parts.jpg', 'service.jpg'
    ],
    'lifestyle': [
        'lifestyle', 'adventure', 'family', 'road trip', 'camping', 'outdoor', 'outdoors', 'explore',
        'exploring', 'vacation', 'weekend getaway', 'recreation', 'hiking', 'nature', 'pets', 'dogs',
        'scenic', 'journey', 'active lifestyle', 'beach', 'mountain', 'snow', 'skiing', 'kayak', 'paddleboard',
        'tailgate party', 'tailgating', 'commute', 'city driving', 'open road', 'traveling', 'travel'
    ],
    'performance': [
        'horsepower', 'engine', 'torque', 'towing', 'towing capacity', 'payload', 'transmission', 'mpg',
        '4x4', 'awd', '4wd', 'ecoboost', 'v6', 'v8', 'suspension', 'off-road', 'off road', 'handling',
        'turbo', 'turbocharged', 'supercharged', 'drivetrain', 'capability', 'hemi', 'tremec', 'z71',
        'raptor', 'trd', 'acceleration', 'skid plate', 'all-terrain', 'terrain management', 'crawling',
        'lockers', 'differential', 'exhaust', 'paddle shifters', 'sport mode', 'trail rated', 'dynamic driving'
    ],
    'interior': [
        'cabin', 'seat', 'seats', 'seating', 'leather', 'cargo', 'cargo space', 'cargo volume', 'legroom',
        'dashboard', 'interior', 'steering wheel', 'upholstery', 'center console', 'panoramic sunroof',
        'moonroof', 'sunroof', 'headroom', 'comfort', 'cockpit', 'heated seats', 'ventilated seats',
        'dual-zone', 'passenger volume', 'cupholders', 'armrest', 'fold-flat', 'third row', '3rd row',
        'captain chairs', 'ambient lighting'
    ],
    'exterior': [
        'grille', 'wheel', 'wheels', 'body styling', 'led headlight', 'led taillight', 'headlights',
        'taillights', 'paint', 'roof rails', 'bumper', 'styling', 'exterior', 'design', 'tires', 'doors',
        'tailgate', 'power liftgate', 'hands-free liftgate', 'fascia', 'color options', 'silhouette',
        'spoiler', 'rims', 'alloy wheels', 'body lines', 'side mirrors', 'black accent', 'chrome accent'
    ],
    'technology': [
        'touchscreen', 'apple carplay', 'android auto', 'infotainment', 'uconnect', 'sync 4', 'sync',
        'bluetooth', 'wireless charging', 'navigation', 'gps', 'display screen', 'speaker', 'speakers',
        'wifi hotspot', 'wi-fi', 'sound system', 'digital cluster', 'instrument cluster', 'bose',
        'harman kardon', 'bang & olufsen', 'head-up display', 'hud', 'usb-c', 'digital key', 'audio system'
    ],
    'safety': [
        'airbag', 'airbags', 'blind spot', 'blind-spot', 'automatic braking', 'emergency braking',
        'lane assist', 'lane keep', 'lane departure', 'collision', 'adaptive cruise', 'safety',
        'backup camera', 'rear camera', '360-degree camera', 'surround view', 'parking sensor',
        'sensors', 'cross traffic', 'forward collision', 'pre-collision', 'eyesight', 'co-pilot360',
        'safety sense', 'pedestrian detection', 'driver alert', 'driver assistance', 'safety shield'
    ],
    'trims': [
        'trim level', 'available trims', 'trim options', 'big bend', 'outer banks', 'badlands', 'wildtrak',
        'rubicon', 'sahara', 'sport s', 'tradesman', 'bighorn', 'big horn', 'laramie', 'limited',
        'xlt', 'lariat', 'king ranch', 'platinum', 'overland', 'elevation', 'denali', 'at4', 'trailhawk',
        'trail boss', 'rst', 'ltz', 'high country', 'gt line', 'type r', 'nismo', 'trd pro', 'edition'
    ]
}

def classify_metadata(image_url, surrounding_text="", alt_text="", section_title="", page_url="", page_title="", h1_text="", dealer_id=""):
    """
    Unified, hierarchical classifier for vehicle asset metadata.
    Returns: (year, make, model, condition, category)
    """
    url_str = (image_url or '').strip()
    url_low = url_str.lower()
    alt_low = (alt_text or '').lower()
    title_low = (section_title or '').lower()
    text_low = (surrounding_text or '').lower()
    page_url_low = (page_url or '').lower()
    page_title_low = (page_title or '').lower()
    h1_low = (h1_text or '').lower()
    dealer_low = (dealer_id or '').lower()

    # 1. Condition (New, Used, General)
    condition = 'general'
    cond_corpus = f"{page_url_low} {page_title_low} {h1_low} {alt_low} {title_low}"
    if any(k in cond_corpus for k in ['/used-', 'used ', 'pre-owned', 'certified used', 'preowned']):
        condition = 'used'
    elif any(k in cond_corpus for k in ['/new-', 'new ', 'brand new']):
        condition = 'new'

    # 2. Year Detection (Priority: URL filename/path -> title/alt -> text -> page_url)
    year = ''
    for src in [url_str, section_title, alt_text, page_url, surrounding_text, page_title]:
        if not src:
            continue
        m = YEAR_REGEX.search(str(src))
        if m:
            year = m.group(1)
            break

    # 3. Make & Model Detection
    found_make = 'unknown'
    found_model = 'unknown'

    # Priority A: Check direct dealer.com dbcreative taxonomy path
    # e.g. Automotive Brands/GMC/2023/Terrain/SLT/
    dbcreative_m = re.search(r'Automotive Brands/([^/]+)/(?:(\d{4})/)?([^/]+)', url_str, re.I)
    if dbcreative_m:
        brand_raw = dbcreative_m.group(1).strip()
        for mk, data in AUTO_TAXONOMY.items():
            if brand_raw.lower() in [mk.lower()] + data['aliases']:
                found_make = mk
                break
        model_candidate = dbcreative_m.group(3).strip()
        if model_candidate and not model_candidate.startswith('_'):
            for mk, data in AUTO_TAXONOMY.items():
                for can_model, aliases in data['models']:
                    if any(a == model_candidate.lower() or a in model_candidate.lower() for a in aliases):
                        found_make = mk
                        found_model = can_model
                        break
                if found_model != 'unknown':
                    break

    # Priority B: Check Focused context (Alt Text + Section Title + Image URL filename)
    filename = url_str.split('?')[0].split('/')[-1].lower()
    focused_corpus = f"{alt_low} {title_low} {filename}"
    general_corpus = f"{focused_corpus} {page_url_low} {page_title_low} {h1_low} {text_low}"

    if found_make == 'unknown' or found_model == 'unknown':
        for mk, data in AUTO_TAXONOMY.items():
            make_matched = any(alias in general_corpus for alias in [mk.lower()] + data['aliases'])
            if not make_matched and dealer_low:
                make_matched = any(alias in dealer_low for alias in [mk.lower()] + data['aliases'])

            # Look for models
            for can_model, aliases in data['models']:
                # Search focused first
                if any(re.search(rf'\b{re.escape(a)}\b', focused_corpus) for a in aliases):
                    found_make = mk
                    found_model = can_model
                    break
                # Search general corpus
                elif any(re.search(rf'\b{re.escape(a)}\b', general_corpus) for a in aliases):
                    found_make = mk
                    found_model = can_model
                    break

            if found_model != 'unknown':
                break
            elif make_matched and found_make == 'unknown':
                found_make = mk

    # 4. Category Scoring (Prioritizing Lifestyle & Service)
    scores = {cat: 0 for cat in CATEGORY_RULES}
    
    # Strong image URL hints
    if '_lifestyle' in url_low or '-lifestyle-' in url_low or 'lifestyle' in filename:
        scores['lifestyle'] += 15
    if '_fixed ops' in url_low or '/service/' in url_low or '-service-' in url_low or 'service.' in filename or 'parts.' in filename:
        scores['service'] += 15

    for cat, kws in CATEGORY_RULES.items():
        for kw in kws:
            if kw in alt_low or kw in title_low:
                scores[cat] += 4
            elif kw in text_low:
                scores[cat] += 1
            if kw in url_low:
                scores[cat] += 3

    best_cat = max(scores, key=scores.get)
    category = best_cat if scores[best_cat] > 0 else 'general'

    return year, found_make, found_model, condition, category

TRACKING_DOMAINS = [
    'doubleclick.net', 'googleadservices.com', 'getclicky.com', 'adform.net',
    'crwdcntrl.net', 'statistinamics.com', 'doublesmart.digital', 'fzlnk.com',
    'matchmyip.com', 'tidaltv.com', 'w55c.net', 'everesttech.net', 'adnxs.com',
    'bat.bing.com', 'collective-media.net', 'facebook.com', 'scorecardresearch.com',
    'quantserve.com', 'rubiconproject.com', 'criteo.com', 'statcounter.com'
]

def is_junk_asset(url):
    if not url:
        return True
    u_low = url.lower()
    if any(td in u_low for td in TRACKING_DOMAINS):
        return True
    # If no image extension and not a dealer picture service
    if not any(ext in u_low for ext in ['.jpg', '.jpeg', '.png', '.webp', '.avif', 'impolicy=', 'pictures.dealer.com', 'images.dealer.com', 'pictures.web.dealer.com']):
        return True
    return False

def run_reclassification(db_path=None):
    if not db_path:
        db_path = os.path.join(os.path.dirname(__file__), 'image_bank.db')

    print(f"\n=======================================================")
    print(f"  IMAGE BANK MIGRATION & RECLASSIFICATION ENGINE")
    print(f"=======================================================")
    print(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure schema has 'year'
    cursor.execute("PRAGMA table_info(image_assets)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'year' not in cols:
        print("[SCHEMA] Adding 'year' column to image_assets...")
        cursor.execute("ALTER TABLE image_assets ADD COLUMN year TEXT DEFAULT ''")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_asset_year ON image_assets(year)")
        conn.commit()

    # Fetch all assets with their primary occurrence page_url
    cursor.execute('''
        SELECT a.id, a.image_url, a.year, a.make, a.model, a.condition, a.category,
               a.surrounding_text, a.alt_text, a.section_title, a.dealer_id,
               o.page_url
        FROM image_assets a
        LEFT JOIN (
            SELECT image_url, page_url FROM image_occurrences GROUP BY image_url
        ) o ON a.image_url = o.image_url
    ''')
    assets = cursor.fetchall()
    
    # Filter and delete junk/tracking pixels
    junk_ids = [a['id'] for a in assets if is_junk_asset(a['image_url'])]
    if junk_ids:
        print(f"[CLEANUP] Removing {len(junk_ids)} tracking pixel/junk assets...")
        cursor.executemany("DELETE FROM image_assets WHERE id = ?", [(jid,) for jid in junk_ids])
        conn.commit()
        assets = [a for a in assets if a['id'] not in set(junk_ids)]

    total = len(assets)
    print(f"[INFO] Loaded {total} genuine image assets for reclassification...\n")

    updated_count = 0
    stats_after = {'makes': 0, 'models': 0, 'years': 0, 'categories': {}}

    batch_updates = []
    for asset in assets:
        old_id = asset['id']
        url = asset['image_url']
        
        year, make, model, condition, category = classify_metadata(
            image_url=url,
            surrounding_text=asset['surrounding_text'] or '',
            alt_text=asset['alt_text'] or '',
            section_title=asset['section_title'] or '',
            page_url=asset['page_url'] or '',
            dealer_id=asset['dealer_id'] or ''
        )

        # Fallback to existing make/model if previous had valid data and new is unknown
        final_make = make if make != 'unknown' else (asset['make'] or 'unknown')
        final_model = model if model != 'unknown' else (asset['model'] or 'unknown')
        final_year = year if year else (asset['year'] or '')
        final_condition = condition if condition != 'general' else (asset['condition'] or 'general')
        final_category = category if category != 'general' else (asset['category'] or 'general')

        # Track stats
        if final_make != 'unknown': stats_after['makes'] += 1
        if final_model != 'unknown': stats_after['models'] += 1
        if final_year: stats_after['years'] += 1
        stats_after['categories'][final_category] = stats_after['categories'].get(final_category, 0) + 1

        batch_updates.append((final_year, final_make, final_model, final_condition, final_category, old_id))
        updated_count += 1

    # Execute batch updates
    print("[PROCESSING] Applying metadata updates to database...")
    cursor.executemany('''
        UPDATE image_assets
        SET year = ?, make = ?, model = ?, condition = ?, category = ?
        WHERE id = ?
    ''', batch_updates)
    conn.commit()
    conn.close()

    print(f"\n[OK] Reclassification complete! Updated {updated_count} assets.")
    print("-------------------------------------------------------")
    print(f"Total Assets in Bank:  {total}")
    print(f"Makes Identified:      {stats_after['makes']} ({stats_after['makes']/total*100:.1f}%)")
    print(f"Models Identified:     {stats_after['models']} ({stats_after['models']/total*100:.1f}%)")
    print(f"Years Identified:      {stats_after['years']} ({stats_after['years']/total*100:.1f}%)")
    print("\nCategory Distribution:")
    for cat, cnt in sorted(stats_after['categories'].items(), key=lambda x: x[1], reverse=True):
        print(f"  * {cat.capitalize():<14}: {cnt} images ({cnt/total*100:.1f}%)")
    print("=======================================================\n")
    return stats_after

if __name__ == '__main__':
    run_reclassification()
