"""
semantic_qa.py
==============
Deep semantic QA reasoning engine for automotive dealer pages.

Layer 1 (fast): all-MiniLM-L6-v2 cosine scoring — always runs (coherence_engine.py)
Layer 2 (deep): Local LLM reasoning via Ollama — runs in background thread, ~3-10s

This module provides Layer 2.

Key capability over Layer 1:
  It can detect NAMED ENTITY mismatches — e.g. a Silverado 2500 URL with
  Equinox EV body copy — which cosine similarity CANNOT detect because
  the semantic space treats all vehicles as similar.

Architecture:
  - Each check is wrapped in a try/except so a crash never breaks the main scan.
  - Results are returned as structured dicts compatible with the bugs[] list.
  - If Ollama is not running, all functions return safe defaults immediately.
"""

import re
import json
import threading
from typing import Optional
from urllib.parse import urlparse

from ollama_client import ask_ollama_json, is_ollama_available, DEFAULT_MODEL

# ---------------------------------------------------------------------------
# Automotive model entity extractor (fast, no LLM needed)
# ---------------------------------------------------------------------------
# Maps URL slug tokens → canonical model names for ground-truth comparison

_MODEL_SLUG_MAP = {
    # Chevrolet
    "silverado-1500": "Silverado 1500", "silverado-2500": "Silverado 2500 HD",
    "silverado-3500": "Silverado 3500 HD", "equinox": "Equinox", "equinox-ev": "Equinox EV",
    "blazer": "Blazer", "blazer-ev": "Blazer EV", "traverse": "Traverse",
    "colorado": "Colorado", "tahoe": "Tahoe", "suburban": "Suburban",
    "trailblazer": "Trailblazer", "malibu": "Malibu", "camaro": "Camaro",
    "corvette": "Corvette", "trax": "Trax", "spark": "Spark",
    # Ford
    "f-150": "F-150", "f-250": "F-250 Super Duty", "f-350": "F-350 Super Duty",
    "explorer": "Explorer", "escape": "Escape", "edge": "Edge",
    "bronco": "Bronco", "bronco-sport": "Bronco Sport", "mustang": "Mustang",
    "mustang-mache": "Mustang Mach-E", "maverick": "Maverick", "ranger": "Ranger",
    # Ram
    "ram-1500": "Ram 1500", "ram-2500": "Ram 2500", "ram-3500": "Ram 3500",
    "promaster": "ProMaster",
    # Dodge
    "challenger": "Challenger", "charger": "Charger", "durango": "Durango",
    "hornet": "Hornet",
    # Jeep
    "wrangler": "Wrangler", "grand-cherokee": "Grand Cherokee",
    "cherokee": "Cherokee", "compass": "Compass", "renegade": "Renegade",
    "gladiator": "Gladiator",
    # Toyota
    "camry": "Camry", "corolla": "Corolla", "rav4": "RAV4", "highlander": "Highlander",
    "tacoma": "Tacoma", "tundra": "Tundra", "4runner": "4Runner",
    "prius": "Prius", "sienna": "Sienna", "venza": "Venza",
    # Honda
    "civic": "Civic", "accord": "Accord", "cr-v": "CR-V", "pilot": "Pilot",
    "odyssey": "Odyssey", "ridgeline": "Ridgeline",
    # Nissan
    "altima": "Altima", "sentra": "Sentra", "rogue": "Rogue",
    "murano": "Murano", "pathfinder": "Pathfinder", "frontier": "Frontier",
    "titan": "Titan", "armada": "Armada",
    # Hyundai
    "elantra": "Elantra", "sonata": "Sonata", "tucson": "Tucson",
    "santa-fe": "Santa Fe", "palisade": "Palisade", "ioniq-5": "IONIQ 5",
    "ioniq-6": "IONIQ 6", "ioniq-9": "IONIQ 9",
    # Kia
    "optima": "Optima", "k5": "K5", "forte": "Forte", "sportage": "Sportage",
    "sorento": "Sorento", "telluride": "Telluride", "ev6": "EV6", "ev9": "EV9",
    # Lexus
    "es-350": "ES 350", "is-350": "IS 350", "gx": "GX", "gx-550": "GX 550",
    "nx-350": "NX 350", "rx-350": "RX 350", "rx-500h": "RX 500h",
    "rz-350e": "RZ 350e", "tx": "TX", "tx-350": "TX 350", "ux-300h": "UX 300h",
    # BMW
    "3-series": "3 Series", "5-series": "5 Series", "7-series": "7 Series",
    "x1": "X1", "x2": "X2", "x3": "X3", "x4": "X4", "x5": "X5", "x6": "X6", "x7": "X7", "xm": "XM",
    "m2": "M2", "m3": "M3", "m4": "M4", "m5": "M5", "m8": "M8",
    "i4": "i4", "i5": "i5", "i7": "i7", "ix": "iX",
    # Mercedes
    "c-class": "C-Class", "e-class": "E-Class", "gle": "GLE", "glc": "GLC",
    # Cadillac
    "escalade": "Escalade", "ct5": "CT5", "ct4": "CT4", "xt5": "XT5", "xt6": "XT6",
    "lyriq": "LYRIQ", "optiq": "OPTIQ",
    # GMC
    "sierra-1500": "Sierra 1500", "sierra-2500": "Sierra 2500 HD",
    "sierra-3500": "Sierra 3500 HD", "canyon": "Canyon",
    "yukon": "Yukon", "terrain": "Terrain", "acadia": "Acadia",
    "hummer-ev": "HUMMER EV",
    # Buick
    "enclave": "Enclave", "encore": "Encore", "envision": "Envision",
    "envista": "Envista",
    # Lincoln
    "navigator": "Navigator", "aviator": "Aviator", "nautilus": "Nautilus",
    "corsair": "Corsair", "continental": "Continental", "mkz": "MKZ",
    "mkc": "MKC", "mkx": "MKX", "mkt": "MKT",
    # Subaru
    "outback": "Outback", "forester": "Forester", "impreza": "Impreza",
    "legacy": "Legacy", "ascent": "Ascent", "wrx": "WRX", "brz": "BRZ",
    "crosstrek": "Crosstrek",
    # Volkswagen
    "jetta": "Jetta", "passat": "Passat", "tiguan": "Tiguan",
    "atlas": "Atlas", "id4": "ID.4",
    # Audi
    "a3": "A3", "a4": "A4", "a6": "A6", "q3": "Q3", "q5": "Q5", "q7": "Q7",
    "e-tron": "e-tron", "q4-e-tron": "Q4 e-tron",
}


