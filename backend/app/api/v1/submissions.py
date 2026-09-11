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
