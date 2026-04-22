"""Retrieval node — handles hybrid_course and semantic_general retrieval passes."""
from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from rag.graph.cache_utils import normalize_query
from rag.graph.middleware import error_guard_middleware, timing_middleware
from rag.state.pipeline_state import PipelineState


def _compute_dynamic_k(function: str, n_courses: int) -> dict[str, int]:
    """Compute retrieve_k scaled by number of courses."""
    base = config.PER_COURSE_K[function]
    if function == "semantic_general":
        return dict(base)
    n = max(1, n_courses)
    return {
        "retrieve_k": min(base["retrieve_k"] * n, config.MAX_RETRIEVE_K),
        "rerank_k": min(base["rerank_k"] * n, config.MAX_RERANK_K),
    }


def _make_retrieval_cache_key(function, course_ids, rewritten_query, eval_query=None):
    return f"{sorted(course_ids)}|{normalize_query(rewritten_query)}"


@timing_middleware
@error_guard_middleware
def retrieval_node(state: PipelineState) -> dict:
    """Execute retrieval based on function type."""
    from rag.tools.mongo import hybrid_search, semantic_search
    from rag.tools.voyage import rerank as voyage_rerank

    function = state.get("function", "out_of_scope")
    course_ids = state.get("course_ids", [])
    rewritten_query = state.get("rewritten_query") or state.get("query", "")
    node_trace = list(state.get("node_trace", []))
    node_trace.append("retrieval")

    dk = _compute_dynamic_k(function, len(course_ids))
    retrieve_k = dk["retrieve_k"]
    rerank_k = dk["rerank_k"]
    apply_knee = not state.get("recursive_search", False)

    # Cache check — skip retrieval on exact-match hit
    if config.SESSION_CACHE_ENABLED:
        cache_key = _make_retrieval_cache_key(function, course_ids, rewritten_query)
        cached_chunks = state.get("retrieval_cache", {}).get(cache_key)
        if cached_chunks is not None:
            node_trace.append("retrieval_cache_hit")
            try:
                from langfuse import get_client
                get_client().update_current_observation(metadata={"cache_hit": True})
            except Exception:
                pass
            return {"retrieved_chunks": cached_chunks, "node_trace": node_trace}

    try:
        if function == "hybrid_course":
            all_chunks: list[dict] = []
            errors: list[str] = []

            if len(course_ids) <= 1:
                # Fast path: single course — no thread overhead
                if course_ids:
                    all_chunks = hybrid_search(rewritten_query, course_ids[0], retrieve_k)
            else:
                # Parallel path: fan out one thread per course.
                #
                # Context propagation design:
                #   ThreadPoolExecutor in Python <3.12 does NOT copy contextvars
                #   to worker threads. We capture the calling thread's context once
                #   (original_ctx) and derive an INDEPENDENT copy per worker via
                #   original_ctx.run(copy_context). This gives each worker its own
                #   isolated snapshot so that ContextVar writes inside one worker
                #   (e.g. Langfuse @observe updating the current span ID) cannot
                #   bleed into sibling workers.
                original_ctx = contextvars.copy_context()
                worker_ctxs = [
                    original_ctx.run(contextvars.copy_context)
                    for _ in course_ids
                ]
                futures = {}
                with ThreadPoolExecutor(max_workers=min(len(course_ids), 8)) as executor:
                    for wctx, cid in zip(worker_ctxs, course_ids):
                        futures[executor.submit(wctx.run, hybrid_search, rewritten_query, cid, retrieve_k)] = cid
                    for future in as_completed(futures):
                        cid = futures[future]
                        try:
                            all_chunks.extend(future.result())
                        except Exception as exc:  # noqa: BLE001
                            msg = f"hybrid_search failed for {cid}: {exc}"
                            errors.append(msg)
                            logging.warning("retrieval_node: %s", msg)

            reranked = voyage_rerank(
                rewritten_query, all_chunks, top_k=rerank_k, apply_knee=apply_knee,
            )

            retrieval_cache_update = {}
            if config.SESSION_CACHE_ENABLED:
                cache_key = _make_retrieval_cache_key(function, course_ids, rewritten_query)
                existing_cache = state.get("retrieval_cache", {})
                retrieval_cache_update = {**existing_cache, cache_key: reranked}

            result: dict = {
                "retrieved_chunks": reranked,
                "retrieval_cache": retrieval_cache_update,
                "node_trace": node_trace,
            }
            if errors:
                result["retrieval_partial_errors"] = errors
            return result

        elif function == "semantic_general":
            chunks = semantic_search(rewritten_query, retrieve_k)
            reranked = voyage_rerank(
                rewritten_query, chunks, top_k=rerank_k, apply_knee=apply_knee,
            )

            retrieval_cache_update = {}
            if config.SESSION_CACHE_ENABLED:
                cache_key = _make_retrieval_cache_key(function, course_ids, rewritten_query)
                existing_cache = state.get("retrieval_cache", {})
                retrieval_cache_update = {**existing_cache, cache_key: reranked}

            return {"retrieved_chunks": reranked, "retrieval_cache": retrieval_cache_update, "node_trace": node_trace}

        else:
            return {"retrieved_chunks": [], "node_trace": node_trace}

    except Exception as e:
        return {
            "retrieved_chunks": [],
            "error": f"Retrieval failed: {e}",
            "node_trace": node_trace,
        }
