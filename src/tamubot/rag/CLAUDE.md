# tamubot.rag — RAG Pipeline

## LLM Client

All LLM calls go through `tools/llm.py` (`call_llm` / `stream_llm`) — never call `config.get_tamu_client()` / `config.get_genai_client()` directly.

## Gotchas

- **TAMU gateway**: always returns SSE regardless of `stream` param. All calls must use `stream=True`. Base URL: `https://chat-api.tamu.ai/openai` (no `/v1`). Min `max_tokens=4096` or response is empty. Token counts are None on TAMU path.
- **Gemini JSON mode**: free-form Markdown fields silently return empty → render Markdown in Python (`_render_comparison_markdown()`)
- **Primacy-recency** (`format_context_xml`): rank 1 → start, rank 2 → end, 3–N → middle
- **Gate 1** (sync, regex): `validate_citations_with_trace()` — checks `[Source N]` presence after generation