def extract_model_from_url(url: str) -> Optional[str]:
    """
    Extracts the vehicle model name from a URL slug.
    Returns canonical model name string or None if not detected.
    """
    path = urlparse(url).path.lower()
    slug = path.replace("/", " ").replace("_", "-").strip()

    for key, name in _MODEL_SLUG_MAP.items():
        if key in slug:
            return name

    return None


def extract_models_from_text(text: str) -> list[str]:
    """
    Finds all known vehicle model names mentioned in page text.
    Returns list of canonical model names.
    Uses word boundaries and cleans common automotive phrases that cause false positives.
    """
    text_clean = text.lower()
    # Strip common automotive phrases that falsely trigger model names
    text_clean = re.sub(r'\b(?:all|rough|any)[-\s]terrain\b|\bterrain\s+(?:tires?|modes?)\b', ' ', text_clean)
    text_clean = re.sub(r'\b(?:pro|co|auto)[-\s]?pilot\b', ' ', text_clean)
    text_clean = re.sub(r'\b(?:phone|wireless|battery|turbo|super|ev|fast)[-\s]?charger\b', ' ', text_clean)
    text_clean = re.sub(r'\bspark\s+plugs?\b', ' ', text_clean)
    text_clean = re.sub(r'\b(?:cutting|leading)[-\s]?edge\b', ' ', text_clean)
    
    found = []
    for key, name in _MODEL_SLUG_MAP.items():
        pattern = rf'\b(?:{re.escape(name.lower())}|{re.escape(key)})\b'
        if re.search(pattern, text_clean):
            if name not in found:
                found.append(name)
    return found


# ---------------------------------------------------------------------------
# Quick deterministic cross-check (no LLM needed)
# ---------------------------------------------------------------------------

def deterministic_model_check(url: str, page_text: str) -> Optional[dict]:
    """
    FAST check: extracts model from URL and looks for it in page text.
    Returns a warning dict if a mismatch is strongly detected, None otherwise.

    This runs WITHOUT Ollama and is always active.
    """
    url_model = extract_model_from_url(url)
    if not url_model:
        return None  # Can't check without a known model in URL

    text_lower = page_text.lower()
    model_lower = url_model.lower()

    # Check if model name or base model name (e.g. "Silverado 2500" for "Silverado 2500 HD") appears in text
    import re as _re_model
    base_model = _re_model.sub(r'\b(hd|super duty|ev)\b', '', model_lower).strip()
    if model_lower in text_lower or (base_model and base_model in text_lower):
        return None  # All good

    # On comparison pages (/compare/...) multiple models are expected
    if '/compare' in url.lower():
        return None

    # Look for other models that ARE mentioned in text
    conflicting = extract_models_from_text(page_text)
    # Filter out partial matches (e.g. "Silverado 1500" page mentioning "Sierra" is OK)
    conflicting = [m for m in conflicting if m.lower() != model_lower and (not base_model or m.lower() != base_model)]

    if not conflicting:
        return None  # No conflict detected

    return {
        "type":    "semantic_model_mismatch",
        "level":   "warning",
        "url_model": url_model,
        "found_models": conflicting[:5],
        "message": (
            f"URL suggests '{url_model}' content, but this model was NOT found on the page. "
            f"Content may reference other models: {', '.join(conflicting[:3])}."
        ),
    }


# ---------------------------------------------------------------------------
# LLM deep semantic check (runs in background thread)
# ---------------------------------------------------------------------------

_SEMANTIC_SYSTEM = (
    "You are an expert QA specialist for automotive dealer websites. "
    "You analyze pages for semantic correctness and content integrity. "
    "You ALWAYS respond in valid JSON only. No explanations outside the JSON."
)

_SEMANTIC_PROMPT_TEMPLATE = """\
Analyze this automotive dealer landing page for semantic correctness.

URL: {url}
Page Title: {title}
H1: {h1}
URL suggests this vehicle model: {url_model}
Content models mentioned in page: {content_models}

Page content (first 800 chars):
{content_snippet}

{rag_context}

Respond ONLY with this JSON structure:
{{
  "verdict": "ok" | "warning" | "bug",
  "score": <integer 0-100>,
  "model_match": true | false,
  "issues": ["<concise issue description>", ...],
  "explanation": "<one sentence summary>"
}}

Rules:
- verdict "ok": content clearly matches URL intent and vehicle model. If URL suggests a generic category (e.g. EV, used) and content matches, it's "ok".
- verdict "warning": partial mismatch, could be intentional.
- verdict "bug": clear mismatch — URL says one model but content discusses a different model.
- issues: list specific semantic problems found, max 3 items, empty array if none.
- score 90-100 = perfect match, 70-89 = good, 50-69 = warning, below 50 = bug.

EXAMPLES OF WHAT IS VALID (DO NOT REPORT AS BUGS):
- Example 1: URL has 'trax', Title or H1 has 'Chevrolet Trax', and content discusses Trax or mentions other dealership models (like Silverado in navigation or related inventory). Verdict: "ok", score: 95, issues: []. (Dealerships routinely list multiple models in inventory bars or headers).
- Example 2: Category page (e.g. /used-cars-lincolnton-nc.htm or /managers-specials.htm) listing several inventory models. Verdict: "ok", score: 90, issues: [].

EXAMPLES OF REAL BUGS (REPORT THESE):
- Example 3: URL specifies '/new-inventory/chevrolet-corvette.htm' but Title, H1, and entire text ONLY discuss 'Silverado 1500' with ZERO mentions of Corvette. Verdict: "bug", score: 30, model_match: false, issues: ["Page content discusses Silverado 1500 instead of Corvette"].

CRITICAL CONSTRAINTS TO AVOID FALSE POSITIVES:
1. Do NOT report that content is "cut off" or "incomplete". You are only seeing an 800-character snippet by design.
2. Do NOT flag multi-brand mentions as an error if they could be part of the dealership's name (e.g. "Buick GMC").
3. Do NOT claim a keyword (like 'EV' or model name) is missing from the title if it is actually present in the provided Page Title or H1.
4. If url_model is 'Unknown', do not force a model mismatch if the content aligns with the general URL path (e.g. '/ev-san-antonio.htm' matching EV content).
5. If the URL model is mentioned in the H1, Title, or content, the verdict MUST be 'ok'. Dealership websites routinely feature other models in navigation menus, footer links, or cross-shopping references — this is NOT a model mismatch.
6. Do NOT mistake automotive features (like 'all-terrain tires', 'ProPILOT Assist', or 'wireless charger') for vehicle models.
"""


