"""
instruction_engine.py
=====================
LLM-powered Instruction Compliance Engine.

Parses natural language instructions into structured requirements and checks 
them against the parsed HTML and text of the page.

Supports graceful fallback: If Ollama is unavailable, returns a flag indicating 
fallback is needed so `app.py` can use its legacy regex logic.
"""

import json
from bs4 import BeautifulSoup
from typing import List, Dict

from ollama_client import ask_ollama_json, is_ollama_available

_PARSE_SYSTEM = (
    "You are an expert technical QA parser for automotive dealership websites. "
    "The user provides a set of layout, inventory configuration, and tone instructions in natural language. "
    "Extract them into a strict JSON object containing requirement rules and inventory overrides. "
    "Output ONLY valid JSON, nothing else."
)

_PARSE_PROMPT = """
Natural Language Instructions: "{instructions}"

Parse the instructions into a JSON object.
Allowed 'type' values for rules:
  - "presence": an element must exist (e.g. breadcrumbs, accordion, inventory widget, hero image, grid layout, list layout, lead form, contact form, imagery/photos).
  - "absence": an element must NOT exist (e.g. remove map, no breadcrumbs).
  - "inventory_config": specific inventory filters requested (e.g. new vehicles under $30,000, used trucks under 20k, Ram 1500).
  - "tone": the writing style to adopt (e.g. urban youthful tone, formal tone).
  - "other": any other instruction.

Output JSON schema:
{{
  "inventory_overrides": {{
    "inventory_type": "new" | "used" | "certified" | null,
    "max_price": 30000 | null,
    "make": null,
    "model": null,
    "body_style": null,
    "layout": "Grid" | "List" | null
  }},
  "rules": [
    {{"type": "inventory_config", "element": "new vehicles under 30000", "original_text": "Please include new vehicles inventory config and filter by vehicles below $30,000"}},
    {{"type": "presence", "element": "imagery", "original_text": "Please put content in sections with modern corresponding imagery"}}
  ]
}}

Respond ONLY with valid JSON.
"""

_TONE_SYSTEM = (
    "You are a tone and writing style evaluator for automotive marketing content. "
    "Respond ONLY in valid JSON format."
)

_TONE_PROMPT = """
Evaluate if the following page content matches the requested tone.
Requested Tone: "{requested_tone}"

Page Content (snippet):
{content_snippet}

Respond ONLY in JSON:
{{
  "match": true | false,
  "reason": "Brief explanation of why it matches or fails."
}}
"""


def parse_instructions(instructions: str) -> tuple[List[Dict], Dict]:
    """
    Uses LLM to parse raw text instructions into a structured array of rules and inventory overrides.
    Returns tuple: (rules_list, inventory_overrides_dict).
    """
    if not is_ollama_available() or not instructions.strip():
        return [], {}
        
    prompt = _PARSE_PROMPT.format(instructions=instructions)
    result = ask_ollama_json(
        prompt=prompt,
        system=_PARSE_SYSTEM,
        default={},
        timeout=20
    )
    
    rules = []
    overrides = {}
    
    if isinstance(result, list):
        rules = result
    elif isinstance(result, dict):
        rules = result.get("rules", [])
        overrides = result.get("inventory_overrides", {})
        
    return rules, overrides



