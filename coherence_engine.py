"""
coherence_engine.py
===================
Local NLP semantic coherence engine for automotive SEO QA.
Replaces the Gemini API dependency entirely.

Core functions:
  - analyze_coherence(url, title, path, page_text): score the semantic alignment
  - nlp_inventory_fallback(url, page_title, nav_links, learned_examples):
      SAFE deterministic fallback when local_inventory_inference() returns None.
      Never hallucinates models or brands — only uses what's in the URL.

Model: all-MiniLM-L6-v2 — fast (80ms/doc), ~80MB, no GPU needed.
"""

import re
import json
from urllib.parse import urlparse

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ---------------------------------------------------------------------------
# Global model — loaded once at server startup, reused for every request.
# ---------------------------------------------------------------------------
MODEL_NAME = 'all-MiniLM-L6-v2'
_model = None

def _get_model():
    global _model
    if _model is None:
        print(f"[CoherenceEngine] Loading '{MODEL_NAME}'...")
        try:
            _model = SentenceTransformer(MODEL_NAME)
            print("[CoherenceEngine] Model ready.")
        except Exception as e:
            print(f"[CoherenceEngine] WARNING: Could not load model: {e}")
    return _model


# ---------------------------------------------------------------------------
# Automotive domain context — helps anchor the embedding space.
# ---------------------------------------------------------------------------
_DOMAIN_HINTS = {
    'new-inventory': 'new vehicles for sale new car inventory',
    'used-inventory': 'used pre-owned vehicles for sale',
    'certified-inventory': 'certified pre-owned CPO vehicles',
    'bargain': 'affordable bargain used pre-owned vehicles for sale under',
    'pre-owned': 'used pre-owned vehicles for sale',
    'service': 'auto service repair maintenance oil change',
    'parts': 'auto parts accessories OEM',
    'finance': 'auto financing car loan credit application',
    'specials': 'deals offers discounts promotions incentives',
    'about': 'about us dealership team staff',
    'contact': 'contact us directions hours phone',
    'research': 'research compare vehicles models specs',
    'compare': 'vehicle comparison models features specs',
}

def _build_meta_text(title: str, path: str) -> str:
    """
    Constructs a rich metadata string by appending domain-hint keywords
    that match the URL path, so the embedding space stays automotive-aware.
    """
    path_lower = path.lower()
    hints = []
    for key, phrase in _DOMAIN_HINTS.items():
        if key in path_lower:
            hints.append(phrase)
    
    # Humanize the slug (path minus extension and leading slash)
    slug = path_lower.replace('.htm', '').replace('.html', '')
    slug = re.sub(r'[/_-]', ' ', slug).strip()
    
    parts = [f"Title: {title}", f"Page type: {slug}"]
    if hints:
        parts.append("Context: " + ". ".join(hints))
    
    return ". ".join(parts)


# ---------------------------------------------------------------------------
# Primary coherence analyzer
# ---------------------------------------------------------------------------
def analyze_coherence(url: str, title: str, page_text: str) -> dict:
    """
    Scores how well the page's metadata (Title + URL path) matches its
    actual visible text content.

    Args:
        url:        Full URL of the page.
        title:      H1 or page title (from the scan).
        page_text:  Plain-text content of the page (e.g. soup.get_text()).

    Returns:
        {
            "score":        int 0-100,
            "explanation":  str  (1 sentence, human-readable),
            "status":       "coherent" | "suspicious" | "incoherent"
        }
    """
    model = _get_model()
    if not model:
        return {
            "score": None,
            "explanation": "NLP coherence model unavailable. Check server logs.",
            "status": "error"
        }

    path = urlparse(url).path

    if not page_text or len(page_text.strip()) < 80:
        return {
            "score": None,
            "explanation": "Not enough page text to evaluate semantic coherence.",
            "status": "error"
        }

    meta_text = _build_meta_text(title, path)
    # Cap content — model max seq is 256 tokens ≈ 1500 chars
    content_snippet = page_text[:1800]

    try:
        emb = model.encode([meta_text, content_snippet], show_progress_bar=False)
        raw_score = float(cosine_similarity([emb[0]], [emb[1]])[0][0])
        # Cosine similarity can be negative; clamp to [0, 1]
        score = max(0.0, min(1.0, raw_score))
        
        # Scale score for display (since Cosine Sim between title/path and 1500 chars of prose rarely exceeds 0.75)
        display_score = min(100, int((score / 0.75) * 100))

        if display_score >= 60:
            status = "coherent"
            explanation = (
                f"Excellent semantic alignment ({display_score}%). "
                "The page content strongly matches the Title and URL path intent."
            )
        else:
            # Calculate missing keywords for better feedback when score is medium/low
            path_slug = urlparse(url).path.lower().replace('.htm', '').replace('.html', '')
            path_slug = re.sub(r'[/_-]', ' ', path_slug).strip()
            combined_text = f"{title.lower()} {path_slug}"
            words = set(re.findall(r'\b[a-z]{3,}\b', combined_text))
            stop_words = {'for', 'sale', 'new', 'used', 'the', 'and', 'with', 'inventory', 'index', 'page', 'cars', 'vehicles', 'dealership', 'auto', 'from', 'your', 'our', 'are', 'this', 'that'}
            important_words = words - stop_words
            
            page_text_lower = page_text.lower()
            missing_words = [w for w in important_words if w not in page_text_lower]
            
            missing_str = ""
            if missing_words:
                missing_str = f" Missing key terms: {', '.join(missing_words)}."
                
            if display_score >= 40:
                status = "suspicious"
                explanation = (
                    f"Partial alignment ({display_score}%). "
                    f"Some content may not fully match the declared page category.{missing_str}"
                )
            else:
                status = "incoherent"
                explanation = (
                    f"Low alignment ({display_score}%). "
                    f"The text on the page does not seem to match the Title or URL.{missing_str}"
                )

        return {"score": display_score, "explanation": explanation, "status": status}

    except Exception as e:
        print(f"[CoherenceEngine] Embedding error: {e}")
        return {
            "score": None,
            "explanation": f"Internal NLP error: {e}",
            "status": "error"
        }


