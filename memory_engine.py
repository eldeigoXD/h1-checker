"""
memory_engine.py
================
RAG-style vector memory for the QA Web Tool Pro.

Uses ChromaDB as the local vector store (file-backed, no server needed).
Embeddings are generated with the same all-MiniLM-L6-v2 model already loaded
in coherence_engine.py — zero additional model downloads.

Collections:
  - qa_cases:          Completed QA scan results (bugs, inventory, layout)
  - layout_patterns:   Widget/section patterns for page types

IMPORTANT: This module degrades gracefully if ChromaDB is not installed.
All public functions return safe defaults when ChromaDB is unavailable.

Typical usage:
    from memory_engine import store_qa_case, retrieve_similar_cases, build_rag_context

    # After a scan completes:
    store_qa_case(case_id="D-123", url="https://...", bugs=bugs, ...)

    # Before calling LLM:
    context = build_rag_context(url="https://...", instructions="Add breadcrumbs")
    prompt  = f"{context}\n\nNow audit this page..."
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# ChromaDB availability guard
# ---------------------------------------------------------------------------
try:
    import chromadb
    from chromadb.config import Settings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False
    print("[MemoryEngine] WARNING - ChromaDB not installed -- vector memory disabled. Run: pip install chromadb")

# ---------------------------------------------------------------------------
# Embedding model — reuse coherence_engine's model if available
# ---------------------------------------------------------------------------
_embed_model = None

def _get_embed_model():
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[MemoryEngine] Embedding model ready.")
    except Exception as e:
        print(f"[MemoryEngine] Could not load embedding model: {e}")
    return _embed_model

def _embed(text: str) -> list[float]:
    """Returns embedding vector for a text string, or [] on error."""
    model = _get_embed_model()
    if model is None:
        return []
    try:
        return model.encode([text], show_progress_bar=False)[0].tolist()
    except Exception as e:
        print(f"[MemoryEngine] Embedding error: {e}")
        return []

# ---------------------------------------------------------------------------
# ChromaDB client — lazy singleton
# ---------------------------------------------------------------------------
_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_CHROMA_DIR = os.path.join(_BASE_DIR, "chroma_db")
_client = None

def _get_client():
    global _client
    if not _CHROMA_AVAILABLE:
        return None
    if _client is not None:
        return _client
    try:
        os.makedirs(_CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=_CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        print(f"[MemoryEngine] ChromaDB ready at {_CHROMA_DIR}")
    except Exception as e:
        print(f"[MemoryEngine] ChromaDB init error: {e}")
    return _client

def _get_collection(name: str):
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as e:
        print(f"[MemoryEngine] Could not get collection '{name}': {e}")
        return None

# ---------------------------------------------------------------------------
# Collection: qa_cases
# ---------------------------------------------------------------------------

def store_qa_case(
    case_id: str,
    url: str,
    bugs: list,
    instructions: str = "",
    inventory_filter: str = "",
    layout_widgets: list = None,
    page_title: str = "",
    h1_text: str = "",
) -> bool:
    """
    Embeds and stores a completed QA scan into the 'qa_cases' collection.

    The embedding is built from: URL path + title + H1 + instructions
    so that similar pages are retrieved as nearest neighbours.

    Returns True if stored successfully, False otherwise.
    """
    col = _get_collection("qa_cases")
    if col is None:
        return False

    try:
        from urllib.parse import urlparse
        path = urlparse(url).path

        # Build searchable text
        text_for_embed = " ".join(filter(None, [
            path, page_title, h1_text, instructions
        ]))
        embedding = _embed(text_for_embed)
        if not embedding:
            return False

        doc_id = hashlib.md5(f"{url}:{case_id}".encode()).hexdigest()

        metadata = {
            "case_id":         case_id,
            "url":             url[:500],
            "path":            path[:200],
            "page_title":      page_title[:200],
            "h1_text":         h1_text[:200],
            "instructions":    instructions[:500],
            "inventory_filter": inventory_filter[:300],
            "bug_count":       len(bugs),
            "layout_widgets":  json.dumps(layout_widgets or [])[:500],
            "stored_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        # ChromaDB documents are used for retrieval display
        document = (
            f"Case: {case_id} | URL: {url} | Bugs: {len(bugs)} | "
            f"Title: {page_title} | H1: {h1_text} | "
            f"Inventory: {inventory_filter} | Instructions: {instructions}"
        )[:1000]

        col.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        print(f"[MemoryEngine] Stored QA case: {case_id} ({url[:60]})")
        return True

    except Exception as e:
        print(f"[MemoryEngine] store_qa_case error: {e}")
        return False


def retrieve_similar_cases(
    url: str,
    instructions: str = "",
    page_title: str = "",
    h1_text: str = "",
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieves the most semantically similar past QA cases.

    Returns list of metadata dicts, ordered by similarity (most similar first).
    Returns [] if ChromaDB is unavailable or no matches found.
    """
    col = _get_collection("qa_cases")
    if col is None:
        return []

    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        query_text = " ".join(filter(None, [path, page_title, h1_text, instructions]))
        embedding  = _embed(query_text)
        if not embedding:
            return []

        count = col.count()
        if count == 0:
            return []

        results = col.query(
            query_embeddings=[embedding],
            n_results=min(top_k, count),
            include=["metadatas", "documents", "distances"],
        )

        out = []
        for meta, doc, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        ):
            out.append({
                "similarity": round(1 - dist, 3),  # cosine distance → similarity
                "document":   doc,
                **meta,
            })
        return out

    except Exception as e:
        print(f"[MemoryEngine] retrieve_similar_cases error: {e}")
        return []


