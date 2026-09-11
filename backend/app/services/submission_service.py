"""
SubmissionService — submission lifecycle and document upload management.

Responsibilities:
  - Create new submissions with auto-generated submission numbers
  - Validate and store uploaded documents (file validation + DB record creation)
  - Handle document re-upload (versioning)
  - Provide submission detail and list queries

File upload flow:
  1. Validate file extension and size (before reading full bytes)
  2. Read file bytes into memory
  3. Validate MIME type against actual file bytes
  4. Write bytes to disk (async, UUID filename)
  5. Create Document ORM record in DB
  6. If a document with the same original_filename already exists in this
     submission, mark previous versions as is_current_version=False

Rollback:
  If the DB commit fails after the file has been written, the orphaned file
  is deleted (best-effort). The transaction is rolled back by the session
  dependency in get_db().
"""
from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    DocumentValidationError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.document import Document, DocumentVersion
from app.models.submission import Submission
from app.repositories.document_repository import (
    DocumentRepository,
    DocumentVersionRepository,
)
from app.repositories.submission_repository import SubmissionRepository
from app.schemas.document import DocumentResponse, DocumentSummary, DocumentVersionResponse
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionResponse,
    SubmissionSummary,
    SubmissionUpdate,
)
from app.schemas.user import UserSummary
from app.utils.file_utils import (
    delete_upload_file,
    save_upload_file,
    validate_filename,
    validate_mime_type,
)

logger = get_logger(__name__)

# Maximum bytes to read for MIME detection
_MIME_HEADER_SIZE = 512


def _user_summary_from_user(user) -> UserSummary | None:
    if user is None:
        return None
    return UserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name if user.role else "",
    )