def llm_semantic_check(
    url: str,
    h1: str,
    page_text: str,
    page_title: str = "",
    rag_context: str = "",
    model: str = DEFAULT_MODEL,
    timeout: int = 40,
) -> dict:
    """
    Sends page metadata + content to local LLM for deep semantic analysis.

    Returns:
        {
            "verdict":     "ok" | "warning" | "bug" | "skipped",
            "score":       int 0-100,
            "issues":      list[str],
            "explanation": str,
            "source":      "llm" | "skipped",
        }
    """
    default_result = {
        "verdict": "skipped",
        "score": None,
        "issues": [],
        "explanation": "LLM semantic check skipped (Ollama not available).",
        "source": "skipped",
    }

    if not is_ollama_available():
        return default_result

    try:
        url_model      = extract_model_from_url(url) or "Unknown"
        content_models = extract_models_from_text(page_text)
        content_snippet = page_text[:800].strip()

        prompt = _SEMANTIC_PROMPT_TEMPLATE.format(
            url=url,
            title=page_title or h1,
            h1=h1,
            url_model=url_model,
            content_models=", ".join(content_models[:8]) if content_models else "none detected",
            content_snippet=content_snippet,
            rag_context=rag_context or "",
        )

        raw = ask_ollama_json(
            prompt=prompt,
            system=_SEMANTIC_SYSTEM,
            model=model,
            timeout=timeout,
            default={},
        )

        if not raw:
            return default_result

        return {
            "verdict":     raw.get("verdict", "ok"),
            "score":       raw.get("score"),
            "model_match": raw.get("model_match", True),
            "issues":      raw.get("issues", []),
            "explanation": raw.get("explanation", ""),
            "source":      "llm",
        }

    except Exception as e:
        print(f"[SemanticQA] LLM check error: {e}")
        return {**default_result, "explanation": f"LLM error: {e}"}


# ---------------------------------------------------------------------------
# Combined check — runs both layers and merges results
# ---------------------------------------------------------------------------

# Keywords that signal a false-positive LLM issue (meta-complaints, not real content bugs)
_FP_ISSUE_PHRASES = [
    "cut off", "truncated", "incomplete", "snippet", "without specif",
    "does not automatically", "url suggests 'unknown'", "url model is unknown",
    "cannot determine", "not enough context", "h1 title only says",
    "h1 only says", "title only says",
]


def _is_false_positive_issue(issue_text: str) -> bool:
    """Returns True if the LLM issue string is a known false-positive meta-complaint."""
    low = issue_text.lower()
    return any(fp in low for fp in _FP_ISSUE_PHRASES)


