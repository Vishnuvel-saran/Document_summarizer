from pydantic import BaseModel


class DocumentProcessingResponse(BaseModel):
    document_id: str
    status: str
    chunk_count: int
    embedding_model: str
    skipped: bool = False
