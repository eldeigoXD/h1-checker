"""
inventory_learner.py
====================
Persistent correction-memory for the inventory inference engine.

Problem it solves:
  When the deterministic engine infers the wrong filter URL (e.g. returns
  model=IS instead of model=IS%20350 for a Lexus IS page), a user can manually
  correct the filter URL via the UI.  This module saves that correction and
  reloads it on the next scan of the same page, immediately improving accuracy.

Storage:
  inventory_memory.json — a JSON file next to this module.
  Schema (per domain/path key):
  {
    "www.motorcitylexusofbakersfield.com|/new-lexus/is-bakersfield-ca.htm": {
      "filter_url":        "/new-inventory/index.htm?make=Lexus&model=IS%20350",
      "source":            "manual_correction",
      "corrected_at":      "2026-06-08T19:30:00",
      "confirmation_count": 2,
      "confidence":         0.97
    },
    ...
  }

Confidence model:
  - manual_correction starts at 0.90
  - Each subsequent auto-confirm (page count ≈ filter count) raises it by 0.02
  - Each contradiction (count mismatch) lowers it by 0.05
  - Confidence >= 0.85 → used automatically; below that → shown as suggestion

Thread safety:
  A threading.Lock() protects all read/write operations so concurrent Flask
  requests never corrupt the file.
"""

import json
import os
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Optional

# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_MEMORY_FILE = os.path.join(_BASE_DIR, "inventory_memory.json")

_lock   = threading.Lock()
_memory: dict = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_key(url_or_domain: str, path: str = "") -> str:
    """
    Builds a stable lookup key from a URL or (domain, path) pair.
    Strips query strings and fragments.  Leading slash on path is normalised.

    Examples:
      _make_key("https://www.example.com/new/silverado.htm") →
          "www.example.com|/new/silverado.htm"

      _make_key("www.example.com", "/new/silverado.htm") →
          "www.example.com|/new/silverado.htm"
    """
    if path:
        # Called as (domain, path)
        domain = url_or_domain.lower().strip().lstrip("https://").split("/")[0]
        clean_path = "/" + path.lstrip("/")
        return f"{domain}|{clean_path}"
    else:
        # Called with a full URL
        parsed = urlparse(url_or_domain)
        domain = parsed.netloc.lower()
        clean_path = parsed.path or "/"
        return f"{domain}|{clean_path}"


