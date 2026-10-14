from app.services.chunking import ChunkingConfig, StructureAwareChunker
from app.services.document_parser import DocumentExtractionResult, ExtractionBlock


def _chunker(**overrides: int) -> StructureAwareChunker:
    values = {"target_tokens": 50, "overlap_tokens": 8, "max_tokens": 64}
    values.update(overrides)
    return StructureAwareChunker(ChunkingConfig(**values))


def test_chunker_keeps_heading_context_and_source_order() -> None:
    extracted = DocumentExtractionResult(
        file_type="docx",
        filename="contract.docx",
        blocks=[
            ExtractionBlock(block_type="heading", text="Payment", block_index=0),
            ExtractionBlock(
                block_type="paragraph",
                text="Invoices are due in thirty days.",
                section_title="Payment",
                block_index=1,
            ),
            ExtractionBlock(
                block_type="paragraph",
                text="Late balances accrue interest.",
                section_title="Payment",
                block_index=2,
            ),
        ],
    )

    chunks = _chunker().chunk_document(extracted, "doc-1")

    assert len(chunks) == 1
    assert chunks[0].content.index("Payment") < chunks[0].content.index("Invoices")
    assert chunks[0].content.index("Invoices") < chunks[0].content.index(
        "Late balances"
    )
    assert chunks[0].section_title == "Payment"
    assert chunks[0].source_block_indices == [0, 1, 2]
    assert chunks[0].block_type == "mixed"


def test_chunker_skips_empty_blocks_and_keeps_page_span() -> None:
    extracted = DocumentExtractionResult(
        file_type="pdf",
        filename="report.pdf",
        blocks=[
            ExtractionBlock(
                block_type="paragraph", text="First page.", page_number=1, block_index=4
            ),
            ExtractionBlock(
                block_type="paragraph", text="   ", page_number=2, block_index=5
            ),
            ExtractionBlock(
                block_type="paragraph",
                text="Second page.",
                page_number=2,
                block_index=6,
            ),
        ],
    )

    chunks = _chunker().chunk_document(extracted, "doc-2")

    assert len(chunks) == 1
    assert chunks[0].page_number is None
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
    assert chunks[0].source_block_indices == [4, 6]


def test_chunker_splits_oversized_paragraph_with_overlap_without_losing_words() -> None:
    words = [f"term{i}" for i in range(100)]
    extracted = DocumentExtractionResult(
        file_type="docx",
        filename="long.docx",
        blocks=[
            ExtractionBlock(block_type="paragraph", text=" ".join(words), block_index=0)
        ],
    )

    chunks = _chunker(target_tokens=20, overlap_tokens=5, max_tokens=24).chunk_document(
        extracted, "doc-3"
    )

    assert len(chunks) > 1
    assert all(chunk.token_count <= 24 for chunk in chunks)
    assert all(
        chunk.token_counting_method == "tiktoken:cl100k_base" for chunk in chunks
    )
    observed_words = {word for chunk in chunks for word in chunk.content.split()}
    assert set(words) <= observed_words
    assert chunks[0].chunk_index == 0
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunker_splits_tables_and_repeats_header_context() -> None:
    rows = [["Column A", "Column B"]] + [[f"row{i}-a", f"row{i}-b"] for i in range(12)]
    extracted = DocumentExtractionResult(
        file_type="docx",
        filename="table.docx",
        blocks=[
            ExtractionBlock(
                block_type="table",
                text="table source text",
                section_title="Schedule",
                block_index=7,
                metadata={"rows": rows},
            )
        ],
    )

    chunks = _chunker(target_tokens=12, overlap_tokens=3, max_tokens=16).chunk_document(
        extracted, "doc-4"
    )

    assert len(chunks) > 1
    assert all("Column A | Column B" in chunk.content for chunk in chunks)
    assert all(chunk.page_number is None for chunk in chunks)
    assert all(chunk.block_type == "table" for chunk in chunks)
    assert all(chunk.source_block_indices == [7] for chunk in chunks)
    assert all(chunk.source_metadata["table_rows"][0] == rows[0] for chunk in chunks)
    for index in range(12):
        assert any(f"row{index}-a" in chunk.content for chunk in chunks)


def test_chunker_is_deterministic_and_does_not_split_small_paragraphs() -> None:
    extracted = DocumentExtractionResult(
        file_type="docx",
        filename="small.docx",
        blocks=[
            ExtractionBlock(block_type="paragraph", text="Small one.", block_index=0),
            ExtractionBlock(block_type="paragraph", text="Small two.", block_index=1),
        ],
    )
    chunker = _chunker()

    first = chunker.chunk_document(extracted, "doc-5")
    second = chunker.chunk_document(extracted, "doc-5")

    assert [chunk.model_dump() for chunk in first] == [
        chunk.model_dump() for chunk in second
    ]
    assert len(first) == 1
    assert first[0].content == "Small one.\n\nSmall two."