def _document_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        submission_id=doc.submission_id,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        file_extension=doc.file_extension,
        document_type=doc.document_type,
        classification_confidence=doc.classification_confidence,
        classification_reason=doc.classification_reason,
        processing_status=doc.processing_status,
        failure_reason=doc.failure_reason,
        page_count=doc.page_count,
        is_scanned=doc.is_scanned,
        version_number=doc.version_number,
        is_current_version=doc.is_current_version,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _submission_to_response(sub: Submission, doc_count: int = 0) -> SubmissionResponse:
    return SubmissionResponse(
        id=sub.id,
        submission_number=sub.submission_number,
        applicant_name=sub.applicant_name,
        applicant_business_type=sub.applicant_business_type,
        applicant_industry=sub.applicant_industry,
        broker_name=sub.broker_name,
        broker_email=sub.broker_email,
        broker_company=sub.broker_company,
        status=sub.status,
        failure_reason=sub.failure_reason,
        assigned_to=sub.assigned_to,
        assigned_underwriter=_user_summary_from_user(sub.assigned_underwriter),
        created_by=sub.created_by,
        creator=_user_summary_from_user(sub.creator),
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


class SubmissionService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.sub_repo = SubmissionRepository(db)
        self.doc_repo = DocumentRepository(db)
        self.ver_repo = DocumentVersionRepository(db)

    # ---------------------------------------------------------------------- #
    # Submission CRUD
    # ---------------------------------------------------------------------- #

    async def create_submission(
        self, payload: SubmissionCreate, created_by_id: UUID
    ) -> SubmissionResponse:
        """Create a new submission and return it."""
        submission_number = await self.sub_repo.get_next_submission_number()

        submission = Submission(
            submission_number=submission_number,
            broker_name=payload.broker_name,
            broker_email=payload.broker_email,
            broker_company=payload.broker_company,
            created_by=created_by_id,
        )
        sub = await self.sub_repo.create(submission)
        await self.db.commit()
        await self.db.refresh(sub)

        logger.info(
            "Submission created",
            submission_number=submission_number,
            created_by=str(created_by_id),
        )
        return _submission_to_response(sub)

    async def get_submission(self, submission_id: UUID) -> SubmissionResponse:
        sub = await self.sub_repo.get_with_relations(submission_id)
        if sub is None:
            raise NotFoundError("Submission", str(submission_id))
        doc_count = await self.doc_repo.count_by_submission(submission_id)
        return _submission_to_response(sub, doc_count)

    async def list_submissions(
        self,
        *,
        status=None,
        assigned_to: UUID | None = None,
        created_by: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SubmissionSummary], int]:
        offset = (page - 1) * page_size
        subs, total = await self.sub_repo.list_submissions(
            status=status,
            assigned_to=assigned_to,
            created_by=created_by,
            offset=offset,
            limit=page_size,
        )

        summaries: list[SubmissionSummary] = []
        for sub in subs:
            doc_count = await self.doc_repo.count_by_submission(sub.id)
            summaries.append(
                SubmissionSummary(
                    id=sub.id,
                    submission_number=sub.submission_number,
                    applicant_name=sub.applicant_name,
                    broker_name=sub.broker_name,
                    broker_company=sub.broker_company,
                    status=sub.status,
                    assigned_underwriter=_user_summary_from_user(
                        sub.assigned_underwriter
                    ),
                    document_count=doc_count,
                    created_at=sub.created_at,
                    updated_at=sub.updated_at,
                )
            )
        return summaries, total

    async def update_submission(
        self, submission_id: UUID, payload: SubmissionUpdate
    ) -> SubmissionResponse:
        sub = await self.sub_repo.get_with_relations(submission_id)
        if sub is None:
            raise NotFoundError("Submission", str(submission_id))

        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if updates:
            sub = await self.sub_repo.update(sub, updates)
            await self.db.commit()
            sub = await self.sub_repo.get_with_relations(submission_id)

        return _submission_to_response(sub)  # type: ignore[arg-type]

    # ---------------------------------------------------------------------- #
    # Document Upload
    # ---------------------------------------------------------------------- #

    async def upload_document(
        self,
        submission_id: UUID,
        upload: UploadFile,
        uploaded_by_id: UUID,
        change_note: str | None = None,
    ) -> DocumentResponse:
        """
        Validate, store, and register a single uploaded document.

        Steps:
          1. Confirm submission exists (raises NotFoundError if not)
          2. Check submission document count limit
          3. Validate file extension
          4. Read file bytes + validate size
          5. Validate MIME type
          6. Write file to disk (async)
          7. Insert Document record; handle versioning
          8. Commit transaction; rollback file on DB failure

        Returns the new DocumentResponse.
        """
        settings = get_settings()

        # 1. Confirm submission exists
        sub = await self.sub_repo.get_by_id(submission_id)
        if sub is None:
            raise NotFoundError("Submission", str(submission_id))

        # 2. Check document count limit
        current_count = await self.doc_repo.count_by_submission(submission_id)
        if current_count >= settings.max_files_per_submission:
            raise DocumentValidationError(
                f"Submission already has {current_count} documents. "
                f"Maximum is {settings.max_files_per_submission}.",
                filename=upload.filename,
            )

        original_filename = upload.filename or "unknown"

        # 3. Validate extension
        extension = validate_filename(original_filename)

        # 4. Read bytes + size check
        # Read up to max_size + 1 so we detect oversized files without
        # reading the entire file if it's huge
        max_bytes = settings.max_upload_size_bytes + 1
        raw_bytes = await upload.read(max_bytes)

        if len(raw_bytes) > settings.max_upload_size_bytes:
            raise DocumentValidationError(
                f"File '{original_filename}' exceeds maximum size of "
                f"{settings.max_upload_size_mb} MB.",
                filename=original_filename,
            )

        if len(raw_bytes) == 0:
            raise DocumentValidationError(
                f"File '{original_filename}' is empty.",
                filename=original_filename,
            )

        # 5. Validate MIME type from file bytes
        mime_type = validate_mime_type(raw_bytes[:_MIME_HEADER_SIZE], original_filename, extension)

        # 6. Write to disk
        stored_filename, checksum, file_size = await save_upload_file(
            file_data=raw_bytes,
            submission_id=str(submission_id),
            extension=extension,
        )

        # 7. DB record — with versioning
        try:
            # Check if a document with this original_filename already exists
            prev_version_count = await self.doc_repo.mark_previous_versions(
                submission_id, original_filename
            )
            max_version = await self.doc_repo.get_max_version_number(
                submission_id, original_filename
            )
            version_number = max_version + 1 if prev_version_count > 0 else 1

            doc = Document(
                submission_id=submission_id,
                uploaded_by=uploaded_by_id,
                original_filename=original_filename,
                stored_filename=stored_filename,
                mime_type=mime_type,
                file_size_bytes=file_size,
                file_extension=extension,
                checksum_sha256=checksum,
                version_number=version_number,
                is_current_version=True,
                created_by=uploaded_by_id,
            )
            saved_doc = await self.doc_repo.create(doc)

            # Create corresponding DocumentVersion record
            doc_version = DocumentVersion(
                document_id=saved_doc.id,
                version_number=version_number,
                stored_filename=stored_filename,
                file_size_bytes=file_size,
                checksum_sha256=checksum,
                uploaded_by=uploaded_by_id,
                change_note=change_note,
            )
            await self.ver_repo.create(doc_version)

            await self.db.commit()
            await self.db.refresh(saved_doc)

        except Exception as exc:
            # Roll back the file we just wrote before re-raising
            await delete_upload_file(str(submission_id), stored_filename)
            logger.error(
                "Document DB insert failed — file cleaned up",
                filename=original_filename,
                stored_filename=stored_filename,
                error=str(exc),
            )
            raise

        logger.info(
            "Document uploaded",
            document_id=str(saved_doc.id),
            submission_id=str(submission_id),
            filename=original_filename,
            version=version_number,
            size_bytes=file_size,
        )

        return _document_to_response(saved_doc)

    async def list_documents(
        self,
        submission_id: UUID,
        *,
        current_only: bool = True,
    ) -> list[DocumentResponse]:
        """Return all documents for a submission."""
        sub = await self.sub_repo.get_by_id(submission_id)
        if sub is None:
            raise NotFoundError("Submission", str(submission_id))

        docs = await self.doc_repo.get_by_submission(
            submission_id, current_only=current_only
        )
        return [_document_to_response(d) for d in docs]

    async def get_document(
        self, submission_id: UUID, document_id: UUID
    ) -> DocumentResponse:
        doc = await self.doc_repo.get_by_id(document_id)
        if doc is None or doc.submission_id != submission_id:
            raise NotFoundError("Document", str(document_id))
        return _document_to_response(doc)

    async def get_document_versions(
        self, submission_id: UUID, document_id: UUID
    ) -> list[DocumentVersionResponse]:
        doc = await self.doc_repo.get_by_id(document_id)
        if doc is None or doc.submission_id != submission_id:
            raise NotFoundError("Document", str(document_id))

        versions = await self.ver_repo.get_versions_for_document(document_id)
        return [
            DocumentVersionResponse(
                id=v.id,
                document_id=v.document_id,
                version_number=v.version_number,
                file_size_bytes=v.file_size_bytes,
                checksum_sha256=v.checksum_sha256,
                uploaded_by=v.uploaded_by,
                change_note=v.change_note,
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
            for v in versions
        ]

    async def upload_multiple_documents(
        self,
        submission_id: UUID,
        uploads: list[UploadFile],
        uploaded_by_id: UUID,
    ) -> list[DocumentResponse]:
        """
        Upload up to MAX_FILES_PER_SUBMISSION files in one call.

        Returns a list of DocumentResponse for each file.
        Stops on first error — partial uploads may have been persisted.
        The caller can inspect the response to see which succeeded.
        """
        settings = get_settings()

        if len(uploads) > settings.max_files_per_submission:
            raise DocumentValidationError(
                f"Cannot upload {len(uploads)} files at once. "
                f"Maximum is {settings.max_files_per_submission} per submission."
            )

        results: list[DocumentResponse] = []
        for upload in uploads:
            doc_response = await self.upload_document(
                submission_id=submission_id,
                upload=upload,
                uploaded_by_id=uploaded_by_id,
            )
            results.append(doc_response)

        return results