def build_rag_context(
    url: str,
    instructions: str = "",
    page_title: str = "",
    h1_text: str = "",
    top_k: int = 3,
) -> str:
    """
    Builds a natural-language context block from similar past cases.
    Designed to be prepended to LLM prompts.

    Returns "" if no similar cases found (safe to concat with any prompt).
    """
    cases = retrieve_similar_cases(url, instructions, page_title, h1_text, top_k=top_k)
    if not cases:
        return ""

    lines = ["=== Similar Past QA Cases (for context) ==="]
    for i, c in enumerate(cases, 1):
        sim_pct = int(c["similarity"] * 100)
        lines.append(
            f"\n[Case {i} — {sim_pct}% similar]\n"
            f"  URL: {c.get('url', 'N/A')}\n"
            f"  Case ID: {c.get('case_id', 'N/A')}\n"
            f"  Bugs found: {c.get('bug_count', '?')}\n"
            f"  Inventory filter used: {c.get('inventory_filter', 'N/A')}\n"
            f"  Instructions: {c.get('instructions', 'N/A')[:150]}"
        )
    lines.append("\n=== End of Past Cases ===\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Collection: layout_patterns
# ---------------------------------------------------------------------------

def store_layout_pattern(
    page_type: str,
    widgets: list[str],
    case_id: str = "",
    instructions: str = "",
) -> bool:
    """
    Stores a validated layout (widget list) for a given page type.

    page_type examples: 'new_model_landing', 'service_page', 'used_inventory_lp'
    """
    col = _get_collection("layout_patterns")
    if col is None:
        return False

    try:
        text = f"{page_type} {' '.join(widgets)} {instructions}"
        embedding = _embed(text)
        if not embedding:
            return False

        doc_id = hashlib.md5(f"{page_type}:{case_id}:{','.join(sorted(widgets))}".encode()).hexdigest()
        metadata = {
            "page_type":   page_type,
            "case_id":     case_id,
            "widgets":     json.dumps(widgets),
            "instructions": instructions[:400],
            "stored_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        col.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )
        print(f"[MemoryEngine] Stored layout pattern: {page_type} ({len(widgets)} widgets)")
        return True
    except Exception as e:
        print(f"[MemoryEngine] store_layout_pattern error: {e}")
        return False


def retrieve_similar_layouts(
    page_type: str,
    instructions: str = "",
    top_k: int = 3,
) -> list[dict]:
    """Returns most similar past layouts for the given page type + instructions."""
    col = _get_collection("layout_patterns")
    if col is None:
        return []
    try:
        query_text = f"{page_type} {instructions}"
        embedding  = _embed(query_text)
        if not embedding:
            return []
        count = col.count()
        if count == 0:
            return []
        results = col.query(
            query_embeddings=[embedding],
            n_results=min(top_k, count),
            include=["metadatas", "distances"],
        )
        out = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            out.append({
                "similarity": round(1 - dist, 3),
                "page_type":  meta.get("page_type"),
                "widgets":    json.loads(meta.get("widgets", "[]")),
                "case_id":    meta.get("case_id"),
                "instructions": meta.get("instructions"),
            })
        return out
    except Exception as e:
        print(f"[MemoryEngine] retrieve_similar_layouts error: {e}")
        return []


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def get_memory_stats() -> dict:
    """Returns counts for all collections."""
    if not _CHROMA_AVAILABLE:
        return {"available": False, "reason": "ChromaDB not installed"}
    client = _get_client()
    if client is None:
        return {"available": False, "reason": "ChromaDB client init failed"}
    stats = {"available": True, "chroma_path": _CHROMA_DIR}
    for name in ["qa_cases", "layout_patterns"]:
        col = _get_collection(name)
        stats[name] = col.count() if col else 0
    return stats


def delete_qa_case(case_id: str) -> bool:
    """Deletes all entries for a given case_id from qa_cases."""
    col = _get_collection("qa_cases")
    if col is None:
        return False
    try:
        results = col.get(where={"case_id": case_id})
        if results["ids"]:
            col.delete(ids=results["ids"])
            print(f"[MemoryEngine] Deleted {len(results['ids'])} entries for case {case_id}")
            return True
        return False
    except Exception as e:
        print(f"[MemoryEngine] delete_qa_case error: {e}")
        return False


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Memory Engine Self-Test ===")
    print(json.dumps(get_memory_stats(), indent=2))

    if _CHROMA_AVAILABLE:
        ok = store_qa_case(
            case_id="TEST-001",
            url="https://www.example.com/new-chevrolet/silverado-2500.htm",
            bugs=[{"message": "H1 mismatch"}],
            page_title="New Chevrolet Silverado 2500 for Sale",
            h1_text="New Silverado 2500",
            inventory_filter="/new-inventory/index.htm?make=Chevrolet&model=Silverado%202500%20HD",
            instructions="",
        )
        print(f"Store result: {ok}")

        cases = retrieve_similar_cases(
            url="https://www.example.com/new-chevrolet/silverado-1500.htm",
            page_title="New Chevrolet Silverado 1500",
        )
        print(f"Retrieved {len(cases)} similar cases:")
        for c in cases:
            print(f"  [{c['similarity']*100:.0f}%] {c.get('url')}")

        context = build_rag_context(
            url="https://www.example.com/new-chevrolet/silverado-1500.htm"
        )
        print(f"\nRAG context preview:\n{context[:300]}")
    else:
        print("ChromaDB not available. Run: pip install chromadb")