def run_semantic_check(
    url: str,
    h1: str,
    page_text: str,
    page_title: str = "",
    rag_context: str = "",
    run_llm: bool = True,
) -> dict:
    """
    Runs both the fast deterministic check and (optionally) the LLM deep check.

    The deterministic check always runs.
    The LLM check runs ONLY if:
      - Ollama is available
      - run_llm=True
      - The URL contains a known vehicle model (url_model is not None)
        because without a concrete model anchor, the LLM produces vague
        meta-complaints instead of real semantic errors.

    Returns a merged result dict.
    """
    url_model = extract_model_from_url(url)

    result = {
        "deterministic": None,
        "llm": None,
        "combined_verdict": "ok",
        "combined_issues": [],
        "url_model": url_model,
    }

    # Layer 1: Fast deterministic check (always runs)
    det = deterministic_model_check(url, page_text)
    result["deterministic"] = det
    if det:
        result["combined_issues"].append(det["message"])
        result["combined_verdict"] = "warning"

    # Layer 2: Model Frequency Counter & Ground-Truth Verification
    if url_model:
        url_model_lower = url_model.lower()
        title_low = (page_title or "").lower()
        h1_low    = (h1 or "").lower()
        text_low  = (page_text or "").lower()

        # Clean text of generic automotive phrases
        text_clean = text_low
        text_clean = re.sub(r'\b(?:all|rough|any)[-\s]terrain\b|\bterrain\s+(?:tires?|modes?)\b', ' ', text_clean)
        text_clean = re.sub(r'\b(?:pro|co|auto)[-\s]?pilot\b', ' ', text_clean)
        text_clean = re.sub(r'\b(?:phone|wireless|battery|turbo|super|ev|fast)[-\s]?charger\b', ' ', text_clean)
        text_clean = re.sub(r'\bspark\s+plugs?\b', ' ', text_clean)
        text_clean = re.sub(r'\b(?:cutting|leading)[-\s]?edge\b', ' ', text_clean)

        model_in_title_or_h1 = url_model_lower in title_low or url_model_lower in h1_low
        target_count = len(re.findall(rf'\b{re.escape(url_model_lower)}\b', text_clean))

        # Count all other known vehicle models in page text
        other_model_counts = {}
        for key, name in _MODEL_SLUG_MAP.items():
            if name.lower() == url_model_lower:
                continue
            if name in other_model_counts:
                continue
            pat = rf'\b{re.escape(name.lower())}\b'
            cnt = len(re.findall(pat, text_clean))
            if cnt > 0:
                other_model_counts[name] = cnt

        max_other_count = max(other_model_counts.values()) if other_model_counts else 0
        top_other_model = max(other_model_counts, key=other_model_counts.get) if other_model_counts else None

        # --- DETERMINISTIC GROUND TRUTH RESOLUTION ---
        # Rule 1: If target model is confirmed in Title or H1 (and by definition in URL):
        # The page is 100% verified as targeting this model. Dealerships routinely mention other
        # models in inventory facet filters, header dropdowns, or comparisons. This is NEVER a bug.
        if model_in_title_or_h1:
            result["combined_verdict"] = "ok"
            result["combined_issues"] = []
            return result

        # Rule 2: If target model is dominant in page text (target_count >= 2 and target_count >= max_other_count):
        if target_count >= 2 and target_count >= max_other_count:
            result["combined_verdict"] = "ok"
            result["combined_issues"] = []
            return result

        # Rule 3: If target model is completely absent (0 mentions) and another model dominates heavily (>= 5 mentions):
        if target_count == 0 and max_other_count >= 5 and top_other_model:
            result["combined_verdict"] = "warning"
            result["combined_issues"] = [
                f"URL suggests '{url_model}' content, but page primarily features '{top_other_model}' ({max_other_count} mentions)."
            ]
            return result

        # Rule 4: If counts are close / ambiguous, consult LLM if available
        if run_llm and is_ollama_available():
            llm_result = llm_semantic_check(
                url=url,
                h1=h1,
                page_text=page_text,
                page_title=page_title,
                rag_context=rag_context,
            )
            result["llm"] = llm_result

            if llm_result.get("verdict") in ("warning", "bug"):
                real_issues = []
                for iss in llm_result.get("issues", []):
                    if not iss or _is_false_positive_issue(iss):
                        continue
                    iss_low = iss.lower()

                    # Suppress false positives if target model has mentions or if another model was just in facet
                    if target_count > 0 and any(fp in iss_low for fp in [
                        "focus", "generic", "lacks", "without", "misleading", "mention", "different models", "other models"
                    ]):
                        continue

                    real_issues.append(iss)

                if real_issues:
                    result["combined_verdict"] = llm_result["verdict"]
                    result["combined_issues"].extend(real_issues)
                else:
                    result["combined_verdict"] = "ok"

    return result

# ---------------------------------------------------------------------------
# CTA & Brand Coherence Auditor (Deterministic + LLM)
# ---------------------------------------------------------------------------

ALL_AUTO_MAKES = {
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
    'bmw': 'BMW', 'mini': 'MINI', 'mercedes': 'Mercedes-Benz', 'mercedes-benz': 'Mercedes-Benz',
    'volvo': 'Volvo', 'jaguar': 'Jaguar', 'land rover': 'Land Rover', 'landrover': 'Land Rover',
    'mitsubishi': 'Mitsubishi', 'alfa romeo': 'Alfa Romeo', 'porsche': 'Porsche',
}

def is_utility_or_compliance_link(text: str, href: str) -> bool:
    """
    Returns True for standard website utility links that should NEVER be audited
    as marketing CTAs or flagged for label-to-destination semantic incoherence:
    - Privacy Policy, Terms, Compliance (e.g. ComplyAuto), Disclaimers
    - Directions, Maps (Google Maps, Mapquest, Waze, Apple Maps), Dealership Address
    - Contact Us, Hours, Phone numbers, Tel/Mailto
    - Accessibility, Sitemap, Opt-out / Do Not Sell
    """
    t_low = (text or '').lower().strip()
    h_low = (href or '').lower().strip()
    if not t_low and not h_low:
        return True

    # 1. Text checks
    if any(k in t_low for k in [
        'privacy policy', 'privacy', 'terms of use', 'terms of service', 'terms & conditions',
        'terms and conditions', 'disclaimer', 'compliance', 'cookie policy', 'cookies',
        'directions', 'get directions', 'hours & directions', 'hours and directions',
        'hours', 'store hours', 'sales hours', 'service hours', 'parts hours',
        'visit us', 'visit our', 'address', 'location', 'accessibility', 'sitemap',
        'site map', 'do not sell', 'your privacy choices', 'contact us', 'contact',
        'call us', 'call now', 'phone', 'freight charge', 'freight charges',
        'destination charge', 'destination charges', 'destination freight', 'handling charge',
        'handling charges', 'freight/destination'
    ]):
        return True

    # Home / root navigation
    if t_low in ('home', 'homepage', 'home page', 'back to top', 'top'):
        return True

    # Address link with street / hwy / zip (e.g. "Visit us at: 1801 Highway 69 Trumann, AR 72472")
    if any(k in t_low for k in [
        'highway', 'hwy', 'street', 'st.', 'blvd', 'avenue', 'ave', 'road', 'rd.',
        'route', 'rt.', 'parkway', 'pkwy', 'drive', 'dr.', 'way', 'lane', 'ln.', 'suite', 'ste'
    ]) and any(c.isdigit() for c in t_low):
        return True

    # 2. Href checks
    if h_low in ('/', '/index.htm', '/index.html'):
        return True

    if any(k in h_low for k in [
        'privacy-policy', 'privacy', 'terms', 'disclaimer', 'complyauto', 'compliance',
        'directions', 'google.com/maps', 'maps.google.com', 'goo.gl/maps', 'waze.com',
        'apple.com/maps', 'maps.apple.com', 'bing.com/maps', 'mapquest.com',
        'sitemap.xml', 'sitemap.htm', 'accessibility',
        'facebook.com', 'twitter.com', 'x.com', 'instagram.com', 'youtube.com', 'linkedin.com'
    ]) or h_low.startswith('tel:') or h_low.startswith('mailto:'):
        return True

    return False

