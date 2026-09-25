"""
Knowledge base API endpoints — admin-only.

Admins upload underwriting guidelines, coverage rules, and FAQs.
Documents are approved, chunked, embedded, and indexed for RAG retrieval.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import AdminDep, DatabaseDep
from app.schemas.base import APIResponse
from app.core.constants import KnowledgeDocumentStatus
from app.core.logging import get_logger
from app.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


# --------------------------------------------------------------------------- #
# Request/Response models
# --------------------------------------------------------------------------- #

class KnowledgeDocumentOut(BaseModel):
    id: str
    title: str
    category: str
    version: str
    status: str
    is_indexed: bool
    chunk_count: int | None
    original_filename: str
    file_size_bytes: int | None
    uploaded_by: str | None
    approved_by: str | None
    effective_date: str | None
    expiration_date: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class KnowledgeChunkOut(BaseModel):
    id: str
    chunk_text: str
    chunk_index: int
    page_number: int | None
    section: str | None
    similarity: float | None = None

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.post(
    "/upload",
    response_model=APIResponse[KnowledgeDocumentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge document (admin only)",
)
async def upload_knowledge_document(
    current_user: AdminDep,
    db: DatabaseDep,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    version: str = Form(...),
    description: str | None = Form(None),
    effective_date: str | None = Form(None),
    expiration_date: str | None = Form(None),
) -> APIResponse[KnowledgeDocumentOut]:
    """
    Upload a new knowledge document.

    Supported formats: PDF, DOCX, TXT.
    Document starts in DRAFT status — must be approved before indexing.
    """
    content = await file.read()
    mime_type = file.content_type or "application/octet-stream"

    svc = KnowledgeService(db)
    doc = await svc.upload_document(
        uploaded_file=content,
        original_filename=file.filename or "unknown",
        mime_type=mime_type,
        title=title,
        category=category,
        version=version,
        uploaded_by=current_user.id,
        description=description,
        effective_date=effective_date,
        expiration_date=expiration_date,
    )
    await db.commit()

    return APIResponse.created(
        KnowledgeDocumentOut.model_validate(doc),
        message="Knowledge document uploaded successfully. Approve to index for RAG.",
    )


@router.post(
    "/{document_id}/approve",
    response_model=APIResponse[KnowledgeDocumentOut],
    status_code=status.HTTP_200_OK,
    summary="Approve and index a knowledge document",
)
async def approve_knowledge_document(
    document_id: UUID,
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[KnowledgeDocumentOut]:
    """
    Approve a DRAFT document, change status to ACTIVE, extract text, chunk, embed, and index.
    """
    svc = KnowledgeService(db)
    doc = await svc.approve_document(document_id, approved_by=current_user.id)
    await db.commit()

    return APIResponse.ok(
        KnowledgeDocumentOut.model_validate(doc),
        message=f"Document approved and indexed ({doc.chunk_count} chunks).",
    )


@router.post(
    "/{document_id}/reindex",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Re-index a knowledge document",
)
async def reindex_knowledge_document(
    document_id: UUID,
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[dict]:
    """
    Re-run chunking and embedding for an existing document.
    Replaces old chunks.
    """
    svc = KnowledgeService(db)
    chunk_count = await svc.index_document(document_id)
    await db.commit()

    return APIResponse.ok({
        "document_id": str(document_id),
        "chunk_count": chunk_count,
    })


@router.post(
    "/rebuild-index",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Rebuild the entire vector index",
)
async def rebuild_vector_index(
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[dict]:
    """
    Rebuild the in-memory vector index from all ACTIVE indexed documents.
    Call this after bulk document approval or after startup.
    """
    svc = KnowledgeService(db)
    count = await svc.rebuild_index()
    await db.commit()

    return APIResponse.ok({
        "indexed_chunks": count,
        "message": "Vector index rebuilt successfully.",
    })


@router.get(
    "",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="List knowledge documents",
)
async def list_knowledge_documents(
    current_user: AdminDep,
    db: DatabaseDep,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> APIResponse[dict]:
    """
    List all knowledge documents with optional filters.
    """
    svc = KnowledgeService(db)
    docs, total = await svc.list_documents(
        status=status_filter,
        category=category,
        offset=offset,
        limit=limit,
    )

    return APIResponse.ok({
        "documents": [KnowledgeDocumentOut.model_validate(d) for d in docs],
        "total": total,
        "offset": offset,
        "limit": limit,
    })


@router.delete(
    "/{document_id}",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete a knowledge document",
)
async def delete_knowledge_document(
    document_id: UUID,
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[dict]:
    """
    Delete a knowledge document and all its chunks.
    Invalidates the vector index cache.
    """
    svc = KnowledgeService(db)
    await svc.delete_document(document_id)
    await db.commit()

    return APIResponse.ok({
        "document_id": str(document_id),
        "message": "Knowledge document deleted.",
    })


@router.post(
    "/search",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Search the knowledge base (RAG retrieval test)",
)
async def search_knowledge(
    current_user: AdminDep,
    db: DatabaseDep,
    query: str = Query(..., min_length=3),
    top_k: int = Query(5, ge=1, le=20),
) -> APIResponse[dict]:
    """
    Test RAG retrieval — find the most relevant knowledge chunks for a query.
    """
    from app.rag import retrieve_chunks

    chunks = await retrieve_chunks(query=query, top_k=top_k, db=db, rebuild_index=False)

    return APIResponse.ok({
        "query": query,
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "chunk_text": c.chunk_text[:300] + "..." if len(c.chunk_text) > 300 else c.chunk_text,
                "similarity": c.similarity,
                "section": c.section,
                "page": c.page_number,
                "metadata": c.metadata,
            }
            for c in chunks
        ],
    })
