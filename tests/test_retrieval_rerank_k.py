"""Tests that retrieval_node and recursive_retrieval_node apply rerank_k cutoff.

Bug: both nodes called voyage_rerank with top_k=len(all_chunks), discarding
rerank_k from compute_dynamic_k entirely.
"""
from unittest.mock import call, patch

import config


# ---------------------------------------------------------------------------
# retrieval_node — hybrid_course
# ---------------------------------------------------------------------------

def test_hybrid_course_rerank_uses_rerank_k_not_all_chunks():
    """voyage_rerank must be called with rerank_k, not len(all_chunks)."""
    from tamubot.rag.nodes.retrieval_node import retrieval_node

    # 1 course → rerank_k = config.PER_COURSE_K["hybrid_course"]["rerank_k"] * 1
    expected_rerank_k = config.PER_COURSE_K["hybrid_course"]["rerank_k"]
    # Return more chunks than rerank_k to expose the bug
    fake_chunks = [{"content": f"chunk {i}", "score": 0.9} for i in range(20)]

    state = {
        "function": "hybrid_course",
        "course_ids": ["202611_CSCE_221_500"],
        "rewritten_query": "what is the syllabus?",
        "node_trace": [],
        "retrieval_cache": {},
    }

    with patch("tamubot.rag.tools.mongo.hybrid_search", return_value=fake_chunks), \
         patch("tamubot.rag.tools.voyage.rerank", return_value=fake_chunks[:expected_rerank_k]) as mock_rerank:
        retrieval_node(state)

    mock_rerank.assert_called_once()
    called_top_k = mock_rerank.call_args[1]["top_k"]
    assert called_top_k == expected_rerank_k, (
        f"Expected top_k={expected_rerank_k} (rerank_k), got top_k={called_top_k} (len of all chunks)"
    )


# ---------------------------------------------------------------------------
# retrieval_node — semantic_general
# ---------------------------------------------------------------------------

def test_semantic_general_rerank_uses_rerank_k_not_all_chunks():
    """semantic_general must also apply rerank_k cutoff."""
    from tamubot.rag.nodes.retrieval_node import retrieval_node

    expected_rerank_k = config.PER_COURSE_K["semantic_general"]["rerank_k"]
    fake_chunks = [{"content": f"chunk {i}", "score": 0.9} for i in range(20)]

    state = {
        "function": "semantic_general",
        "course_ids": [],
        "rewritten_query": "ML courses at TAMU",
        "node_trace": [],
        "retrieval_cache": {},
    }

    with patch("tamubot.rag.tools.mongo.semantic_search", return_value=fake_chunks), \
         patch("tamubot.rag.tools.voyage.rerank", return_value=fake_chunks[:expected_rerank_k]) as mock_rerank:
        retrieval_node(state)

    mock_rerank.assert_called_once()
    called_top_k = mock_rerank.call_args[1]["top_k"]
    assert called_top_k == expected_rerank_k, (
        f"Expected top_k={expected_rerank_k} (rerank_k), got top_k={called_top_k}"
    )


# ---------------------------------------------------------------------------
# recursive_retrieval_node
# ---------------------------------------------------------------------------

def test_recursive_retrieval_rerank_uses_rerank_k_not_all_chunks():
    """recursive_retrieval_node must apply rerank_k cutoff."""
    from tamubot.rag.nodes.recursive_retrieval_node import recursive_retrieval_node

    expected_rerank_k = config.PER_COURSE_K["recursive"]["rerank_k"]
    fake_chunks = [{"content": f"chunk {i}", "score": 0.9} for i in range(20)]

    state = {
        "function": "recursive",
        "course_ids": ["202611_CSCE_221_500"],
        "rewritten_query": "prereqs for CSCE 221",
        "node_trace": [],
        "retrieval_cache": {},
    }

    with patch("tamubot.rag.tools.mongo.hybrid_search", return_value=fake_chunks), \
         patch("tamubot.rag.tools.voyage.rerank", return_value=fake_chunks[:expected_rerank_k]) as mock_rerank:
        recursive_retrieval_node(state)

    mock_rerank.assert_called_once()
    called_top_k = mock_rerank.call_args[1]["top_k"]
    assert called_top_k == expected_rerank_k, (
        f"Expected top_k={expected_rerank_k} (rerank_k), got top_k={called_top_k}"
    )


# ---------------------------------------------------------------------------
# retrieval_node — parallel multi-course
# ---------------------------------------------------------------------------

def test_parallel_multi_course_calls_hybrid_search_once_per_course():
    """With N course IDs, hybrid_search must be called exactly N times in parallel."""
    from tamubot.rag.nodes.retrieval_node import retrieval_node

    course_ids = ["CSCE 638", "CSCE 670", "CSCE 625"]
    fake_chunks_per_course = [{"content": f"chunk {cid}", "score": 0.9, "course_id": cid}
                               for cid in course_ids]
    rerank_k = config.PER_COURSE_K["hybrid_course"]["rerank_k"] * len(course_ids)

    state = {
        "function": "hybrid_course",
        "course_ids": course_ids,
        "rewritten_query": "compare ML courses",
        "node_trace": [],
        "retrieval_cache": {},
    }

    call_log: list[str] = []

    def fake_hybrid_search(query, cid, k):
        call_log.append(cid)
        return [{"content": f"result for {cid}", "score": 0.9, "course_id": cid}]

    with patch("tamubot.rag.tools.mongo.hybrid_search", side_effect=fake_hybrid_search), \
         patch("tamubot.rag.tools.voyage.rerank",
               side_effect=lambda q, c, top_k, **kw: c[:top_k]) as mock_rerank:
        result = retrieval_node(state)

    # Every course must have been searched
    assert sorted(call_log) == sorted(course_ids), (
        f"Expected calls for {course_ids}, got {call_log}"
    )
    # Rerank called exactly once with the combined pool
    mock_rerank.assert_called_once()
    # No errors
    assert "retrieval_partial_errors" not in result
    assert "retrieval" in result["node_trace"]


def test_parallel_multi_course_handles_partial_failure_gracefully():
    """If one course's search raises, the node should still return results from the others."""
    from tamubot.rag.nodes.retrieval_node import retrieval_node

    good_course = "CSCE 638"
    bad_course = "CSCE 999"  # will raise

    def fake_hybrid_search(query, cid, k):
        if cid == bad_course:
            raise ConnectionError(f"Simulated network failure for {cid}")
        return [{"content": f"result for {cid}", "score": 0.9, "course_id": cid}]

    state = {
        "function": "hybrid_course",
        "course_ids": [good_course, bad_course],
        "rewritten_query": "compare ML courses",
        "node_trace": [],
        "retrieval_cache": {},
    }

    with patch("tamubot.rag.tools.mongo.hybrid_search", side_effect=fake_hybrid_search), \
         patch("tamubot.rag.tools.voyage.rerank",
               side_effect=lambda q, c, top_k, **kw: c[:top_k]):
        result = retrieval_node(state)

    # Node must not crash and must surface partial results
    assert isinstance(result["retrieved_chunks"], list)
    # Good course chunks still present
    assert any(c["course_id"] == good_course for c in result["retrieved_chunks"])
    # Error surfaced in state
    assert "retrieval_partial_errors" in result
    assert any(bad_course in e for e in result["retrieval_partial_errors"])
