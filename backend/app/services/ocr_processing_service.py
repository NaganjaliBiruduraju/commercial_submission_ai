"""
OCRProcessingService — DB-aware OCR orchestration.

Ties together:
  - Document DB record (status, page_count, is_scanned)
  - File reading from disk
  - OCR via ocr_service.run_ocr_async()
  - ParsedDocument cache (read existing, write updated)
  - DocumentProcessingService.process_document() fallback if no cached
    parse result exists yet

Processing flow:
  1. Load Document ORM record → verify it's in OCR_PROCESSING state.
  2. Try to load cached ParsedDocument from data/processed/.
     If not found → run Phase 4 parsing first (parse then OCR).
  3. Read raw file bytes from disk.
  4. Run OCR async (thread pool) → updated ParsedDocument.
  5. Save updated ParsedDocument cache.
  6. Update Document DB record:
     - processing_status → COMPLETED
     - page_count (may have changed after OCR revealed more content)
  7. Caller commits the DB session.

Status transitions:
  OCR_PROCESSING → COMPLETED  (success)
  OCR_PROCESSING → FAILED     (unrecoverable OCR error)
  PENDING → PARSING → OCR_PROCESSING → COMPLETED  (cold start, no cache)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentProcessingStatus
from app.core.exceptions import DocumentParsingError, OCRError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.ingestion.models import ParsedDocument
from app.ingestion.ocr_service import ocr_availability_info, run_ocr_async
from app.repositories.document_repository import DocumentRepository
from app.services.document_processing_service import (
    DocumentProcessingService,
    _read_file_bytes,
    _save_parsed_output,
)

logger = get_logger(__name__)


class OCRProcessingService:
    """
    DB-aware OCR orchestration service.

    Usage:
        svc = OCRProcessingService(db)
        parsed = await svc.run_ocr_for_document(document_id)
        await db.commit()
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self._parse_svc = DocumentProcessingService(db)

    async def run_ocr_for_document(
        self,
        document_id: UUID,
        lang: str = "eng",
    ) -> ParsedDocument:
        """
        Run OCR for a single document and update its DB record.

        Returns the updated ParsedDocument on success.
        Raises OCRError / DocumentParsingError on fatal failure (after
        updating the document's processing_status to FAILED).
        """
        from app.core.config import get_settings
        settings = get_settings()

        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        async with StageLogger(stage=ProcessingStage.OCR, document_id=str(document_id)):
            # Step 1: Ensure we have a ParsedDocument (from cache or fresh parse)
            parsed = await self._parse_svc.load_parsed_output(
                submission_id=doc.submission_id,
                document_id=document_id,
            )

            if parsed is None:
                logger.info(
                    "No cached parse result — running Phase 4 parser first",
                    document_id=str(document_id),
                )
                # Phase 4 parse — sets processing_status = OCR_PROCESSING automatically
                parsed = await self._parse_svc.process_document(document_id)
                # Reload doc record (status now updated)
                doc = await self.doc_repo.get_by_id_or_raise(document_id)

            if not parsed.needs_ocr:
                logger.info(
                    "Document does not need OCR — marking complete",
                    document_id=str(document_id),
                )
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.COMPLETED.value,
                })
                return parsed

            # Step 2: Read raw file bytes
            try:
                file_bytes = await _read_file_bytes(
                    upload_dir=settings.upload_dir,
                    submission_id=str(doc.submission_id),
                    stored_filename=doc.stored_filename,
                )
            except Exception as exc:
                await self._mark_failed(doc, str(exc))
                raise

            # Step 3: Run OCR
            try:
                parsed = await run_ocr_async(
                    file_bytes=file_bytes,
                    parsed_doc=parsed,
                    lang=lang,
                )
            except (OCRError, DocumentParsingError) as exc:
                await self._mark_failed(doc, str(exc))
                raise
            except Exception as exc:
                await self._mark_failed(doc, f"Unexpected OCR error: {exc}")
                raise OCRError(str(exc)) from exc

            # Step 4: Save updated cache
            await _save_parsed_output(
                parsed=parsed,
                upload_dir=settings.upload_dir,
                submission_id=str(doc.submission_id),
                document_id=str(document_id),
            )

            # Step 5: Update Document DB record
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.COMPLETED.value,
                "page_count": parsed.page_count,
                "is_scanned": True,
                "failure_reason": None,
            })

            logger.info(
                "OCR processing complete",
                document_id=str(document_id),
                page_count=parsed.page_count,
                char_count=parsed.total_chars(),
                mean_confidence=parsed.metadata.get("ocr_mean_confidence"),
            )

            return parsed

    async def run_ocr_for_submission(
        self,
        submission_id: UUID,
        lang: str = "eng",
    ) -> list[ParsedDocument]:
        """
        Run OCR on all documents in OCR_PROCESSING state for a submission.

        Continues on per-document failures — logs and skips failed docs.
        Returns list of successfully OCR-processed ParsedDocuments.
        """
        docs = await self.doc_repo.get_by_submission(submission_id, current_only=True)
        ocr_pending = [
            d for d in docs
            if d.processing_status == DocumentProcessingStatus.OCR_PROCESSING.value
        ]

        if not ocr_pending:
            logger.info(
                "No documents waiting for OCR",
                submission_id=str(submission_id),
            )
            return []

        logger.info(
            "Running OCR for submission",
            submission_id=str(submission_id),
            count=len(ocr_pending),
        )

        results: list[ParsedDocument] = []
        for doc in ocr_pending:
            try:
                parsed = await self.run_ocr_for_document(doc.id, lang=lang)
                results.append(parsed)
            except Exception as exc:
                logger.error(
                    "OCR failed for document — skipping",
                    document_id=str(doc.id),
                    filename=doc.original_filename,
                    error=str(exc),
                )

        return results

    async def _mark_failed(self, doc: object, reason: str) -> None:
        """Update document status to FAILED with the given reason."""
        try:
            await self.doc_repo.update(doc, {  # type: ignore[arg-type]
                "processing_status": DocumentProcessingStatus.FAILED.value,
                "failure_reason": reason[:2000],
            })
            logger.error(
                "Document OCR failed",
                document_id=str(doc.id),  # type: ignore[attr-defined]
                reason=reason[:200],
            )
        except Exception:
            pass  # best-effort

    @staticmethod
    def ocr_status() -> dict:
        """Return OCR system availability info for health checks."""
        return ocr_availability_info()