def _check_presence_absence(rule: Dict, soup: BeautifulSoup, is_presence: bool, seo_coverage: int = None, inventory_info: dict = None) -> Dict:
    """Deterministic DOM checks for common widgets based on the requested element."""
    element = rule.get("element", "").lower()
    original_txt = rule.get("original_text", "").lower()
    found = False
    details = ""
    status = "success"
    
    # 1. Photos/Images check
    if "photo" in element or "image" in element or "photo" in original_txt or "image" in original_txt:
        imgs = soup.find_all('img') if soup else []
        found = len(imgs) > 0
        details = f"Images/photos detected on page ({len(imgs)} found)." if found else "No images/photos found."

    # 2. Content check (using seo_coverage if available)
    elif "content" in element or "page content" in element or "content" in original_txt or "page content" in original_txt:
        if seo_coverage is not None and seo_coverage >= 0:
            found = seo_coverage >= 60
            details = f"SEO Content Coverage is {seo_coverage}%." if found else f"SEO Content Coverage is low ({seo_coverage}%)."
        else:
            # Fallback to checking if text is present
            found = len(soup.get_text(strip=True)) > 200 if soup else False
            details = "Page content/text detected on page." if found else "No significant page content found."

    elif "breadcrumb" in element:
        has_schema = bool(soup.find(attrs={'itemtype': lambda x: x and 'BreadcrumbList' in x})) if soup else False
        has_class = bool(soup.find(attrs={'class': lambda x: x and 'breadcrumb' in x.lower()})) if soup else False
        has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'breadcrumb' in x.lower()})) if soup else False
        found = has_schema or has_class or has_widget
        details = "Breadcrumb component detected in DOM." if found else "No breadcrumb component found."
        
    elif "hero" in element:
        has_hero = bool(soup.find(attrs={'class': lambda x: x and 'hero' in x.lower()})) if soup else False
        has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'hero' in x.lower()})) if soup else False
        found = has_hero or has_widget
        details = "Hero component detected." if found else "No hero component found."
        
    elif "accordion" in element or "faq" in element or "accordion" in original_txt or "faq" in original_txt:
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

        if "accordion" in element or "accordion" in original_txt:
            if has_acc:
                found = True
                details = "Accordion widget detected for FAQ section."
            elif has_faq_widget or has_faq_header:
                found = True
                status = "manual_review"
                details = "FAQ section found in plain text/HTML headers, but requested specifically as accordion widget."
            else:
                found = False
                details = "No Accordion or FAQ section found."
        else:
            found = has_acc or has_faq_widget or has_faq_header
            details = "FAQ section detected (Accordion or HTML text)." if found else "No FAQ section found."
        
    elif "map" in element:
        has_map = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'map' in x.lower()})) if soup else False
        has_iframe = bool(soup.find('iframe', src=lambda x: x and 'maps' in x.lower())) if soup else False
        found = has_map or has_iframe
        details = "Map widget/iframe detected." if found else "No map element found."
        
    elif "inventory" in element or "under" in element or "below" in element or "$" in element or "vehicle" in element or "inventory" in original_txt or "under" in original_txt or "below" in original_txt or "$" in original_txt or "vehicle" in original_txt:
        p_cnt = inventory_info.get('page_count') if inventory_info else None
        f_cnt = inventory_info.get('filter_count') if inventory_info else None
        inv_status = inventory_info.get('status') if inventory_info else None
        filter_url = inventory_info.get('filter_url') if inventory_info else ''

        is_mismatch = (inv_status == 'mismatch') or (p_cnt is not None and f_cnt is not None and str(p_cnt) != str(f_cnt))
        if is_mismatch:
            found = False
            status = "error"
            details = f"Inventory Mismatch: Current page shows {p_cnt} vehicles, but requested configuration ({filter_url}) returns {f_cnt} vehicles."
        else:
            found = True
            status = "success"
            details = f"Inventory configuration rule verified against target filter."


    elif "inventory widget" in element:
        # Assuming inventory status will be handled globally, but we can do a quick check
        found = bool(soup.find(attrs={'data-widget-name': lambda x: x and 'inventory' in x.lower()})) if soup else False
        details = "Inventory widget detected in DOM." if found else "No inventory widget found."


        
    elif "grid" in element:
        found = bool(soup.find(attrs={'class': lambda x: x and 'grid' in x.lower()}))
        details = "Grid layout classes detected." if found else "Grid layout not detected."
        
    elif "list" in element:
        found = bool(soup.find(attrs={'class': lambda x: x and 'list' in x.lower()}))
        details = "List layout classes detected." if found else "List layout not detected."
        
    elif "form" in element or "lead" in element or "contact" in element:
        has_form = bool(soup.find('form'))
        has_widget = bool(soup.find(attrs={'data-widget-name': lambda x: x and ('form' in x.lower() or 'lead' in x.lower() or 'contact' in x.lower())}))
        has_class = bool(soup.find(attrs={'class': lambda x: x and ('form' in x.lower() or 'lead' in x.lower() or 'contact' in x.lower())}))
        found = has_form or has_widget or has_class
        details = "Lead/Contact form detected on page." if found else "No lead/contact form found."
        
    else:
        # Vague/Ambiguous keywords (e.g. "service" suelto)
        vague_kws = ['service', 'update', 'photos', 'page content', 'content']
        is_vague = any(vk == element.strip() or vk == original_txt.strip() for vk in vague_kws)
        if is_vague:
            status = "manual_review"
            details = f"Vague/Underspecified clause '{original_txt or element}' requires manual verification."
        else:
            found = element in soup.get_text().lower()
            details = f"Text matching '{element}' found on page." if found else f"Could not find '{element}'."

    # Evaluate compliance
    if status != "manual_review":
        if is_presence:
            status = "success" if found else "error"
            reason = details if details else f"Required element '{element}' is missing."

        else:
            status = "error" if found else "success"
            reason = f"Prohibited element '{element}' was found on the page." if found else f"Prohibited element '{element}' is successfully absent."
    else:
        reason = details

    return {
        "original": rule.get("original_text", f"{'Add' if is_presence else 'Remove'} {element}"),
        "status": status,
        "reason": reason,
        "type": rule.get("type")
    }


