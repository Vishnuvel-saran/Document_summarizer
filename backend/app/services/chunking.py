from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import tiktoken

from app.schemas.chunk import DocumentChunk
from app.services.document_parser import DocumentExtractionResult, ExtractionBlock


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 500
    overlap_tokens: int = 75
    max_tokens: int = 700
    tokenizer_encoding: str = "cl100k_base"

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be greater than zero.")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be at least target_tokens.")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_tokens:
            raise ValueError(
                "overlap_tokens must be non-negative and below max_tokens."
            )


class StructureAwareChunker:
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        self.encoding = tiktoken.get_encoding(self.config.tokenizer_encoding)

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def chunk_document(
        self, extracted: DocumentExtractionResult, document_id: str
    ) -> list[DocumentChunk]:
        ordered_blocks = [
            block
            for _, block in sorted(
                enumerate(extracted.blocks),
                key=lambda item: (item[1].block_index, item[0]),
            )
        ]
        chunks: list[DocumentChunk] = []
        pending: list[ExtractionBlock] = []
        active_section: str | None = None

        def emit(
            content: str,
            source_blocks: list[ExtractionBlock],
            block_type: str,
            section_title: str | None,
            source_metadata: dict[str, Any] | None = None,
        ) -> None:
            content = content.strip()
            if not content:
                return
            pages = sorted(
                {
                    block.page_number
                    for block in source_blocks
                    if block.page_number is not None
                }
            )
            metadata = source_metadata or {
                "blocks": [
                    {
                        "block_index": block.block_index,
                        "block_type": block.block_type,
                        "metadata": block.metadata,
                    }
                    for block in source_blocks
                ]
            }
            chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    content=content,
                    block_type=block_type,
                    page_number=pages[0] if len(pages) == 1 else None,
                    page_start=pages[0] if pages else None,
                    page_end=pages[-1] if pages else None,
                    section_title=section_title,
                    source_block_indices=list(
                        dict.fromkeys(block.block_index for block in source_blocks)
                    ),
                    source_metadata=metadata,
                    token_count=self.count_tokens(content),
                    token_counting_method=f"tiktoken:{self.config.tokenizer_encoding}",
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
            )

        def flush_pending() -> None:
            if not pending:
                return
            types = {block.block_type for block in pending}
            block_type = next(iter(types)) if len(types) == 1 else "mixed"
            section_title = next(
                (
                    block.section_title
                    for block in reversed(pending)
                    if block.section_title
                ),
                active_section,
            )
            emit(
                "\n\n".join(
                    block.text.strip() for block in pending if block.text.strip()
                ),
                list(pending),
                block_type,
                section_title,
            )
            pending.clear()

        def emit_long_block(
            block: ExtractionBlock, heading_context: list[ExtractionBlock]
        ) -> None:
            prefix = "\n\n".join(item.text.strip() for item in heading_context)
            prefix_with_separator = f"{prefix}\n\n" if prefix else ""
            available = self.config.max_tokens - self.count_tokens(
                prefix_with_separator
            )
            if available < 1:
                heading_context = []
                prefix_with_separator = ""
                available = self.config.max_tokens
            parts = self._split_oversized_text(block.text.strip(), available)
            for part in parts:
                emit(
                    f"{prefix_with_separator}{part}",
                    [*heading_context, block],
                    "mixed" if heading_context else block.block_type,
                    block.section_title or active_section,
                )

        for block in ordered_blocks:
            text_value = block.text.strip()
            if not text_value:
                continue

            if block.block_type == "heading":
                flush_pending()
                active_section = text_value
                pending.append(block)
                continue

            if (
                block.section_title
                and active_section
                and block.section_title != active_section
            ):
                flush_pending()
            if block.section_title:
                active_section = block.section_title

            if block.block_type == "table":
                heading_context = [
                    item for item in pending if item.block_type == "heading"
                ]
                flush_pending()
                self._emit_table(
                    block, document_id, active_section, chunks, heading_context
                )
                continue

            block_tokens = self.count_tokens(text_value)
            heading_context = (
                pending
                if pending and all(item.block_type == "heading" for item in pending)
                else []
            )
            heading_prefix = "\n\n".join(item.text.strip() for item in heading_context)
            combined = "\n\n".join(
                [*(item.text.strip() for item in pending), text_value]
            )
            combined_tokens = self.count_tokens(combined)

            if block_tokens > self.config.max_tokens or (
                heading_context and combined_tokens > self.config.max_tokens
            ):
                if heading_context:
                    pending.clear()
                else:
                    flush_pending()
                emit_long_block(block, list(heading_context))
                continue

            if (
                pending
                and combined_tokens > self.config.target_tokens
                and not heading_context
            ):
                flush_pending()
            elif heading_prefix and combined_tokens > self.config.max_tokens:
                flush_pending()
            pending.append(block)

        flush_pending()
        return chunks

    def _split_oversized_text(self, text: str, token_limit: int) -> list[str]:
        tokens = self.encoding.encode(text)
        if len(tokens) <= token_limit:
            return [text]

        parts: list[str] = []
        start = 0
        overlap = min(self.config.overlap_tokens, max(0, token_limit - 1))
        while start < len(tokens):
            end = min(start + token_limit, len(tokens))
            if end < len(tokens):
                candidate = self.encoding.decode(tokens[start:end])
                boundary = max(
                    candidate.rfind(". "), candidate.rfind("? "), candidate.rfind("! ")
                )
                if boundary >= len(candidate) // 2:
                    sentence_tokens = len(
                        self.encoding.encode(candidate[: boundary + 1])
                    )
                    if sentence_tokens > 0:
                        end = min(start + sentence_tokens, end)
            part = self.encoding.decode(tokens[start:end]).strip()
            if part:
                parts.append(part)
            if end >= len(tokens):
                break
            start = max(start + 1, end - overlap)
        return parts

    def _emit_table(
        self,
        block: ExtractionBlock,
        document_id: str,
        section_title: str | None,
        chunks: list[DocumentChunk],
        heading_context: list[ExtractionBlock],
    ) -> None:
        rows = block.metadata.get("rows")
        if not isinstance(rows, list) or not rows:
            rows = [[cell.strip() for cell in block.text.split("|")]]
        normalized_rows = [[str(cell).strip() for cell in row] for row in rows]
        header = normalized_rows[0]
        groups: list[list[list[str]]] = []
        current = [header]

        def render(table_rows: list[list[str]]) -> str:
            lines = [" | ".join(row) for row in table_rows]
            table_text = "\n".join(lines)
            context = section_title or (
                heading_context[-1].text if heading_context else None
            )
            return f"Section: {context}\n\n{table_text}" if context else table_text

        for row in normalized_rows[1:]:
            candidate = [*current, row]
            if self.count_tokens(render(candidate)) <= self.config.max_tokens:
                current.append(row)
            else:
                groups.append(current)
                current = [header, row]
        if current:
            groups.append(current)

        for group_index, table_rows in enumerate(groups):
            source_metadata = {
                "blocks": [
                    {
                        "block_index": block.block_index,
                        "block_type": block.block_type,
                        "metadata": block.metadata,
                    }
                ],
                "table_rows": table_rows,
                "table_header_repeated": group_index > 0,
            }
            emit_content = render(table_rows)
            pages = [block.page_number] if block.page_number is not None else []
            chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    content=emit_content,
                    block_type="table",
                    page_number=pages[0] if pages else None,
                    page_start=pages[0] if pages else None,
                    page_end=pages[0] if pages else None,
                    section_title=section_title or block.section_title,
                    source_block_indices=[block.block_index],
                    source_metadata=source_metadata,
                    token_count=self.count_tokens(emit_content),
                    token_counting_method=f"tiktoken:{self.config.tokenizer_encoding}",
                    content_hash=hashlib.sha256(
                        emit_content.encode("utf-8")
                    ).hexdigest(),
                )
            )