def is_standard_valid_cta(text: str, href: str) -> bool:
    """
    Returns True if the button text and href represent a standard, completely coherent
    automotive navigation pattern that should NOT be flagged as a mismatch or sent to LLM.
    e.g. "Home" -> /index.htm
         "New Inventory" -> /new-inventory/index.htm
         "Used Inventory" -> /used-inventory/index.htm
         "New Vehicles" -> /new-inventory/
         "Shop New" -> /new-inventory/
         "Certified Pre-Owned" -> /certified-inventory/
         "Contact Us" -> /contact.htm
         "Schedule Service" -> /schedule-service.htm
    """
    if not text or not href:
        return False
    t_low = text.lower().strip()
    h_low = href.lower().strip()

    # 0. Root / Home link alignment
    if t_low in ('home', 'homepage', 'home page') or h_low in ('/', '/index.htm', '/index.html'):
        return True

    # 1. New inventory alignment
    if any(k in t_low for k in [
        'new inventory', 'new vehicle', 'new car', 'new truck', 'new suv',
        'shop new', 'view new', 'browse new', 'search new',
        'new chevrolet', 'new chevy', 'new ford', 'new toyota', 'new honda',
        'new nissan', 'new jeep', 'new ram', 'new dodge', 'new gmc', 'new buick',
        'new cadillac', 'new hyundai', 'new kia', 'new subaru', 'new mazda'
    ]):
        if any(k in h_low for k in ['new-inventory', '/new-', '/new/', 'new-vehicles', 'new-cars']):
            return True

    # 2. Used inventory alignment
    if any(k in t_low for k in [
        'used inventory', 'used vehicle', 'used car', 'used truck', 'used suv',
        'shop used', 'view used', 'browse used', 'search used',
        'pre-owned', 'preowned', 'certified pre-owned', 'cpo'
    ]):
        if any(k in h_low for k in ['used-inventory', '/used-', '/used/', 'pre-owned', 'preowned', 'certified']):
            return True

    # 3. Model-specific inventory alignment (e.g. "Shop Trax" -> URL containing "trax")
    for slug, name in _MODEL_SLUG_MAP.items():
        if slug in h_low or name.lower() in h_low:
            if slug in t_low or name.lower() in t_low:
                return True

    # 4. Standard department alignment
    if 'service' in t_low and 'service' in h_low:
        return True
    if ('financ' in t_low) and ('financ' in h_low):
        return True
    if 'part' in t_low and 'part' in h_low:
        return True
    if 'special' in t_low and 'special' in h_low:
        return True
    if 'schedule' in t_low and ('schedule' in h_low or 'service' in h_low):
        return True
    if 'contact' in t_low and 'contact' in h_low:
        return True
    if 'direction' in t_low and 'direction' in h_low:
        return True
    if 'center' in t_low and 'center' in h_low:
        return True

    # 5. EV / Hybrid / Electric inventory alignment
    if any(k in t_low for k in ['ev', 'hybrid', 'electric', 'phev', 'electrified']):
        if any(k in h_low for k in ['ev', 'hybrid', 'hybird', 'electric', 'phev', 'electrified']):
            return True

    return False

_CTA_COHERENCE_SYSTEM = (
    "You are an expert QA auditor for automotive dealership websites. "
    "Analyze CTA buttons and links for severe brand contradictions, syntax incoherence, and misleading destinations. "
    "Respond ONLY in valid JSON."
)

_CTA_COHERENCE_PROMPT = """\
Dealership Brand: {main_brand}
Allowed Brands for this site: {allowed_brands}
Page URL: {url}

Actionable Marketing Buttons and Links to analyze:
{ctas_json}

Evaluate if any CTA button:
1. Mentions a competitor brand/make NOT allowed for this dealership (e.g. Subaru on a Ford site). This is a CRITICAL bug.
2. Has incoherent wording vs destination URL (e.g. 'New' text pointing to /used-inventory/).
3. Has broken syntax or obvious typos.

EXAMPLES OF COMPLETELY VALID CTAS (DO NOT REPORT AS BUGS):
- "Home" -> "/index.htm" (Standard root navigation, 100% VALID)
- "New Inventory" -> "/new-inventory/index.htm" (Standard, coherent, valid)
- "Used Inventory" -> "/used-inventory/index.htm" (Standard, coherent, valid)
- "Schedule Service" -> "/service/schedule-service.htm" (Standard, coherent, valid)
- "Contact Us" -> "/contact.htm" (Standard, coherent, valid)
- "Shop Trax" -> "/new-inventory/index.htm?model=Trax" (Standard, coherent, valid)
- "BMW XM" -> "/new-inventory/index.htm?model=XM" (Model names as button text are 100% VALID)
- "new BMW portfolio" -> "/new-inventory/index.htm" (Portfolio/lineup buttons are 100% VALID)
- "finance center" -> "/financing/center.htm" (Department & finance links are 100% VALID)
- "View EV/Hybrid Inventory" -> "/new-inventory/hyundai-hybird-evs-for-sale.htm" (EV and Hybrid inventory links are 100% VALID)
- "Get Pre-Qualified" -> "/finance.htm" (Standard, coherent, valid)

EXAMPLES OF REAL BUGS (REPORT THESE):
- "Shop New Ford" on a Chevrolet dealer site -> type: "cta_brand_mismatch", level: "red", message: "Ford CTA on Chevrolet website"
- "Browse New Inventory" -> "/used-inventory/index.htm" -> type: "cta_syntax_mismatch", level: "yellow", message: "Button text says New but destination is Used inventory"
- "Schdule Servce" -> type: "cta_typo", level: "red", message: "Spelling errors in button label"

CRITICAL CONSTRAINTS TO PREVENT FALSE POSITIVES:
- Do NOT report on standard navigation labels like 'Home', 'Directions', 'Contact Us', 'Hours', 'About Us', or 'Privacy Policy'.
- NEVER claim standard, correctly spelled words like 'Home' are typos or spelling errors.
- NEVER report typos inside destination URLs or URL paths (e.g. '/hyundai-hybird-evs-for-sale.htm'). URL paths are existing site pages and are NOT button label typos. Only evaluate spelling inside the button's visible text.
- Do NOT flag EV / Hybrid buttons (e.g. 'View EV/Hybrid Inventory') as errors or ambiguities when pointing to EV / hybrid pages.
- NEVER complain about capitalization, uppercase, or lowercase (e.g. 'finance center' vs 'Finance Center'). Both lowercase linked text in SEO content and title-case buttons are standard and NEVER typos or bugs.
- NEVER complain that a button label lacks an action verb (e.g. 'BMW XM' instead of 'Shop BMW XM' or 'new BMW portfolio' instead of 'Browse New BMW Portfolio'). Noun-based and model-based button labels are standard automotive practice and are NEVER typos or bugs.
- A 'cta_typo' is ONLY for genuinely misspelled English words (e.g. 'inventroy', 'shcedule'). Suggesting alternative wording, action verbs, or phrasing is NEVER a typo.
- Do NOT report on address or map links (e.g. Google Maps).
- Do NOT complain that normal automotive CTA buttons (e.g. 'New Inventory', 'New Ford Inventory', 'Get Pre-Qualified') are 'vague', 'redundant', or lack brand names.
- Do NOT report general inventory buttons (like 'New Inventory' -> '/new-inventory/index.htm') appearing on specific model pages. Dealerships always include site-wide inventory buttons.

Respond ONLY with this JSON:
{{
  "issues": [
    {{
      "text": "<button text>",
      "href": "<button href>",
      "type": "cta_brand_mismatch" | "cta_syntax_mismatch" | "cta_typo",
      "level": "red" | "yellow",
      "message": "<clear explanation of why this is an error>"
    }}
  ]
}}
"""