def _check_tone(rule: Dict, page_text: str) -> Dict:
    """Uses LLM to evaluate tone."""
    style = rule.get("style", "")
    original = rule.get("original_text", f"Use {style} tone")
    
    if not is_ollama_available():
        return {
            "original": original,
            "status": "manual_review",
            "reason": "Ollama is unavailable. Please verify tone manually.",
            "type": "tone"
        }
        
    prompt = _TONE_PROMPT.format(
        requested_tone=style,
        content_snippet=page_text[:1500]  # First 1500 chars usually sets the tone
    )
    
    result = ask_ollama_json(prompt=prompt, system=_TONE_SYSTEM, timeout=25)
    match = result.get("match", False)
    reason = result.get("reason", "Tone evaluation completed.")
    
    return {
        "original": original,
        "status": "success" if match else "error",
        "reason": reason,
        "type": "tone"
    }


def evaluate_instructions(instructions: str, soup: BeautifulSoup, page_text: str, seo_coverage: int = None, inventory_info: dict = None) -> dict:
    """
    Main entry point. 
    Returns:
    {
       "fallback": bool (True if Ollama is down and caller should use legacy regex),
       "evaluations": list of evaluation results,
       "requires_layout_ui": bool,
       "requires_breadcrumb_ui": bool,
       "inventory_overrides": dict
    }
    """
    if not instructions.strip():
        return {"fallback": False, "evaluations": [], "requires_layout_ui": False, "requires_breadcrumb_ui": False, "inventory_overrides": {}}

    if not is_ollama_available():
        return {"fallback": True, "evaluations": [], "requires_layout_ui": False, "requires_breadcrumb_ui": False, "inventory_overrides": {}}
        
    rules, overrides = parse_instructions(instructions)
    if not rules and not overrides:
        # Parsing failed, fallback to legacy
        return {"fallback": True, "evaluations": [], "requires_layout_ui": False, "requires_breadcrumb_ui": False, "inventory_overrides": {}}

    evaluations = []
    req_layout = False
    req_breadcrumb = False

    for rule in rules:
        rtype = rule.get("type")
        element = rule.get("element", "").lower()
        original_text = rule.get("original_text", "").lower()
        
        # Flags for UI dynamic rendering
        if "grid" in element or "list" in element or "layout" in element:
            req_layout = True
        if "breadcrumb" in element:
            req_breadcrumb = True
            
        # Check if we can verify rules deterministically
        is_verifiable = rtype in ("presence", "absence", "inventory_config")
        el_or_orig = (element + " " + original_text).lower()
        verifiable_keywords = ['photo', 'image', 'content', 'faq', 'accordion', 'form', 'lead', 'contact', 'map', 'breadcrumb', 'hero', 'grid', 'list', 'inventory', 'under', 'below', 'price', 'vehicle', 'car', 'truck', '$']
        if any(vk in el_or_orig for vk in verifiable_keywords):
            is_verifiable = True


        if is_verifiable:
            is_presence = rtype != "absence"
            evaluations.append(_check_presence_absence(rule, soup, is_presence=is_presence, seo_coverage=seo_coverage, inventory_info=inventory_info))

        elif rtype == "tone":
            evaluations.append(_check_tone(rule, page_text))
        else:
            # Vague keywords like "service" go to manual review
            evaluations.append({
                "original": rule.get("original_text", "Unknown instruction"),
                "status": "manual_review",
                "reason": f"Vague clause '{rule.get('original_text')}' requires manual verification.",
                "type": "other"
            })

    return {
        "fallback": False,
        "evaluations": evaluations,
        "requires_layout_ui": req_layout,
        "requires_breadcrumb_ui": req_breadcrumb,
        "inventory_overrides": overrides
    }

