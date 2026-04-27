from __future__ import annotations

import re
from dataclasses import dataclass, field


def _tokens_approx(text: str) -> int:
    return max(0, round(len(text) / 4))


def _has_table(content: str) -> bool:
    return bool(re.search(r"\|.*\|", content))


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
    return parts


# ── Section tree ─────────────────────────────────────────────────────────────


@dataclass
class SectionNode:
    header: str = ""
    level: int = 0
    body: str = ""
    children: list[SectionNode] = field(default_factory=list)

    def total_tokens(self) -> int:
        t = _tokens_approx(self._full_text())
        return t

    def _full_text(self) -> str:
        parts = []
        if self.header:
            parts.append(f"{'#' * self.level} {self.header}")
        if self.body:
            parts.append(self.body)
        for child in self.children:
            parts.append(child._full_text())
        return "\n\n".join(parts)


_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)")


def _parse_sections(markdown: str) -> SectionNode:
    root = SectionNode(header="", level=0, body="", children=[])
    stack: list[SectionNode] = [root]
    body_lines: list[str] = []

    def _flush_body():
        text = "\n".join(body_lines).strip()
        if text:
            stack[-1].body = text
        body_lines.clear()

    for line in markdown.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            _flush_body()
            level = len(m.group(1))
            node = SectionNode(header=m.group(2).strip(), level=level)
            # Find parent: pop stack until we find a node with level < this one
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)
        else:
            body_lines.append(line)

    _flush_body()
    return root


# ── Chunking ─────────────────────────────────────────────────────────────────


def _header_path(ancestors: list[str]) -> str:
    return " > ".join(a for a in ancestors if a)


def _emit_chunk(
    content: str,
    header_path: str,
    split_reason: str,
    chunks: list[dict],
):
    content = content.strip()
    if not content:
        return
    chunks.append(
        {
            "chunk_index": len(chunks),
            "content": content,
            "header_path": header_path,
            "token_count": _tokens_approx(content),
            "has_table": _has_table(content),
            "split_reason": split_reason,
        }
    )


def _node_text(node: SectionNode, include_children: bool = True) -> str:
    parts = []
    if node.header:
        parts.append(f"{'#' * node.level} {node.header}")
    if node.body:
        parts.append(node.body)
    if include_children:
        for child in node.children:
            parts.append(_node_text(child))
    return "\n\n".join(parts)


def _walk(
    node: SectionNode,
    ancestors: list[str],
    max_tok: int,
    min_tok: int,
    chunks: list[dict],
    log: dict,
):
    total = node.total_tokens()
    hp = _header_path(ancestors)

    if total <= max_tok:
        # Emit as one chunk
        text = _node_text(node)
        _emit_chunk(text, hp, "section", chunks)
        log["kept_as_is"] += 1
        return

    if node.children:
        # Emit this node's own body first (if any)
        if node.body.strip():
            body_text = ""
            if node.header:
                body_text = f"{'#' * node.level} {node.header}\n\n{node.body}"
            else:
                body_text = node.body
            if _tokens_approx(body_text) > max_tok:
                _paragraph_fallback(body_text, hp, max_tok, chunks, log)
            elif body_text.strip():
                _emit_chunk(body_text, hp, "sub-header", chunks)

        # Recurse into children
        for child in node.children:
            _walk(child, ancestors + [child.header], max_tok, min_tok, chunks, log)
        log["split"] += 1
        return

    # Leaf node too big — paragraph fallback
    text = _node_text(node)
    _paragraph_fallback(text, hp, max_tok, chunks, log)


def _paragraph_fallback(
    text: str,
    header_path: str,
    max_tok: int,
    chunks: list[dict],
    log: dict,
):
    paragraphs = _split_paragraphs(text)
    current_parts: list[str] = []
    current_tok = 0

    for para in paragraphs:
        ptok = _tokens_approx(para)
        if current_tok + ptok > max_tok and current_parts:
            _emit_chunk("\n\n".join(current_parts), header_path, "paragraph-fallback", chunks)
            current_parts = []
            current_tok = 0
        current_parts.append(para)
        current_tok += ptok

    if current_parts:
        _emit_chunk("\n\n".join(current_parts), header_path, "paragraph-fallback", chunks)

    log["paragraph_fallback"] += 1


def _merge_small(chunks: list[dict], min_tok: int) -> tuple[list[dict], int]:
    if not chunks:
        return chunks, 0
    merged: list[dict] = []
    merge_count = 0

    for chunk in chunks:
        if merged and chunk["token_count"] < min_tok and merged[-1]["header_path"] == chunk["header_path"]:
            merged[-1]["content"] += "\n\n" + chunk["content"]
            merged[-1]["token_count"] = _tokens_approx(merged[-1]["content"])
            merged[-1]["has_table"] = merged[-1]["has_table"] or chunk["has_table"]
            merged[-1]["split_reason"] = "merged"
            merge_count += 1
        elif merged and merged[-1]["token_count"] < min_tok:
            merged[-1]["content"] += "\n\n" + chunk["content"]
            merged[-1]["token_count"] = _tokens_approx(merged[-1]["content"])
            merged[-1]["has_table"] = merged[-1]["has_table"] or chunk["has_table"]
            merged[-1]["split_reason"] = "merged"
            merge_count += 1
        else:
            merged.append(chunk)

    # Re-index
    for i, c in enumerate(merged):
        c["chunk_index"] = i

    return merged, merge_count


def chunk_markdown(
    markdown: str,
    max_chunk_tokens: int = 600,
    min_chunk_tokens: int = 50,
    split_level: int = 3,
) -> list[dict]:
    root = _parse_sections(markdown)
    log: dict = {"kept_as_is": 0, "split": 0, "paragraph_fallback": 0}
    chunks: list[dict] = []

    if not root.children and root.body.strip():
        # No headers at all — use paragraph fallback on entire document
        _paragraph_fallback(root.body, "", max_chunk_tokens, chunks, log)
    else:
        # Emit root body if any
        if root.body.strip():
            if _tokens_approx(root.body) > max_chunk_tokens:
                _paragraph_fallback(root.body, "", max_chunk_tokens, chunks, log)
            else:
                _emit_chunk(root.body, "", "section", chunks)

        for child in root.children:
            _walk(child, [child.header], max_chunk_tokens, min_chunk_tokens, chunks, log)

    chunks, merge_count = _merge_small(chunks, min_chunk_tokens)
    return chunks


def chunk_with_log(markdown: str, **kwargs) -> tuple[list[dict], dict]:
    root = _parse_sections(markdown)
    max_tok = kwargs.get("max_chunk_tokens", 600)
    min_tok = kwargs.get("min_chunk_tokens", 50)

    log = {"kept_as_is": 0, "split": 0, "paragraph_fallback": 0, "merged": 0}
    chunks: list[dict] = []

    total_sections = _count_sections(root)

    if not root.children and root.body.strip():
        _paragraph_fallback(root.body, "", max_tok, chunks, log)
    else:
        if root.body.strip():
            if _tokens_approx(root.body) > max_tok:
                _paragraph_fallback(root.body, "", max_tok, chunks, log)
            else:
                _emit_chunk(root.body, "", "section", chunks)

        for child in root.children:
            _walk(child, [child.header], max_tok, min_tok, chunks, log)

    chunks, merge_count = _merge_small(chunks, min_tok)
    log["merged"] = merge_count
    log["total_sections"] = total_sections

    return chunks, log


def _count_sections(node: SectionNode) -> int:
    count = 1 if node.header else 0
    for child in node.children:
        count += _count_sections(child)
    return count