def audit_cta_and_brand_coherence(
    url: str,
    main_brand: Optional[str],
    allowed_brands: set[str],
    ctas: list[dict],
    requested_ctas: list[dict] = None,
    run_llm: bool = True,
) -> list[dict]:
    """
    Audits CTA buttons on the page for:
    1. Competitor brand contradictions (e.g. 'View New Subaru Inventory' on a Ford site)
    2. Syntax/Destination incoherence ('New' text pointing to /used-inventory/)
    3. Typos in CTA button labels
    4. Corrupted versions of requested CTAs

    Returns list of issue dicts.
    """
    issues = []
    seen_keys = set()

    # Normalize allowed brands
    normalized_allowed = {b.lower() for b in allowed_brands} if allowed_brands else set()
    if main_brand:
        normalized_allowed.add(main_brand.lower())

    other_makes = [m for k, m in ALL_AUTO_MAKES.items() if m.lower() not in normalized_allowed and len(m) > 2]

    # --- Pass 1: Deterministic Check (Immediate, 100% reliable) ---
    for item in ctas:
        txt = (item.get('text') or '').strip()
        href = (item.get('href') or '').strip()
        if not txt or not href:
            continue
        # In-page anchors (#inv, #contact, #learn) are local scroll targets, not external CTAs
        if href.startswith('#') or href.startswith(('javascript:', 'mailto:', 'tel:')):
            continue
        if is_utility_or_compliance_link(txt, href):
            continue

        txt_low = txt.lower()
        href_low = href.lower()

        # A. Brand contradiction check
        if normalized_allowed:
            for ob in other_makes:
                ob_low = ob.lower()
                # Check for competitor brand in button text or destination URL
                if re.search(rf'\b{re.escape(ob_low)}\b', txt_low):
                    # Exclude comparison words and used car sales (dealers legitimately sell used cars of other makes)
                    if any(cmp_w in txt_low for cmp_w in [' vs ', 'compare', 'competitor', 'used ', 'pre-owned ', 'preowned ', 'trade']):
                        continue
                    msg = f"Critical Brand Contradiction: Button '{txt}' references competitor brand '{ob}' on a {main_brand or 'dealership'} website."
                    key = (txt, 'brand_mismatch')
                    if key not in seen_keys:
                        seen_keys.add(key)
                        issues.append({
                            "type": "cta_brand_mismatch",
                            "level": "red",
                            "text": txt,
                            "href": href,
                            "brand": ob,
                            "message": msg,
                        })

        # B. Typo check
        typos = {'inventroy': 'inventory', 'specail': 'special', 'fiannce': 'finance', 'shcedule': 'schedule'}
        for t, correct in typos.items():
            if t in txt_low:
                msg = f"Typo detected in CTA: '{t}' instead of '{correct}'"
                key = (txt, 'typo')
                if key not in seen_keys:
                    seen_keys.add(key)
                    issues.append({
                        "type": "cta_typo",
                        "level": "red",
                        "text": txt,
                        "href": href,
                        "message": msg,
                    })

        # C. Destination Syntax / Type Discrepancy
        if 'new' in txt_low and 'used-inventory' in href_low and 'new-inventory' not in href_low:
            msg = f"Incoherent CTA: 'New' text in '{txt}' points to Used inventory URL ({href})."
            key = (txt, 'syntax_mismatch')
            if key not in seen_keys:
                seen_keys.add(key)
                issues.append({
                    "type": "cta_syntax_mismatch",
                    "level": "yellow",
                    "text": txt,
                    "href": href,
                    "message": msg,
                })
        elif 'used' in txt_low and 'new-inventory' in href_low and 'used-inventory' not in href_low:
            msg = f"Incoherent CTA: 'Used' text in '{txt}' points to New inventory URL ({href})."
            key = (txt, 'syntax_mismatch')
            if key not in seen_keys:
                seen_keys.add(key)
                issues.append({
                    "type": "cta_syntax_mismatch",
                    "level": "yellow",
                    "text": txt,
                    "href": href,
                    "message": msg,
                })

    # --- Pass 2: LLM Deep Semantic Check (Ollama) ---
    if run_llm and is_ollama_available() and ctas:
        try:
            # Send sample of actionable marketing CTAs to Ollama (filter out utility, compliance, standard coherent, and empty/hash links)
            sample_ctas = [
                {'text': c.get('text', '')[:60], 'href': c.get('href', '')[:80]}
                for c in ctas
                if c.get('text')
                and not c.get('href', '').startswith('#')
                and c.get('href') not in ('#', '', 'javascript:void(0)', 'javascript:;')
                and not is_utility_or_compliance_link(c.get('text', ''), c.get('href', ''))
                and not is_standard_valid_cta(c.get('text', ''), c.get('href', ''))
            ][:10]

            if sample_ctas:
                prompt = _CTA_COHERENCE_PROMPT.format(
                    main_brand=main_brand or "Automotive Dealership",
                    allowed_brands=", ".join(sorted(allowed_brands)) if allowed_brands else (main_brand or "N/A"),
                    url=url,
                    ctas_json=json.dumps(sample_ctas, indent=2),
                )
                llm_resp = ask_ollama_json(
                    prompt=prompt,
                    system=_CTA_COHERENCE_SYSTEM,
                    timeout=20,
                    default={},
                )
                if isinstance(llm_resp, dict) and "issues" in llm_resp:
                    for iss in llm_resp.get("issues", []):
                        iss_txt = (iss.get("text") or "").strip()
                        iss_msg = (iss.get("message") or "").strip()
                        iss_href = (iss.get("href") or "").strip()
                        iss_type = iss.get("type", "cta_semantic_issue")
                        iss_level = iss.get("level", "yellow")

                        if not iss_txt and not iss_href:
                            continue
                        if is_utility_or_compliance_link(iss_txt, iss_href):
                            continue
                        if is_standard_valid_cta(iss_txt, iss_href):
                            print(f"[SemanticQA] Suppressed hallucinated issue on standard coherent CTA '{iss_txt}' -> '{iss_href}': {iss_msg}")
                            continue
                        if iss_href in ('#', '', 'javascript:void(0)', 'javascript:;'):
                            continue

                        # If LLM claims brand mismatch, STRICTLY VERIFY that an actual competitor brand exists
                        if "brand" in iss_type.lower() or "brand" in iss_msg.lower():
                            detected_competitor = None
                            for ob in other_makes:
                                if re.search(rf'\b{re.escape(ob.lower())}\b', iss_txt.lower()) or re.search(rf'\b{re.escape(ob.lower())}\b', iss_href.lower()):
                                    detected_competitor = ob
                                    break
                            if not detected_competitor:
                                print(f"[SemanticQA] Suppressed hallucinated brand contradiction on '{iss_txt}': no competitor brand found.")
                                continue

                        # Strictly verify syntax mismatch claims from LLM
                        iss_msg_low = iss_msg.lower()
                        txt_l = iss_txt.lower()
                        hrf_l = iss_href.lower()
                        if "syntax" in iss_type.lower() or "mismatch" in iss_type.lower() or any(w in iss_msg_low for w in ['incoherent', 'does not match', 'wording']):
                            if ('new' in txt_l and 'new' in hrf_l) or \
                               ('used' in txt_l and ('used' in hrf_l or 'pre-owned' in hrf_l)) or \
                               ('inventory' in txt_l and 'inventory' in hrf_l) or \
                               ('special' in txt_l and 'special' in hrf_l):
                                print(f"[SemanticQA] Suppressed false syntax mismatch on '{iss_txt}' -> '{iss_href}': {iss_msg}")
                                continue
                            has_real_contradiction = ('new' in txt_l and 'used-inventory' in hrf_l and 'new-inventory' not in hrf_l) or \
                                                    ('used' in txt_l and 'new-inventory' in hrf_l and 'used-inventory' not in hrf_l)
                            if not has_real_contradiction and not ("brand" in iss_type.lower() or "typo" in iss_type.lower()):
                                print(f"[SemanticQA] Suppressed unverified syntax claim on '{iss_txt}' -> '{iss_href}': {iss_msg}")
                                continue

                        # Strictly verify typo / spelling error claims from LLM
                        if "typo" in iss_type.lower() or "typo" in iss_msg_low or "spelling" in iss_msg_low:
                            # 0. Suppress typos claimed inside destination URLs or URL paths (author does not control CMS slug)
                            quoted_typos = re.findall(r"['\"]([^'\"]+)['\"]", iss_msg)
                            if quoted_typos and any(qt.lower() in iss_href.lower() and qt.lower() not in iss_txt.lower() for qt in quoted_typos):
                                print(f"[SemanticQA] Suppressed typo claimed in URL slug instead of button text on '{iss_txt}': {iss_msg}")
                                continue
                            if any(part in iss_msg_low for part in ['in url', 'in href', 'in path', 'in destination', '.htm', '.html', 'slug']):
                                print(f"[SemanticQA] Suppressed typo claimed in URL path on '{iss_txt}': {iss_msg}")
                                continue

                            # 1. Suppress capitalization / casing complaints (e.g. 'finance center' should be 'Finance Center', or 'compare' should be 'Compare')
                            diff_match = re.search(r"['\"]([^'\"]+)['\"]\s+should be\s+['\"]([^'\"]+)['\"]", iss_msg, re.IGNORECASE)
                            if diff_match:
                                w1 = diff_match.group(1).strip()
                                w2 = diff_match.group(2).strip()
                                if w1.lower() == w2.lower():
                                    print(f"[SemanticQA] Suppressed word capitalization complaint on '{iss_txt}': {iss_msg}")
                                    continue

                            sugg_match = re.search(r"should be ['\"]([^'\"]+)['\"]", iss_msg, re.IGNORECASE)
                            if sugg_match:
                                sugg_text = sugg_match.group(1).strip()
                                if sugg_text.lower() == iss_txt.lower() or (sugg_text.lower() in iss_txt.lower() and sugg_text.istitle()):
                                    print(f"[SemanticQA] Suppressed case/capitalization complaint on '{iss_txt}': {iss_msg}")
                                    continue

                            # 2. Suppress copywriting / styling suggestions masquerading as typos (e.g. "should be 'Shop BMW XM'")
                            if any(phrase in iss_msg_low for phrase in [
                                "should be 'browse", "should be 'shop", "should be 'view", "should be 'explore",
                                "should be 'search", "should be 'check", "should be 'see", "add an action verb",
                                "missing action verb", "lacks an action verb", "imperative verb", "action verb"
                            ]):
                                print(f"[SemanticQA] Suppressed copywriting suggestion masquerading as typo on '{iss_txt}': {iss_msg}")
                                continue

                            valid_common_words = {
                                'home', 'about', 'contact', 'service', 'parts', 'finance', 'financing', 'center',
                                'new', 'used', 'inventory', 'specials', 'special', 'deals', 'directions', 'hours', 'search',
                                'view', 'shop', 'schedule', 'more', 'details', 'apply', 'get', 'pre-qualified',
                                'quote', 'value', 'trade', 'vehicles', 'cars', 'trucks', 'suvs', 'certified',
                                'call', 'visit', 'find', 'explore', 'drive', 'offers', 'incentives', 'info',
                                'information', 'estimate', 'payment', 'calculator', 'chat', 'message',
                                'portfolio', 'lineup', 'showroom', 'model', 'models', 'trim', 'trims',
                                'compare', 'discover', 'learn', 'see', 'configurations', 'configuration', 'features', 'feature', 'reviews', 'overview',
                                'lincoln', 'nautilus', 'navigator', 'aviator', 'corsair',
                                'selection', 'gallery', 'specs', 'features', 'options', 'warranty', 'lease',
                                'hub', 'desk', 'department', 'dept', 'team', 'group', 'store', 'location', 'facility', 'dealership',
                                'suv', 'sedan', 'coupe', 'truck', 'van', 'wagon', 'convertible', 'hybrid',
                                'electric', 'ev', 'phev', 'diesel', 'gas', 'awd', '4wd', 'fwd', 'rwd',
                                'bmw', 'xm', 'ford', 'chevy', 'chevrolet', 'gmc', 'cadillac', 'buick',
                                'toyota', 'honda', 'nissan', 'jeep', 'ram', 'dodge', 'chrysler', 'kia',
                                'hyundai', 'subaru', 'volkswagen', 'vw', 'audi', 'lexus', 'mazda', 'mercedes',
                                'destination', 'freight', 'charge', 'charges', 'handling', 'pricing', 'price', 'prices',
                                'disclaimer', 'disclaimers', 'fee', 'fees', 'taxes', 'tax', 'title', 'license', 'licensing',
                                'registration', 'dealer', 'processing', 'msrp', 'invoice', 'package', 'packages',
                                'accessories', 'equipment', 'transportation', 'delivery', 'cost', 'costs'
                            }
                            words = [w.strip(" .,!?:;'\"-()[]{}") for w in txt_l.split()]
                            words = [w for w in words if w]
                            if words and all(
                                w in valid_common_words or w in _MODEL_SLUG_MAP or any(w == m.lower() for m in ALL_AUTO_MAKES.values())
                                for w in words
                            ):
                                print(f"[SemanticQA] Suppressed hallucinated typo/spelling on valid text '{iss_txt}': {iss_msg}")
                                continue
                            if quoted_typos and any(qt.lower() in valid_common_words for qt in quoted_typos):
                                print(f"[SemanticQA] Suppressed hallucinated typo on valid word '{quoted_typos}' on '{iss_txt}': {iss_msg}")
                                continue

                        # Suppress pedantic meta-complaints and style suggestions from small LLMs
                        if any(bad_phrase in iss_msg_low for bad_phrase in [
                            'does not mention the dealership brand', 'does not mention dealership',
                            'is vague', 'redundant', 'clicking on a map', 'external link which does not',
                            'repeated twice', 'valid href', 'does not have a valid', 'directs users to a ford',
                            'despite the site', 'focus on ford', 'to clearly indicate', 'preposition',
                            'suggesting incoherent wording', 'does not match its destination',
                            'button\'s text does not match', 'button text does not match',
                            'destination, which is \'/new-inventory', 'destination, which is \'/used-inventory',
                            'misleading wording', 'lacks the specific', 'does not specify'
                        ]):
                            continue
                        key = (iss_txt, iss_type)
                        if key not in seen_keys and iss_msg:
                            seen_keys.add(key)
                            issues.append({
                                "type": iss_type,
                                "level": iss_level,
                                "text": iss_txt,
                                "href": iss_href,
                                "message": iss_msg,
                            })
        except Exception as e:
            print(f"[SemanticQA] CTA LLM check skipped: {e}")

    return issues



# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=== Semantic QA Self-Test ===\n")

    # Test 1: Deterministic — Silverado URL with Equinox text
    print("[Test 1] Silverado URL / Equinox content (should detect mismatch)")
    url1 = "https://www.karlchevrolet.com/new-chevrolet/silverado-2500-ankeny-ia.htm"
    text1 = (
        "Welcome to our dealership. Browse our Equinox EV lineup. "
        "The Equinox EV offers great range and efficiency. "
        "The Blazer EV is also available for purchase."
    )
    det = deterministic_model_check(url1, text1)
    print(json.dumps(det, indent=2))

    # Test 2: Deterministic — correct content
    print("\n[Test 2] Silverado URL / Silverado content (should be clean)")
    text2 = (
        "Browse our new Silverado 2500 HD inventory. "
        "The Silverado 2500 is perfect for heavy-duty work. "
        "Get yours today with special financing!"
    )
    det2 = deterministic_model_check(url1, text2)
    print(f"Result: {det2}  (expected None)")

    # Test 3: Model extraction
    print("\n[Test 3] Model extraction from URL")
    for test_url in [
        "https://example.com/new-lexus/is-350-bakersfield-ca.htm",
        "https://example.com/new-chevrolet/silverado-2500-hd.htm",
        "https://example.com/service/index.htm",
    ]:
        model = extract_model_from_url(test_url)
        print(f"  {test_url.split('/')[-1]} → {model}")

    print("\n✅ Done. Run with Ollama active to test LLM layer.")
