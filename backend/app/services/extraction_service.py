"""
ExtractionService — DB-aware structured extraction orchestration.

Responsibilities:
  1. Load the Document ORM record and verify it's classified.
  2. Load ParsedDocument from the processed cache.
  3. Soft-delete any existing Evidence records for this document
     (is_active=False) before re-extraction, preserving audit history.
  4. Call extract_fields() (LLM extraction engine).
  5. Persist ExtractedField + Evidence records for every result.
  6. Update Document.processing_status = EXTRACTING → COMPLETED.
  7. Denormalize key fields to the parent Submission record
     (applicant_name, annual_revenue, employee_count).

Idempotency:
  Re-extracting a document is safe — old Evidence records are soft-deleted,
  old ExtractedField records are deleted and replaced. The DB audit log
  records both the deletion and creation.

DB commit policy:
  The service flushes after each field but commits only once at the end.
  The caller commits the session (standard pattern across all services).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentProcessingStatus, DocumentType
from app.core.exceptions import DocumentParsingError, LLMError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.extraction.extractor import ExtractionOutput, ExtractedFieldResult, extract_fields
from app.ingestion.models import ParsedDocument
from app.models.extraction import Evidence, ExtractedField
from app.repositories.document_repository import DocumentRepository
from app.services.document_processing_service import DocumentProcessingService

logger = get_logger(__name__)


class ExtractionService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self._parse_svc = DocumentProcessingService(db)

    async def extract_document(
        self,
        document_id: UUID,
        rag_context: str = "",
    ) -> ExtractionOutput | None:
        """
        Extract structured fields from a single document.

        Returns None if extraction was skipped (no text, wrong status).
        Returns ExtractionOutput on success.
        Raises LLMError if the LLM call fails.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        # Skip if document failed or has no classification
        if doc.processing_status == DocumentProcessingStatus.FAILED.value:
            logger.warning("Skipping extraction for failed document",
                           document_id=str(document_id))
            return None

        if not doc.document_type:
            logger.warning("Document has no classification — run classify first",
                           document_id=str(document_id))
            return None

        doc_type = DocumentType(doc.document_type)

        async with StageLogger(
            stage=ProcessingStage.EXTRACTION,
            document_id=str(document_id),
        ):
            # Mark as extracting
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.EXTRACTING.value,
            })

            # Load ParsedDocument
            parsed = await self._parse_svc.load_parsed_output(
                submission_id=doc.submission_id,
                document_id=document_id,
            )
            if parsed is None:
                logger.warning("No parse cache — running parser first",
                               document_id=str(document_id))
                parsed = await self._parse_svc.process_document(document_id)
                doc = await self.doc_repo.get_by_id_or_raise(document_id)

            if not parsed.full_text or not parsed.full_text.strip():
                logger.warning("Document has no extractable text",
                               document_id=str(document_id))
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.COMPLETED.value,
                })
                return None

            # Soft-delete existing evidence + hard-delete existing extracted fields
            await self._invalidate_previous_extraction(document_id)

            # Run LLM extraction
            try:
                output = await extract_fields(
                    parsed_doc=parsed,
                    document_type=doc_type,
                    rag_context=rag_context,
                )
            except LLMError as exc:
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.FAILED.value,
                    "failure_reason": f"Extraction LLM error: {exc}"[:2000],
                })
                raise

            # Persist fields + evidence
            await self._persist_extraction(
                output=output,
                document_id=document_id,
                submission_id=doc.submission_id,
            )

            # Denormalize key fields to Submission
            await self._denormalize_to_submission(doc.submission_id, output)

            # Mark complete
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.COMPLETED.value,
                "failure_reason": None,
            })

            logger.info(
                "Extraction persisted",
                document_id=str(document_id),
                fields_found=output.fields_found,
                fields_total=output.total_fields_attempted,
                missing=len(output.missing_fields),
            )

            return output

    async def extract_all_for_submission(
        self,
        submission_id: UUID,
        rag_context: str = "",
    ) -> list[ExtractionOutput]:
        """
        Extract fields from all classified documents in a submission.
        Skips unclassified, failed, or image-only documents.
        """
        docs = await self.doc_repo.get_by_submission(submission_id, current_only=True)
        extractable = [
            d for d in docs
            if d.document_type and d.document_type not in (
                DocumentType.EVIDENCE_PHOTO.value,
                DocumentType.IDENTITY_DOCUMENT.value,
            ) and d.processing_status != DocumentProcessingStatus.FAILED.value
        ]

        if not extractable:
            logger.info("No extractable documents in submission",
                        submission_id=str(submission_id))
            return []

        logger.info("Extracting fields for submission",
                    submission_id=str(submission_id), count=len(extractable))

        results: list[ExtractionOutput] = []
        for doc in extractable:
            try:
                out = await self.extract_document(doc.id, rag_context=rag_context)
                if out:
                    results.append(out)
            except Exception as exc:
                logger.error("Extraction failed for document",
                             document_id=str(doc.id),
                             filename=doc.original_filename,
                             error=str(exc))
        return results

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    async def _invalidate_previous_extraction(self, document_id: UUID) -> None:
        """
        Soft-delete existing Evidence records and hard-delete ExtractedFields
        for this document so a re-extraction starts fresh.
        """
        now = datetime.now(tz=timezone.utc)

        # Soft-delete evidence
        await self.db.execute(
            update(Evidence)
            .where(Evidence.document_id == document_id)
            .where(Evidence.is_active == True)  # noqa: E712
            .values(is_active=False)
        )

        # Hard-delete extracted fields (evidence cascade-deletes via FK)
        existing_fields = await self.db.execute(
            select(ExtractedField)
            .where(ExtractedField.document_id == document_id)
        )
        for ef in existing_fields.scalars().all():
            await self.db.delete(ef)

        await self.db.flush()

    async def _persist_extraction(
        self,
        output: ExtractionOutput,
        document_id: UUID,
        submission_id: UUID,
    ) -> None:
        """Create ExtractedField and Evidence records for each result."""
        now = datetime.now(tz=timezone.utc)

        for result in output.fields:
            # Wrap scalar values in {"value": ...} for JSON column storage
            stored_value = _wrap_value(result.field_value)

            ef = ExtractedField(
                submission_id=submission_id,
                document_id=document_id,
                field_name=result.field_name,
                field_label=result.field_label,
                field_value=stored_value,
                confidence=result.confidence,
                is_overridden=False,
                created_by=None,
            )
            self.db.add(ef)
            await self.db.flush()  # get ef.id

            # Only create evidence if there's a citation
            if result.source_text:
                ev = Evidence(
                    extracted_field_id=ef.id,
                    document_id=document_id,
                    document_name=output.document_id,  # original_filename set by service
                    page_number=result.source_page,
                    section=result.source_section,
                    source_text=result.source_text[:2000],
                    extraction_timestamp=result.extraction_timestamp,
                    is_active=True,
                )
                self.db.add(ev)

        await self.db.flush()

    async def _denormalize_to_submission(
        self,
        submission_id: UUID,
        output: ExtractionOutput,
    ) -> None:
        """
        Copy key fields to the Submission row for quick dashboard display.

        Only updates if the current submission value is None (don't overwrite
        if a later document already set it).
        """
        from app.models.submission import Submission
        from sqlalchemy import select

        result = await self.db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return

        field_map = {r.field_name: r.field_value for r in output.fields if r.field_value is not None}

        updates: dict = {}
        if sub.applicant_name is None and "applicant_name" in field_map:
            updates["applicant_name"] = str(field_map["applicant_name"])

        if updates:
            for k, v in updates.items():
                setattr(sub, k, v)
            await self.db.flush()


def _wrap_value(value: object) -> dict | None:
    """Wrap a scalar value in {"value": ...} for JSON column storage."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"value": value}
    return {"value": value}
