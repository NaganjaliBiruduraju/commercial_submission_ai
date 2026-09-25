"""
ExtractionService — DB-aware prompt-driven extraction orchestration.

Calls extract_with_prompt() or extract_with_default_prompt() from the
extraction engine. The output is whatever the LLM returned for the given
prompt — no fixed schema is enforced by this service.

The raw response is persisted as a single ExtractedField record with
field_name="llm_extraction_output" so it can be retrieved later.
If the response was valid JSON, each top-level key is also stored as
an individual ExtractedField for querying.

Re-extraction is idempotent — previous extraction records for the document
are replaced on each run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentProcessingStatus, DocumentType
from app.core.exceptions import LLMError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.extraction.extractor import ExtractionOutput, extract_with_default_prompt, extract_with_prompt
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
        custom_prompt: str | None = None,
    ) -> ExtractionOutput | None:
        """
        Extract information from a single document.

        If custom_prompt is provided, uses that prompt directly.
        Otherwise builds the default prompt for the document's classified type.

        Returns None if skipped (no text, no classification, failed status).
        Returns ExtractionOutput on success — raw_response contains the LLM output.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        if doc.processing_status == DocumentProcessingStatus.FAILED.value:
            logger.warning("Skipping extraction for failed document",
                           document_id=str(document_id))
            return None

        if not doc.document_type and not custom_prompt:
            logger.warning("Document not classified and no custom prompt — skipping",
                           document_id=str(document_id))
            return None

        doc_type = DocumentType(doc.document_type) if doc.document_type else DocumentType.OTHER

        async with StageLogger(stage=ProcessingStage.EXTRACTION, document_id=str(document_id)):
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.EXTRACTING.value,
            })

            # Load ParsedDocument
            parsed = await self._parse_svc.load_parsed_output(
                submission_id=doc.submission_id,
                document_id=document_id,
            )
            if parsed is None:
                logger.info("No parse cache — running parser first",
                            document_id=str(document_id))
                parsed = await self._parse_svc.process_document(document_id)
                doc = await self.doc_repo.get_by_id_or_raise(document_id)

            if not parsed.full_text or not parsed.full_text.strip():
                logger.warning("No text to extract from", document_id=str(document_id))
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.COMPLETED.value,
                })
                return None

            # Delete previous extraction records
            await self._clear_previous(document_id)

            # Run extraction
            try:
                if custom_prompt:
                    output = await extract_with_prompt(
                        parsed_doc=parsed,
                        prompt=custom_prompt,
                        document_type=doc_type,
                    )
                else:
                    output = await extract_with_default_prompt(
                        parsed_doc=parsed,
                        document_type=doc_type,
                        rag_context=rag_context,
                    )
            except LLMError as exc:
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.FAILED.value,
                    "failure_reason": f"Extraction error: {exc}"[:2000],
                })
                raise

            # Persist the output
            await self._persist(output, document_id, doc.submission_id, doc.original_filename)

            # Denormalize applicant_name to Submission if extractable
            if output.parsed_data and isinstance(output.parsed_data, dict):
                await self._denormalize(doc.submission_id, output.parsed_data)

            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.COMPLETED.value,
                "failure_reason": None,
            })

            logger.info(
                "Extraction persisted",
                document_id=str(document_id),
                response_chars=len(output.raw_response),
                is_json=output.parsed_data is not None,
            )
            return output

    async def extract_all_for_submission(
        self,
        submission_id: UUID,
        rag_context: str = "",
        custom_prompt: str | None = None,
    ) -> list[ExtractionOutput]:
        """
        Extract from all classified documents in a submission.
        Skips image-only documents and failed documents.
        """
        docs = await self.doc_repo.get_by_submission(submission_id, current_only=True)
        skip_types = {DocumentType.EVIDENCE_PHOTO.value, DocumentType.IDENTITY_DOCUMENT.value}
        extractable = [
            d for d in docs
            if d.processing_status != DocumentProcessingStatus.FAILED.value
            and (d.document_type not in skip_types or custom_prompt)
        ]

        results: list[ExtractionOutput] = []
        for doc in extractable:
            try:
                out = await self.extract_document(
                    doc.id,
                    rag_context=rag_context,
                    custom_prompt=custom_prompt,
                )
                if out:
                    results.append(out)
            except Exception as exc:
                logger.error("Extraction failed for document",
                             document_id=str(doc.id),
                             error=str(exc))
        return results

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    async def _clear_previous(self, document_id: UUID) -> None:
        """Remove previous extraction records for this document."""
        # Soft-delete evidence
        from sqlalchemy import update as sa_update
        await self.db.execute(
            sa_update(Evidence)
            .where(Evidence.document_id == document_id)
            .values(is_active=False)
        )
        # Hard-delete extracted fields
        existing = await self.db.execute(
            select(ExtractedField).where(ExtractedField.document_id == document_id)
        )
        for ef in existing.scalars().all():
            await self.db.delete(ef)
        await self.db.flush()

    async def _persist(
        self,
        output: ExtractionOutput,
        document_id: UUID,
        submission_id: UUID,
        original_filename: str,
    ) -> None:
        """
        Persist extraction output to DB.

        Always saves the full raw response as a single field.
        If the response was JSON, also saves each top-level key individually.
        """
        now = datetime.now(tz=timezone.utc)

        # 1. Raw response field — always saved
        raw_ef = ExtractedField(
            submission_id=submission_id,
            document_id=document_id,
            field_name="llm_extraction_output",
            field_label="LLM Extraction Output",
            field_value={"raw": output.raw_response},
            confidence=1.0,
            is_overridden=False,
        )
        self.db.add(raw_ef)
        await self.db.flush()

        # Evidence record pointing to the whole document
        ev = Evidence(
            extracted_field_id=raw_ef.id,
            document_id=document_id,
            document_name=original_filename,
            page_number=None,
            section=None,
            source_text=output.prompt_used[:500],
            extraction_timestamp=now,
            is_active=True,
        )
        self.db.add(ev)

        # 2. If JSON, save each top-level key as its own field
        if isinstance(output.parsed_data, dict):
            for key, value in output.parsed_data.items():
                if key == "llm_extraction_output":
                    continue
                ef = ExtractedField(
                    submission_id=submission_id,
                    document_id=document_id,
                    field_name=str(key),
                    field_label=str(key).replace("_", " ").title(),
                    field_value={"value": value} if not isinstance(value, dict) else value,
                    confidence=0.9,
                    is_overridden=False,
                )
                self.db.add(ef)

        await self.db.flush()

    async def _denormalize(self, submission_id: UUID, parsed: dict) -> None:
        """Copy applicant_name to Submission row if not already set."""
        from app.models.submission import Submission
        result = await self.db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        sub = result.scalar_one_or_none()
        if sub and sub.applicant_name is None:
            for key in ("applicant_name", "named_insured", "insured_name"):
                val = parsed.get(key)
                if val:
                    sub.applicant_name = str(val)[:255]
                    await self.db.flush()
                    break
