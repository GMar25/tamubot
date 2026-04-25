"""Shared RAG pipeline utilities — DRY helpers used across multiple nodes.

Canonical location for functions previously duplicated in router.py,
retrieval_node.py, recursive_retrieval_node.py, and pipeline_state.py.
"""
from __future__ import annotations

import re

from tamubot.core import config

# ---------------------------------------------------------------------------
# Query normalization (for cache keys)
# ---------------------------------------------------------------------------

def normalize_query(query: str) -> str:
    """Normalize a query string for exact-match cache lookups.

    Lowercases, strips punctuation, collapses whitespace.
    """
    cleaned = re.sub(r"[^\w\s]", "", query.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# Course ID normalization
# ---------------------------------------------------------------------------

def normalize_course_id(raw: str) -> str:
    """Normalize 'csce638' -> 'CSCE 638'."""
    raw = raw.strip().upper().replace("-", " ")
    match = re.match(r"^([A-Z]+)\s*(\d+.*)$", raw)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return raw


# ---------------------------------------------------------------------------
# Dynamic-k scaling (pure Python, no LLM)
# ---------------------------------------------------------------------------

def compute_dynamic_k(function: str, n_courses: int) -> dict[str, int]:
    """Compute retrieve_k and rerank_k scaled by the number of courses in the query.

    semantic_general is corpus-wide -- do not scale by course count.
    All other functions multiply their per-course base by n_courses, capped at the
    global maximums to avoid over-retrieving.
    """
    base = config.PER_COURSE_K[function]
    if function == "semantic_general":
        return dict(base)  # fixed, not scaled
    n = max(1, n_courses)
    return {
        "retrieve_k": min(base["retrieve_k"] * n, config.MAX_RETRIEVE_K),
        "rerank_k": min(base["rerank_k"] * n, config.MAX_RERANK_K),
    }


def compute_dynamic_k_recursive(n_courses: int) -> dict[str, int]:
    """Compute retrieve_k and rerank_k for the recursive anchor pass.

    Uses hybrid_course base for retrieve_k (broad fetch) and recursive base
    for rerank_k (tighter reranking).
    """
    base_hybrid = config.PER_COURSE_K["hybrid_course"]
    base_recursive = config.PER_COURSE_K["recursive"]
    n = max(1, n_courses)
    return {
        "retrieve_k": min(base_hybrid["retrieve_k"] * n, config.MAX_RETRIEVE_K),
        "rerank_k": min(base_recursive["rerank_k"] * n, config.MAX_RERANK_K),
    }


# ---------------------------------------------------------------------------
# Cache key factory
# ---------------------------------------------------------------------------

def make_cache_key(prefix: str, course_ids: list[str] | None = None, query: str = "") -> str:
    """Build a deterministic cache key from prefix, course IDs, and normalized query."""
    parts = [prefix]
    if course_ids is not None:
        parts.append(str(sorted(course_ids)))
    parts.append(normalize_query(query))
    return "|".join(parts)


# ---------------------------------------------------------------------------
# Out-of-scope fallback
# ---------------------------------------------------------------------------

OOS_FALLBACK = (
    "Howdy! I'm TamuBot, your Texas A&M academic assistant. "
    "I can help you with questions about courses, syllabi, grading policies, "
    "schedules, and university policies. What would you like to know?"
)
