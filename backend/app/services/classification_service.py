"""
ClassificationService — DB-aware document type classification.

Pipeline for a single document:
  1. Load Document ORM record.
  2. Load ParsedDocument from cache (data/processed/).
     If cache missing → run Phase 4 (parse) first.
  3. Guard: if document still needs OCR → run Phase 5 first.
  4. Run classifier.classify_document() with the full text.
  5. Update Document record:
       - document_type
       - classification_confidence
       - classification_reason
       - processing_status → CLASSIFYING → COMPLETED (or back to OCR_PROCESSING if needed)
  6. Caller commits the DB session.

Status flow:
  COMPLETED (from parse/OCR) → CLASSIFYING → COMPLETED  (happy path)
  OCR_PROCESSING → classification deferred (returns None, logs warning)
  FAILED → classification skipped

Classification is intentionally re-runnable:
  Calling classify_document() again on an already-classified document
  overwrites the previous result. This is intentional — it lets
  underwriters trigger reclassification after OCR quality improves.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.classifier import ClassificationResult, classify_document
from app.core.constants import DocumentProcessingStatus
from app.core.exceptions import DocumentParsingError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.ingestion.models import ParsedDocument
from app.repositories.document_repository import DocumentRepository
from app.services.document_processing_service import DocumentProcessingService

logger = get_logger(__name__)


class ClassificationService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self._parse_svc = DocumentProcessingService(db)

    async def classify_document(
        self,
        document_id: UUID,
        use_llm: bool = True,
    ) -> ClassificationResult | None:
        """
        Classify a single document and update its DB record.

        Returns None if classification was skipped (e.g. still needs OCR).
        Returns ClassificationResult on success.
        Raises DocumentParsingError if no text could be obtained.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        # Skip if document failed processing
        if doc.processing_status == DocumentProcessingStatus.FAILED.value:
            logger.warning(
                "Skipping classification for failed document",
                document_id=str(document_id),
            )
            return None

        async with StageLogger(
            stage=ProcessingStage.CLASSIFICATION,
            document_id=str(document_id),
        ):
            # Mark as classifying
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.CLASSIFYING.value,
            })

            # Load ParsedDocument from cache
            parsed = await self._parse_svc.load_parsed_output(
                submission_id=doc.submission_id,
                document_id=document_id,
            )

            if parsed is None:
                logger.info(
                    "No parse cache — running parser first",
                    document_id=str(document_id),
                )
                parsed = await self._parse_svc.process_document(document_id)
                doc = await self.doc_repo.get_by_id_or_raise(document_id)

            # Defer if OCR is still needed
            if parsed.needs_ocr or doc.processing_status == DocumentProcessingStatus.OCR_PROCESSING.value:
                logger.warning(
                    "Document still needs OCR — deferring classification",
                    document_id=str(document_id),
                )
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.OCR_PROCESSING.value,
                })
                return None

            # Get extension from stored filename
            ext = doc.file_extension or ""

            # Run classifier
            try:
                result = await classify_document(
                    text=parsed.full_text,
                    extension=ext,
                    filename=doc.original_filename,
                    use_llm=use_llm,
                )
            except Exception as exc:
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.COMPLETED.value,
                    "document_type": "OTHER",
                    "classification_confidence": 0.0,
                    "classification_reason": f"Classification error: {exc}"[:500],
                })
                raise

            # Update Document record
            await self.doc_repo.update(doc, {
                "document_type": result.document_type.value,
                "classification_confidence": round(result.confidence, 4),
                "classification_reason": result.classification_reason[:1000],
                "processing_status": DocumentProcessingStatus.COMPLETED.value,
            })

            logger.info(
                "Document classified",
                document_id=str(document_id),
                doc_type=result.document_type.value,
                confidence=round(result.confidence, 3),
                classified_by=result.classified_by,
                filename=doc.original_filename,
            )

            return result

    async def classify_all_for_submission(
        self,
        submission_id: UUID,
        use_llm: bool = True,
    ) -> list[ClassificationResult]:
        """
        Classify all documents in a submission that are ready for classification.

        Skips documents in FAILED or OCR_PROCESSING state.
        Continues past per-document errors.

        Returns list of successful ClassificationResult objects.
        """
        docs = await self.doc_repo.get_by_submission(submission_id, current_only=True)

        # Eligible: COMPLETED from parse/OCR, or already classified (re-run case)
        eligible_statuses = {
            DocumentProcessingStatus.COMPLETED.value,
            DocumentProcessingStatus.CLASSIFYING.value,
        }
        eligible = [d for d in docs if d.processing_status in eligible_statuses]

        if not eligible:
            logger.info(
                "No documents ready for classification",
                submission_id=str(submission_id),
                total_docs=len(docs),
            )
            return []

        logger.info(
            "Classifying documents",
            submission_id=str(submission_id),
            count=len(eligible),
        )

        results: list[ClassificationResult] = []
        for doc in eligible:
            try:
                result = await self.classify_document(doc.id, use_llm=use_llm)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.error(
                    "Classification failed — skipping document",
                    document_id=str(doc.id),
                    filename=doc.original_filename,
                    error=str(exc),
                )

        return results
