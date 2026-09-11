"""
Submissions router — /api/v1/submissions

Endpoints:
  POST   /                         — create a new submission
  GET    /                         — list submissions (paginated, filtered)
  GET    /{submission_id}          — get submission detail
  PATCH  /{submission_id}          — update submission metadata
  POST   /{submission_id}/documents                — upload document(s)
  GET    /{submission_id}/documents                — list documents
  GET    /{submission_id}/documents/{document_id}  — get document detail
  GET    /{submission_id}/documents/{document_id}/versions — version history

Access:
  - UNDERWRITER and ADMIN can create and upload
  - REVIEWER, UNDERWRITER, ADMIN can read
  - Only ADMIN and UNDERWRITER can update
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUser, DatabaseDep, ReviewerDep, UnderwriterDep
from app.core.constants import SubmissionStatus
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.document import DocumentResponse, DocumentVersionResponse
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionResponse,
    SubmissionSummary,
    SubmissionUpdate,
)
from app.services.submission_service import SubmissionService
from app.services.document_processing_service import DocumentProcessingService
from app.services.ocr_processing_service import OCRProcessingService
from app.services.classification_service import ClassificationService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/submissions", tags=["Submissions"])


# --------------------------------------------------------------------------- #
# Submission CRUD
# --------------------------------------------------------------------------- #

@router.post(
    "",
    response_model=APIResponse[SubmissionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new submission",
    description=(
        "Creates a new submission shell. "
        "Broker details are optional at creation — they can be provided at upload time. "
        "Returns a submission_number (e.g. SUB-20250901-0001) for tracking."
    ),
)
async def create_submission(
    payload: SubmissionCreate,
    current_user: UnderwriterDep,
    db: DatabaseDep,
) -> APIResponse[SubmissionResponse]:
    svc = SubmissionService(db)
    submission = await svc.create_submission(payload, created_by_id=current_user.id)
    return APIResponse.ok(submission)


@router.get(
    "",
    response_model=APIResponse[PaginatedResponse[SubmissionSummary]],
    summary="List submissions",
)
async def list_submissions(
    current_user: ReviewerDep,
    db: DatabaseDep,
    submission_status: SubmissionStatus | None = Query(
        default=None, alias="status", description="Filter by pipeline status"
    ),
    assigned_to: UUID | None = Query(default=None, description="Filter by assigned underwriter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> APIResponse[PaginatedResponse[SubmissionSummary]]:
    svc = SubmissionService(db)

    # REVIEWER and UNDERWRITER see only their own submissions
    # ADMIN sees all
    role_name = current_user.role.name if current_user.role else ""
    created_by_filter: UUID | None = None
    if role_name not in ("ADMIN",):
        created_by_filter = current_user.id

    summaries, total = await svc.list_submissions(
        status=submission_status,
        assigned_to=assigned_to,
        created_by=created_by_filter,
        page=page,
        page_size=page_size,
    )
    paginated = PaginatedResponse.create(
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )
    return APIResponse.ok(paginated)


@router.get(
    "/{submission_id}",
    response_model=APIResponse[SubmissionResponse],
    summary="Get submission detail",
)
async def get_submission(
    submission_id: UUID,
    current_user: ReviewerDep,
    db: DatabaseDep,
) -> APIResponse[SubmissionResponse]:
    svc = SubmissionService(db)
    submission = await svc.get_submission(submission_id)
    return APIResponse.ok(submission)


@router.patch(
    "/{submission_id}",
    response_model=APIResponse[SubmissionResponse],
    summary="Update submission metadata",
)
async def update_submission(
    submission_id: UUID,
    payload: SubmissionUpdate,
    current_user: UnderwriterDep,
    db: DatabaseDep,
) -> APIResponse[SubmissionResponse]:
    svc = SubmissionService(db)
    submission = await svc.update_submission(submission_id, payload)
    return APIResponse.ok(submission)


# --------------------------------------------------------------------------- #
# Document Upload and Retrieval
# --------------------------------------------------------------------------- #

@router.post(
    "/{submission_id}/documents",
    response_model=APIResponse[list[DocumentResponse]],
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more documents to a submission",
    description=(
        "Upload PDF, DOCX, XLSX, CSV, or image files. "
        "Files are validated for type (from actual bytes, not just extension) "
        "and size (max 50 MB each). "
        "Uploading a file with the same original name as an existing document "
        "creates a new version — the old version is preserved for audit."
    ),
)
async def upload_documents(
    submission_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
    files: List[UploadFile] = File(
        ...,
        description="One or more files to upload (PDF, DOCX, XLSX, CSV, images)",
    ),
) -> APIResponse[list[DocumentResponse]]:
    svc = SubmissionService(db)
    docs = await svc.upload_multiple_documents(
        submission_id=submission_id,
        uploads=files,
        uploaded_by_id=current_user.id,
    )
    return APIResponse.ok(docs)


@router.get(
    "/{submission_id}/documents",
    response_model=APIResponse[list[DocumentResponse]],
    summary="List documents for a submission",
)
async def list_documents(
    submission_id: UUID,
    current_user: ReviewerDep,
    db: DatabaseDep,
    all_versions: bool = Query(
        default=False,
        description="If true, return all versions; otherwise only current versions",
    ),
) -> APIResponse[list[DocumentResponse]]:
    svc = SubmissionService(db)
    docs = await svc.list_documents(
        submission_id, current_only=not all_versions
    )
    return APIResponse.ok(docs)


@router.get(
    "/{submission_id}/documents/{document_id}",
    response_model=APIResponse[DocumentResponse],
    summary="Get document detail",
)
async def get_document(
    submission_id: UUID,
    document_id: UUID,
    current_user: ReviewerDep,
    db: DatabaseDep,
) -> APIResponse[DocumentResponse]:
    svc = SubmissionService(db)
    doc = await svc.get_document(submission_id, document_id)
    return APIResponse.ok(doc)


@router.get(
    "/{submission_id}/documents/{document_id}/versions",
    response_model=APIResponse[list[DocumentVersionResponse]],
    summary="Get version history for a document",
)
async def get_document_versions(
    submission_id: UUID,
    document_id: UUID,
    current_user: ReviewerDep,
    db: DatabaseDep,
) -> APIResponse[list[DocumentVersionResponse]]:
    svc = SubmissionService(db)
    versions = await svc.get_document_versions(submission_id, document_id)
    return APIResponse.ok(versions)


# --------------------------------------------------------------------------- #
# Document Processing (Phase 4 — trigger parsing pipeline)
# --------------------------------------------------------------------------- #

from app.schemas.base import APIResponse as _APIResponse  # alias to avoid re-import shadowing


class ProcessingResult(_APIResponse):
    pass


@router.post(
    "/{submission_id}/process",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document parsing for all pending documents in a submission",
    description=(
        "Runs the parsing pipeline (Phase 4) on every PENDING document "
        "in the submission. "
        "PDF, DOCX, XLSX, and CSV files are parsed synchronously in a thread pool. "
        "Image files (JPG/PNG) are marked as needing OCR and processed in Phase 5. "
        "Returns a summary of processed documents."
    ),
)
async def process_submission_documents(
    submission_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
) -> APIResponse[dict]:
    svc = DocumentProcessingService(db)
    parsed_docs = await svc.process_all_pending(submission_id)
    await db.commit()

    summary = {
        "submission_id": str(submission_id),
        "documents_processed": len(parsed_docs),
        "documents": [
            {
                "document_id": pd.document_id,
                "filename": pd.original_filename,
                "page_count": pd.page_count,
                "table_count": len(pd.all_tables),
                "needs_ocr": pd.needs_ocr,
                "is_encrypted": pd.is_encrypted,
                "char_count": pd.total_chars(),
                "warnings": pd.parse_warnings,
            }
            for pd in parsed_docs
        ],
    }
    return APIResponse.ok(summary)


@router.post(
    "/{submission_id}/documents/{document_id}/process",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger parsing for a single document",
    description=(
        "Re-parse a specific document (useful after fixing a corrupt upload "
        "or to force reprocessing). Overwrites the cached parsed output."
    ),
)
async def process_single_document(
    submission_id: UUID,
    document_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
) -> APIResponse[dict]:
    svc = DocumentProcessingService(db)
    parsed = await svc.process_document(document_id)
    await db.commit()

    return APIResponse.ok({
        "document_id": parsed.document_id,
        "filename": parsed.original_filename,
        "page_count": parsed.page_count,
        "table_count": len(parsed.all_tables),
        "needs_ocr": parsed.needs_ocr,
        "is_encrypted": parsed.is_encrypted,
        "char_count": parsed.total_chars(),
        "parser_backend": parsed.parser_backend.value,
        "parser_version": parsed.parser_version,
        "warnings": parsed.parse_warnings,
    })


# --------------------------------------------------------------------------- #
# OCR endpoints (Phase 5)
# --------------------------------------------------------------------------- #

@router.post(
    "/{submission_id}/ocr",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run OCR on all documents awaiting OCR in a submission",
    description=(
        "Processes all documents with processing_status=OCR_PROCESSING in this submission. "
        "Scanned PDFs are rendered page-by-page with PyMuPDF then OCR'd with Tesseract. "
        "Images (JPG/PNG) are OCR'd directly. "
        "Returns per-document confidence scores and warnings. "
        "Requires Tesseract to be installed on the server."
    ),
)
async def run_submission_ocr(
    submission_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
    lang: str = Query(default="eng", description="Tesseract language code (e.g. eng, eng+fra)"),
) -> APIResponse[dict]:
    svc = OCRProcessingService(db)
    parsed_docs = await svc.run_ocr_for_submission(submission_id, lang=lang)
    await db.commit()

    return APIResponse.ok({
        "submission_id": str(submission_id),
        "documents_ocred": len(parsed_docs),
        "ocr_status": OCRProcessingService.ocr_status(),
        "documents": [
            {
                "document_id": pd.document_id,
                "filename": pd.original_filename,
                "page_count": pd.page_count,
                "ocr_complete": pd.metadata.get("ocr_complete", False),
                "mean_confidence": pd.metadata.get("ocr_mean_confidence"),
                "total_words": pd.metadata.get("ocr_total_words"),
                "low_confidence_pages": pd.metadata.get("ocr_low_confidence_pages", []),
                "warnings": pd.parse_warnings,
            }
            for pd in parsed_docs
        ],
    })


@router.post(
    "/{submission_id}/documents/{document_id}/ocr",
    response_model=APIResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run OCR on a single document",
    description=(
        "Force OCR on a specific document regardless of current processing_status. "
        "Useful for re-OCRing a document after Tesseract configuration changes."
    ),
)
async def run_document_ocr(
    submission_id: UUID,
    document_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
    lang: str = Query(default="eng", description="Tesseract language code"),
) -> APIResponse[dict]:
    svc = OCRProcessingService(db)
    parsed = await svc.run_ocr_for_document(document_id, lang=lang)
    await db.commit()

    return APIResponse.ok({
        "document_id": parsed.document_id,
        "filename": parsed.original_filename,
        "page_count": parsed.page_count,
        "char_count": parsed.total_chars(),
        "ocr_complete": parsed.metadata.get("ocr_complete", False),
        "mean_confidence": parsed.metadata.get("ocr_mean_confidence"),
        "total_words": parsed.metadata.get("ocr_total_words"),
        "low_confidence_pages": parsed.metadata.get("ocr_low_confidence_pages", []),
        "parser_backend": parsed.parser_backend.value,
        "warnings": parsed.parse_warnings,
    })


# --------------------------------------------------------------------------- #
# Classification endpoints (Phase 6)
# --------------------------------------------------------------------------- #

@router.post(
    "/{submission_id}/classify",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Classify all parsed documents in a submission",
    description=(
        "Runs the classification pipeline on all COMPLETED (parsed) documents. "
        "Uses deterministic keyword rules first; falls back to Groq LLM for "
        "ambiguous or low-confidence results. "
        "Documents in OCR_PROCESSING or FAILED state are skipped."
    ),
)
async def classify_submission_documents(
    submission_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
    use_llm: bool = Query(default=True, description="Enable LLM fallback for ambiguous documents"),
) -> APIResponse[dict]:
    svc = ClassificationService(db)
    results = await svc.classify_all_for_submission(submission_id, use_llm=use_llm)
    await db.commit()

    return APIResponse.ok({
        "submission_id": str(submission_id),
        "documents_classified": len(results),
        "documents": [
            {
                "document_type": r.document_type.value,
                "confidence": r.confidence,
                "classified_by": r.classified_by,
                "reason": r.classification_reason,
                "alternative_type": r.alternative_type.value if r.alternative_type else None,
            }
            for r in results
        ],
    })


@router.post(
    "/{submission_id}/documents/{document_id}/classify",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Classify a single document",
    description="Reclassify a specific document. Overwrites previous classification result.",
)
async def classify_single_document(
    submission_id: UUID,
    document_id: UUID,
    current_user: UnderwriterDep,
    db: DatabaseDep,
    use_llm: bool = Query(default=True, description="Enable LLM fallback"),
) -> APIResponse[dict]:
    svc = ClassificationService(db)
    result = await svc.classify_document(document_id, use_llm=use_llm)
    await db.commit()

    if result is None:
        return APIResponse.ok({
            "document_id": str(document_id),
            "skipped": True,
            "reason": "Document not ready for classification (needs OCR or failed parsing).",
        })

    return APIResponse.ok({
        "document_id": str(document_id),
        "document_type": result.document_type.value,
        "confidence": result.confidence,
        "classified_by": result.classified_by,
        "reason": result.classification_reason,
        "alternative_type": result.alternative_type.value if result.alternative_type else None,
    })
