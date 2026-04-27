# Future Ideas

Architectural patterns and techniques worth exploring for TamuBot, drawn from OpenHands, Letta/MemGPT, and agentic RAG research.

---

## 1. Skills & Context Injection (OpenHands)

Use small Markdown files as reusable "knowledge modules" that get injected into the system prompt.

- **Modes**: always-on (global policies), keyword-triggered (e.g., "exam", "grade"), or on-demand (agent decides when to read).
- **Ideal for**: static but high-value rules — grading policies, enrollment rules, academic integrity.
- Reduces vector DB calls for obvious facts and guarantees they're always in context.
- Must be short (~500 tokens) and manually curated to avoid prompt-injection risks.

## 2. Event-Stream + Pydantic v2 State (OpenHands)

All agent state is stored in a single typed object and an append-only event log.

- Components (router, tools, LLM) remain stateless; they only read/write via this state.
- The log records every user message, tool call, and result, giving auditability and replay.
- Pydantic v2 schemas enforce strict structure but must be configured to tolerate partial updates.
- This becomes the backbone for coordination, debugging, and evaluation across the whole system.

## 3. Context Condenser (OpenHands)

Automatically compresses long conversations when they near the context limit.

- Keeps the earliest messages and latest few turns, and summarises the middle into a compact "history summary".
- Uses a cheaper LLM for summarization to cut cost while preserving intent and key facts.
- Prevents silent truncation of important context by the model or client.
- Especially useful for long-running student interactions that span multiple follow-ups.

## 4. RouterLLM Multi-Model Routing (OpenHands)

A routing layer picks the best model for each request before calling any LLM.

- Simple queries go to a cheap/lightweight model; complex or multimodal tasks go to a stronger one.
- Routing can be rule-based (text vs images) or driven by a classifier model.
- **For TAMU**: Flash-Lite for quick fact checks, Flash for RAG, Pro only for complex syllabus parsing.
- Great for controlling latency and cost without hard-coding model choice in every node.

## 5. Tiered Memory: Core / Recall / Archival (Letta / MemGPT)

Splits memory into three layers: always-on core, searchable conversation history, and large long-term knowledge.

- **Core**: small, high-priority facts always in the prompt (course, semester, user profile).
- **Recall**: full dialogue history you can search when you need past details.
- **Archival**: large corpus (syllabi, policies) accessed via vector search/RAG.
- Prevents overloading the prompt while still keeping everything retrievable when needed.

## 6. Sleep-Time Compute (Letta)

A background "sleep" agent rewrites and cleans up memory when the user is idle.

- Turns messy, incremental notes (e.g., a full syllabus) into a dense, well-structured summary.
- Runs out of band, so user-facing latency stays low.
- Perfect for pre-digesting all syllabi into Q&A-ready summaries ahead of time.
- Shifts cost from every query to rare, scheduled batch jobs.

## 7. Shared Memory Blocks (Letta)

Multiple agents share a single logical memory object and see each other's updates instantly.

- Supervisor agents can write task context; worker agents read it without explicit messaging.
- Enables clean supervisor-worker and "team of agents" patterns without bespoke protocols.
- In our stack, this corresponds to making course/session context a shared, central structure.
- Prevents each agent from re-inferring course, semester, or user intent from scratch.

## 8. RAG-MCP Tool Discovery

Embeds tool descriptions and retrieves only the most relevant tools per query.

- Avoids dumping every tool schema into the prompt, which confuses the model and wastes tokens.
- Significantly improves tool selection accuracy as the number of tools grows.
- Lets you scale from a handful of tools to dozens without redesigning prompts.
- Ideal once we add separate tools for catalog, grading, calendar, and department APIs.

## 9. Agentic RAG Self-Correction

Wraps retrieval + generation in a loop with a query rewriter and relevance grader.

- If retrieved chunks don't look relevant, it rewrites the query and tries again (with limits).
- The grader explicitly decides "do we have enough good context to answer yet?".
- Turns the system from one-shot RAG into a self-correcting search process.
- Particularly important for course-scoped questions where the first retrieval hit might be from the wrong course.
