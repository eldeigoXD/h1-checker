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

from ollama_client import ask_ollama_json, is_ollama_available

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
    "x3": "X3", "x5": "X5", "x7": "X7",
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
    """
    text_lower = text.lower()
    found = []
    for key, name in _MODEL_SLUG_MAP.items():
        # Match key or canonical name (lowercased)
        if key in text_lower or name.lower() in text_lower:
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

    # Check if model name or a reasonable alias appears in text
    if model_lower in text_lower:
        return None  # All good

    # Look for other models that ARE mentioned in text
    conflicting = extract_models_from_text(page_text)
    # Filter out partial matches (e.g. "Silverado 1500" page mentioning "Sierra" is OK)
    conflicting = [m for m in conflicting if m.lower() != model_lower]

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

CRITICAL CONSTRAINTS TO AVOID FALSE POSITIVES:
1. Do NOT report that content is "cut off" or "incomplete". You are only seeing an 800-character snippet by design.
2. Do NOT flag multi-brand mentions as an error if they could be part of the dealership's name (e.g. "Buick GMC").
3. Do NOT claim a keyword (like 'EV') is missing from the title if it is actually present in the provided Page Title or H1.
4. If url_model is 'Unknown', do not force a model mismatch if the content aligns with the general URL path (e.g. '/ev-san-antonio.htm' matching EV content).
"""


def llm_semantic_check(
    url: str,
    h1: str,
    page_text: str,
    page_title: str = "",
    rag_context: str = "",
    model: str = "phi3:mini",
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

    # Layer 2: LLM deep check
    # Only run when we have a known model in the URL — otherwise the LLM
    # has no concrete ground-truth to compare against and hallucinates issues.
    if run_llm and is_ollama_available() and url_model:
        # Pre-check: if the url_model is clearly mentioned in title or h1,
        # we already have a verified match. Any LLM claim that the model
        # is "not mentioned" or "absent from title/H1" is a hallucination.
        url_model_lower = url_model.lower()
        title_low = (page_title or "").lower()
        h1_low    = (h1 or "").lower()
        model_in_title_or_h1 = url_model_lower in title_low or url_model_lower in h1_low

        llm_result = llm_semantic_check(
            url=url,
            h1=h1,
            page_text=page_text,
            page_title=page_title,
            rag_context=rag_context,
        )
        result["llm"] = llm_result

        if llm_result.get("verdict") in ("warning", "bug"):
            # Filter out false-positive meta-complaints before surfacing
            real_issues = []
            for iss in llm_result.get("issues", []):
                if not iss:
                    continue
                if _is_false_positive_issue(iss):
                    continue
                # If model is clearly in title/H1, filter any LLM claim it is missing
                if model_in_title_or_h1:
                    iss_low = iss.lower()
                    if any(fp in iss_low for fp in [
                        "not explicitly mention", "does not mention", "not mentioned",
                        "not in the title", "absent from", "missing from",
                        "not present in", "not found in title", "not found in h1",
                        "dilutes focus",  # content is on-topic, LLM overflagging
                        "wide variety",   # generic LLM complaint about multi-section content
                    ]):
                        print(f"[SemanticQA] Suppressed hallucinated issue (model '{url_model}' IS in title/H1): {iss}")
                        continue
                real_issues.append(iss)

            if real_issues:
                result["combined_verdict"] = llm_result["verdict"]
                result["combined_issues"].extend(real_issues)
            # If all issues were false positives, keep verdict as 'ok'

    return result


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
