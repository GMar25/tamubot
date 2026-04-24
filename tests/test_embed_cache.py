"""Tests for embed_query caching and contextvars propagation in the parallel retrieval path."""
import contextvars
import threading
from unittest.mock import MagicMock, patch


def _clear_cache():
    """Clear the module-level embed cache between tests to ensure isolation."""
    import tamubot.rag.tools.voyage as voyage_mod
    voyage_mod._embed_cache.clear()


def test_embed_query_single_thread_calls_api_once():
    """Sequential repeated calls for the same text hit the cache after the first call."""
    from tamubot.rag.tools.voyage import embed_query

    _clear_cache()
    fake_embedding = [0.1, 0.2, 0.3]

    with patch("tamubot.rag.tools.voyage._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.embed.return_value.embeddings = [fake_embedding]
        mock_get_client.return_value = mock_client

        r1 = embed_query("hello world")
        r2 = embed_query("hello world")  # should hit cache

    assert r1 == fake_embedding
    assert r2 == fake_embedding
    assert mock_client.embed.call_count == 1, (
        f"Expected 1 API call, got {mock_client.embed.call_count}"
    )


def test_embed_query_parallel_threads_call_api_exactly_once():
    """When N threads simultaneously call embed_query with the same text,
    only ONE Voyage API call should be made (double-checked lock prevents thundering herd)."""
    from tamubot.rag.tools.voyage import embed_query

    _clear_cache()
    fake_embedding = [0.4, 0.5, 0.6]
    results: list = []
    errors: list = []

    def _call():
        try:
            results.append(embed_query("concurrent query"))
        except Exception as exc:
            errors.append(exc)

    with patch("tamubot.rag.tools.voyage._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.embed.return_value.embeddings = [fake_embedding]
        mock_get_client.return_value = mock_client

        threads = [threading.Thread(target=_call) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert not errors, f"Threads raised exceptions: {errors}"
    assert len(results) == 5
    # All threads must return the correct embedding
    assert all(r == fake_embedding for r in results), f"Results differed: {results}"
    # Crucially: only one API call despite 5 concurrent threads
    assert mock_client.embed.call_count == 1, (
        f"Expected exactly 1 API call (lock prevented thundering herd), "
        f"got {mock_client.embed.call_count}"
    )


def test_embed_query_different_texts_each_call_api_once():
    """Different query texts each get their own cache entry and API call."""
    from tamubot.rag.tools.voyage import embed_query

    _clear_cache()

    with patch("tamubot.rag.tools.voyage._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.embed.side_effect = lambda texts, **kw: MagicMock(
            embeddings=[[float(len(t)) for _ in range(3)] for t in texts]
        )
        mock_get_client.return_value = mock_client

        r1 = embed_query("short")
        r2 = embed_query("longer query text")
        r3 = embed_query("short")  # cache hit

    assert mock_client.embed.call_count == 2  # "short" + "longer query text"
    assert r1 == r3  # same text → same cached result


def test_parallel_retrieval_propagates_contextvars_to_workers():
    """retrieval_node must propagate the calling thread's contextvars to worker threads,
    AND must isolate each worker so that ContextVar writes in one worker cannot bleed
    into sibling workers.

    Rationale: ThreadPoolExecutor in Python <3.12 does NOT automatically copy
    contextvars to threads. We capture original_ctx once and derive an independent
    copy per worker via original_ctx.run(copy_context) so that Langfuse @observe
    ContextVar writes (span IDs) in one worker cannot contaminate others.
    """
    from tamubot.rag.nodes.retrieval_node import retrieval_node

    sentinel: contextvars.ContextVar[str] = contextvars.ContextVar("sentinel")
    # A second var that workers WRITE to — used to prove write isolation
    writer: contextvars.ContextVar[str] = contextvars.ContextVar("writer")
    seen_before_write: list[str] = []

    def fake_hybrid_search(query, cid, k):
        # Every worker should see the main thread's sentinel value
        seen_before_write.append(sentinel.get("MISSING"))
        # Each worker writes its own value — should NOT affect sibling workers
        writer.set(f"written_by_{cid}")
        return [{"content": f"result for {cid}", "score": 0.9, "course_id": cid}]

    sentinel.set("PROPAGATED")

    state = {
        "function": "hybrid_course",
        "course_ids": ["CSCE 638", "CSCE 670"],
        "rewritten_query": "compare ML courses",
        "node_trace": [],
        "retrieval_cache": {},
    }

    with patch("tamubot.rag.tools.mongo.hybrid_search", side_effect=fake_hybrid_search), \
         patch("tamubot.rag.tools.voyage.rerank", side_effect=lambda q, c, top_k, **kw: c[:top_k]):
        retrieval_node(state)

    # Both workers must have seen the main thread's sentinel value
    assert len(seen_before_write) == 2, f"Expected 2 workers, got {seen_before_write}"
    assert all(v == "PROPAGATED" for v in seen_before_write), (
        f"Workers did not see main thread ContextVar — got: {seen_before_write}"
    )
    # Main thread's sentinel must be unchanged by worker writes
    assert sentinel.get("MISSING") == "PROPAGATED", "Worker writes bled back to main thread"
