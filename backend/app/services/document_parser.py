from __future__ import annotations

from io import BytesIO
from typing import Any

from pydantic import BaseModel, Field


class ExtractionBlock(BaseModel):
    block_type: str
    text: str
    page_number: int | None = None
    section_title: str | None = None
    block_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentExtractionResult(BaseModel):
    file_type: str
    filename: str
    blocks: list[ExtractionBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def parse_pdf(
    file_bytes: bytes, filename: str = "document.pdf"
) -> DocumentExtractionResult:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency installed during setup
        raise RuntimeError("PyMuPDF is not installed.") from exc

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    blocks: list[ExtractionBlock] = []
    warnings: list[str] = []

    for page_number in range(doc.page_count):
        page = doc[page_number]
        text = _normalize_text(page.get_text("text"))
        if not text:
            warnings.append(f"Page {page_number + 1} contains no extractable text.")
            continue
        blocks.append(
            ExtractionBlock(
                block_type="paragraph",
                text=text,
                page_number=page_number + 1,
                block_index=len(blocks),
                metadata={"source": "pdf"},
            )
        )

    if not blocks:
        raise ValueError("The PDF does not contain any extractable text.")

    return DocumentExtractionResult(
        file_type="pdf",
        filename=filename,
        blocks=blocks,
        warnings=warnings,
    )


def parse_docx(
    file_bytes: bytes, filename: str = "document.docx"
) -> DocumentExtractionResult:
    try:
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover - dependency installed during setup
        raise RuntimeError("python-docx is not installed.") from exc

    document = Document(BytesIO(file_bytes))
    blocks: list[ExtractionBlock] = []
    warnings: list[str] = []
    current_section_title: str | None = None
    block_index = 0

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue

            style_name = (paragraph.style.name if paragraph.style else "").lower()
            block_type = (
                "heading"
                if style_name.startswith("heading") or style_name == "title"
                else "paragraph"
            )
            if block_type == "heading":
                current_section_title = text

            blocks.append(
                ExtractionBlock(
                    block_type=block_type,
                    text=_normalize_text(text),
                    page_number=None,
                    section_title=current_section_title,
                    block_index=block_index,
                )
            )
            block_index += 1
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if not rows:
                continue
            table_text = "\n".join(" | ".join(row) for row in rows)
            blocks.append(
                ExtractionBlock(
                    block_type="table",
                    text=_normalize_text(table_text),
                    section_title=current_section_title,
                    block_index=block_index,
                    metadata={"rows": rows},
                )
            )
            block_index += 1

    if not blocks:
        warnings.append(
            "The document does not contain any readable paragraphs or tables."
        )
        raise ValueError("The document does not contain any readable content.")

    return DocumentExtractionResult(
        file_type="docx",
        filename=filename,
        blocks=blocks,
        warnings=warnings,
    )