# ---------------------------------------------------------------------------
# NLP Inventory Fallback — SAFE DETERMINISTIC VERSION
# ---------------------------------------------------------------------------
# NOTE: The previous embedding-based fallback was removed because it would
# hallucinate models/makes from learned examples (e.g. returning
# "make=Jeep&model=Grand%20Cherokee" on a Ford Bronco page).
# This version is strictly logic-based: it only uses signals found in the URL
# and nav links, and NEVER invents a model or brand.
# ---------------------------------------------------------------------------

_BODY_STYLES_SIMPLE = {
    'truck': 'Truck', 'trucks': 'Truck', 'pickup': 'Truck',
    'suv': 'SUV', 'suvs': 'SUV', 'crossover': 'SUV',
    'sedan': 'Sedan', 'sedans': 'Sedan',
    'coupe': 'Coupe',
    'van': 'Van', 'minivan': 'Van',
    'convertible': 'Convertible',
    'hatchback': 'Hatchback',
    'wagon': 'Wagon',
}

def nlp_inventory_fallback(
    url: str,
    page_title: str,
    nav_links: list,
    learned_examples: list,
) -> str | None:
    """
    SAFE deterministic fallback when local_inventory_inference() returns None.

    Logic:
    1. Determine inventory type (new/used/certified) from URL path, title, or nav.
    2. Try to find a body style from the URL slug only.
    3. Returns the simplest matching filter URL — NEVER invents model or brand.
    4. Returns None if signals are insufficient.

    Args:
        url:              Full URL of the page being audited.
        page_title:       Browser/document title.
        nav_links:        List of dicts: [{"text": ..., "href": ...}, ...]
        learned_examples: (unused — kept for API compatibility)

    Returns:
        A relative filter path string or None.
    """
    path = urlparse(url).path.lower()
    title_low = (page_title or '').lower()

    # --- 1. Determine inventory type ---
    is_new  = any(k in path for k in ['/new-', '/new/', 'new-inventory', 'new-cars', 'new-vehicles']) or \
              any(k in title_low for k in ['new ', 'new vehicle', 'new car', 'nuevo'])
    is_used = any(k in path for k in ['/used-', '/pre-owned', 'used-inventory', 'preowned']) or \
              any(k in title_low for k in ['used ', 'pre-owned', 'preowned'])
    is_cert = any(k in path for k in ['/certified', '/cpo']) or 'certified' in title_low

    # Year clue (2024-2027 in path = new model year = new inventory)
    if not is_new and not is_used and not is_cert:
        if re.search(r'/(202[3-9]|203\d)', path):
            is_new = True

    # Nav-based clue: if nav only has new-inventory and no used-inventory
    if not is_new and not is_used and not is_cert:
        nav_hrefs = [l.get('href', '').lower() for l in (nav_links or []) if l.get('href')]
        has_new_nav  = any('/new-inventory' in h for h in nav_hrefs)
        has_used_nav = any('/used-inventory' in h for h in nav_hrefs)
        if has_new_nav and not has_used_nav:
            is_new = True

    # Choose base path
    if is_cert:
        base = '/certified-inventory/index.htm'
    elif is_used:
        base = '/used-inventory/index.htm'
    elif is_new:
        base = '/new-inventory/index.htm'
    else:
        # Cannot determine inventory type — safer to return None
        print("[CoherenceEngine] Deterministic fallback: cannot determine inventory type -> None")
        return None

    # --- 2. Try body style from slug ONLY ---
    slug = path.replace('.htm', '').replace('.html', '').replace('-', ' ').replace('/', ' ')
    slug_norm = f" {slug.strip()} "

    found_body = None
    for key, val in _BODY_STYLES_SIMPLE.items():
        if f" {key} " in slug_norm:
            found_body = val
            break

    # --- 3. Build result ---
    if found_body:
        result = f"{base}?normalBodyStyle={found_body}"
        print(f"[CoherenceEngine] Deterministic fallback -> {result}")
        return result

    # Return plain inventory base only if the page is clearly inventory-related
    if 'inventory' in path or any('inventory' in l.get('href', '') for l in (nav_links or [])):
        print(f"[CoherenceEngine] Deterministic fallback -> {base} (generic)")
        return base

    print("[CoherenceEngine] Deterministic fallback: insufficient signals -> None")
    return None


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Test coherence
    fake_text = (
        "Welcome to our Toyota dealership. Browse our wide selection of new "
        "Toyota Camry, RAV4, and Highlander vehicles. Get great deals today!"
    )
    result = analyze_coherence(
        "https://www.example-toyota.com/new-inventory/toyota-rav4.htm",
        "New Toyota RAV4 for Sale",
        fake_text,
    )
    print(json.dumps(result, indent=2))

    # Test safe deterministic fallback
    nav = [
        {"text": "New Inventory", "href": "/new-inventory/index.htm"},
        {"text": "Used Inventory", "href": "/used-inventory/index.htm"},
    ]
    res = nlp_inventory_fallback(
        "https://www.example-ford.com/2026-ford-bronco.htm",
        "2026 Ford Bronco",
        nav,
        [],
    )
    print("Inventory fallback:", res)