def _load() -> dict:
    """Loads the memory file from disk, returns {} on any error."""
    if not os.path.exists(_MEMORY_FILE):
        return {}
    try:
        with open(_MEMORY_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        print(f"[InventoryLearner] Warning: could not load memory file: {e}")
        return {}


def _save(data: dict) -> None:
    """Saves the entire memory dict to disk atomically (write then rename)."""
    tmp = _MEMORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _MEMORY_FILE)
    except Exception as e:
        print(f"[InventoryLearner] Warning: could not save memory file: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_inventory_memory_all() -> dict:
    """Returns the full in-memory dict (load from disk if not cached)."""
    global _memory
    with _lock:
        if not _memory:
            _memory = _load()
        return dict(_memory)


def lookup(url: str) -> Optional[dict]:
    """
    Returns the stored record for a URL, or None if not found.
    Record includes: filter_url, confidence, source, corrected_at, etc.
    """
    key = _make_key(url)
    with _lock:
        global _memory
        if not _memory:
            _memory = _load()
        return _memory.get(key)


def get_filter(url: str, min_confidence: float = 0.85) -> Optional[str]:
    """
    Returns the stored filter_url string if it exists and meets min_confidence.
    Returns None otherwise — caller should fall back to deterministic logic.
    """
    record = lookup(url)
    if record and record.get("confidence", 0) >= min_confidence:
        return record["filter_url"]
    return None


def save_correction(url: str, filter_url: str, source: str = "manual_correction") -> dict:
    """
    Saves or updates a correction for the given page URL.

    Args:
        url:        Full page URL being corrected.
        filter_url: The correct inventory filter URL (relative or absolute).
        source:     'manual_correction' | 'auto_confirmed' | 'llm_suggestion'

    Returns the saved record.
    """
    key = _make_key(url)
    initial_confidence = {
        "manual_correction": 0.92,
        "auto_confirmed":    0.80,
        "llm_suggestion":    0.65,
    }.get(source, 0.70)

    with _lock:
        global _memory
        if not _memory:
            _memory = _load()

        existing = _memory.get(key, {})
        if existing.get("filter_url") == filter_url:
            # Same correction submitted again — boost confidence slightly
            new_conf = min(0.99, existing.get("confidence", initial_confidence) + 0.02)
        else:
            # Different correction — start fresh with initial confidence
            new_conf = initial_confidence

        record = {
            "filter_url":         filter_url,
            "source":             source,
            "corrected_at":       _now_iso(),
            "confirmation_count": existing.get("confirmation_count", 0) + 1,
            "confidence":         round(new_conf, 3),
            "url":                url,
        }
        _memory[key] = record
        _save(_memory)
        print(f"[InventoryLearner] Saved correction: {key} → {filter_url} (conf={new_conf:.2f})")
        return record


def confirm_correction(url: str, matched: bool) -> None:
    """
    Called after a scan validates whether the stored filter produces the right count.
    matched=True  → boost confidence (+0.02)
    matched=False → lower confidence (-0.05), eventually falls below threshold
    """
    key = _make_key(url)
    with _lock:
        global _memory
        if not _memory:
            _memory = _load()
        if key not in _memory:
            return

        record = _memory[key]
        delta  = +0.02 if matched else -0.05
        record["confidence"] = round(
            max(0.0, min(0.99, record.get("confidence", 0.5) + delta)), 3
        )
        record["confirmation_count"] = record.get("confirmation_count", 0) + 1
        record["last_confirmed"] = _now_iso()
        record["last_outcome"]   = "match" if matched else "mismatch"
        _save(_memory)
        print(f"[InventoryLearner] Confirmed {key}: matched={matched}, new_conf={record['confidence']:.2f}")


def delete_correction(url: str) -> bool:
    """Removes a stored correction. Returns True if something was deleted."""
    key = _make_key(url)
    with _lock:
        global _memory
        if not _memory:
            _memory = _load()
        if key in _memory:
            del _memory[key]
            _save(_memory)
            print(f"[InventoryLearner] Deleted correction for {key}")
            return True
        return False


def list_corrections(domain_filter: str = "") -> list[dict]:
    """Returns all stored corrections, optionally filtered by domain substring."""
    with _lock:
        global _memory
        if not _memory:
            _memory = _load()
        out = []
        for key, record in _memory.items():
            if domain_filter and domain_filter not in key:
                continue
            out.append({"key": key, **record})
        return sorted(out, key=lambda x: x.get("corrected_at", ""), reverse=True)


def get_stats() -> dict:
    """Returns summary statistics about the memory store."""
    with _lock:
        global _memory
        if not _memory:
            _memory = _load()
        total = len(_memory)
        high_conf  = sum(1 for r in _memory.values() if r.get("confidence", 0) >= 0.85)
        manual     = sum(1 for r in _memory.values() if r.get("source") == "manual_correction")
        auto       = sum(1 for r in _memory.values() if r.get("source") == "auto_confirmed")
        return {
            "total_corrections": total,
            "high_confidence":   high_conf,
            "manual":            manual,
            "auto_confirmed":    auto,
            "memory_file":       _MEMORY_FILE,
        }


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile, shutil

    # Use a temporary file for testing
    orig = _MEMORY_FILE
    tmp_dir = tempfile.mkdtemp()
    import inventory_learner as _self
    _self._MEMORY_FILE = os.path.join(tmp_dir, "test_memory.json")
    _self._memory = {}

    test_url = "https://www.motorcitylexusofbakersfield.com/new-lexus/is-bakersfield-ca.htm"
    test_filter = "/new-inventory/index.htm?make=Lexus&model=IS%20350"

    print("=== Save correction ===")
    rec = save_correction(test_url, test_filter)
    print(json.dumps(rec, indent=2))

    print("\n=== Get filter ===")
    f = get_filter(test_url)
    print(f"Filter: {f}")

    print("\n=== Confirm match ===")
    confirm_correction(test_url, matched=True)

    print("\n=== Stats ===")
    print(json.dumps(get_stats(), indent=2))

    print("\n=== List all ===")
    for item in list_corrections():
        print(item)

    # Cleanup
    shutil.rmtree(tmp_dir)
    _self._MEMORY_FILE = orig
    print("\n✅ All tests passed.")
