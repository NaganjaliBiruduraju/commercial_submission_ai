"""
DocumentProcessingService — orchestrates the parsing pipeline for one document.

This service is the bridge between the stored file on disk and the
parsing layer. It:

  1. Reads the stored file from disk (async).
  2. Routes the bytes to the correct parser via parser_router.parse_document().
  3. Updates the Document DB record with:
     - page_count
     - is_scanned (needs_ocr flag from parser)
     - processing_status (COMPLETED or FAILED)
     - failure_reason (on failure)
  4. Persists the ParsedDocument output as a JSON file in data/processed/
     so downstream phases (classification, extraction) can load it without
     re-parsing.
  5. Returns the ParsedDocument for immediate use if the caller needs it.

Processing status transitions:
  PENDING → PARSING → COMPLETED  (success)
  PENDING → PARSING → FAILED     (unrecoverable error)
  PENDING → PARSING → OCR_PROCESSING  (needs_ocr=True, handed to Phase 5)

Design:
  - Does NOT commit the DB session — the caller is responsible.
    This lets the API layer batch the commit with other updates.
  - Parsing runs in a thread pool (via parser_router) — this method is
    async and safe to call from FastAPI route handlers.
  - Failure is caught and recorded; the exception is re-raised so the
    caller can update the submission status too.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import DocumentProcessingStatus
from app.core.exceptions import DocumentParsingError
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.ingestion.models import ParsedDocument
from app.ingestion.parser_router import parse_document
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository

logger = get_logger(__name__)

_PROCESSED_DIR_NAME = "processed"


class DocumentProcessingService:
    """
    Orchestrates parsing for a single Document record.

    Usage (from an API route or background task):

        async with DatabaseSession() as db:
            svc = DocumentProcessingService(db)
            parsed = await svc.process_document(document_id)
            await db.commit()
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = DocumentRepository(db)

    async def process_document(self, document_id: UUID) -> ParsedDocument:
        """
        Parse a document and update its DB record.

        Returns the ParsedDocument on success.
        Raises DocumentParsingError on unrecoverable failure (after updating
        the document's status to FAILED).
        """
        settings = get_settings()

        # 1. Load Document record
        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        async with StageLogger(
            stage=ProcessingStage.PARSING,
            document_id=str(document_id),
        ):
            # 2. Mark as PARSING
            await self.doc_repo.update(doc, {
                "processing_status": DocumentProcessingStatus.PARSING.value,
            })

            # 3. Read file bytes from disk
            file_bytes = await _read_file_bytes(
                upload_dir=settings.upload_dir,
                submission_id=str(doc.submission_id),
                stored_filename=doc.stored_filename,
            )

            # 4. Parse
            try:
                parsed = await parse_document(
                    file_bytes=file_bytes,
                    document_id=str(document_id),
                    original_filename=doc.original_filename,
                    mime_type=doc.mime_type,
                )
            except Exception as exc:
                failure_msg = f"{type(exc).__name__}: {exc}"
                await self.doc_repo.update(doc, {
                    "processing_status": DocumentProcessingStatus.FAILED.value,
                    "failure_reason": failure_msg[:2000],  # DB column length guard
                })
                logger.error(
                    "Document parsing failed",
                    document_id=str(document_id),
                    filename=doc.original_filename,
                    error=failure_msg,
                )
                raise DocumentParsingError(
                    failure_msg, document_id=str(document_id)
                ) from exc

            # 5. Persist ParsedDocument to data/processed/
            await _save_parsed_output(
                parsed=parsed,
                upload_dir=settings.upload_dir,
                submission_id=str(doc.submission_id),
                document_id=str(document_id),
            )

            # 6. Update Document record with parse results
            next_status = (
                DocumentProcessingStatus.OCR_PROCESSING
                if parsed.needs_ocr
                else DocumentProcessingStatus.COMPLETED
            )

            await self.doc_repo.update(doc, {
                "page_count": parsed.page_count,
                "is_scanned": parsed.needs_ocr,
                "processing_status": next_status.value,
                "failure_reason": None,
            })

            if parsed.parse_warnings:
                logger.warning(
                    "Document parsed with warnings",
                    document_id=str(document_id),
                    warning_count=len(parsed.parse_warnings),
                    warnings=parsed.parse_warnings[:5],  # log first 5 only
                )

            logger.info(
                "Document parsing complete",
                document_id=str(document_id),
                page_count=parsed.page_count,
                char_count=parsed.total_chars(),
                table_count=len(parsed.all_tables),
                needs_ocr=parsed.needs_ocr,
                status=next_status.value,
            )

            return parsed

    async def process_all_pending(self, submission_id: UUID) -> list[ParsedDocument]:
        """
        Process all PENDING documents in a submission.

        Continues processing even if individual documents fail —
        logs errors and marks failed documents, then proceeds.

        Returns list of successfully parsed documents.
        """
        docs = await self.doc_repo.get_by_submission(
            submission_id, current_only=True
        )
        pending = [
            d for d in docs
            if d.processing_status == DocumentProcessingStatus.PENDING.value
        ]

        if not pending:
            logger.info(
                "No pending documents to process",
                submission_id=str(submission_id),
            )
            return []

        logger.info(
            "Processing pending documents",
            submission_id=str(submission_id),
            count=len(pending),
        )

        results: list[ParsedDocument] = []
        for doc in pending:
            try:
                parsed = await self.process_document(doc.id)
                results.append(parsed)
            except (DocumentParsingError, Exception) as exc:
                logger.error(
                    "Skipping failed document",
                    document_id=str(doc.id),
                    filename=doc.original_filename,
                    error=str(exc),
                )
                # Continue with remaining documents

        return results

    async def load_parsed_output(
        self,
        submission_id: UUID,
        document_id: UUID,
    ) -> ParsedDocument | None:
        """
        Load a previously saved ParsedDocument from the processed cache.

        Returns None if the file doesn't exist (document not yet parsed
        or cache was cleared).
        """
        settings = get_settings()
        cache_path = _parsed_output_path(
            upload_dir=settings.upload_dir,
            submission_id=str(submission_id),
            document_id=str(document_id),
        )
        if not cache_path.exists():
            return None

        try:
            import aiofiles
            async with aiofiles.open(cache_path, "r", encoding="utf-8") as f:
                raw = await f.read()
            data = json.loads(raw)
            return _dict_to_parsed_document(data)
        except Exception as exc:
            logger.warning(
                "Could not load parsed output cache",
                document_id=str(document_id),
                error=str(exc),
            )
            return None


# --------------------------------------------------------------------------- #
# File I/O helpers
# --------------------------------------------------------------------------- #

async def _read_file_bytes(
    upload_dir: str,
    submission_id: str,
    stored_filename: str,
) -> bytes:
    """Read uploaded file bytes from disk asynchronously."""
    import aiofiles
    file_path = Path(upload_dir) / submission_id / stored_filename
    if not file_path.exists():
        raise DocumentParsingError(
            f"Stored file not found on disk: {file_path}. "
            "The file may have been deleted or the upload directory moved.",
        )
    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


def _parsed_output_path(
    upload_dir: str,
    submission_id: str,
    document_id: str,
) -> Path:
    """Return the path for the cached ParsedDocument JSON."""
    output_dir = Path(upload_dir).parent / _PROCESSED_DIR_NAME / submission_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{document_id}.parsed.json"


async def _save_parsed_output(
    parsed: ParsedDocument,
    upload_dir: str,
    submission_id: str,
    document_id: str,
) -> None:
    """Serialize ParsedDocument to JSON and save to data/processed/."""
    import aiofiles
    from dataclasses import asdict

    cache_path = _parsed_output_path(upload_dir, submission_id, document_id)
    try:
        data = asdict(parsed)
        async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, default=str))
        logger.debug("Parsed output cached", path=str(cache_path))
    except Exception as exc:
        # Non-fatal — downstream phases will re-parse if cache is missing
        logger.warning(
            "Could not save parsed output cache",
            document_id=document_id,
            error=str(exc),
        )


def _dict_to_parsed_document(data: dict) -> ParsedDocument:
    """Reconstruct a ParsedDocument from its serialized dict form."""
    from app.ingestion.models import ParsedPage, ParsedTable, ParserBackend

    pages = []
    for p in data.get("pages", []):
        tables = [
            ParsedTable(
                page_number=t["page_number"],
                table_index=t["table_index"],
                headers=t.get("headers", []),
                rows=t.get("rows", []),
                raw_rows=t.get("raw_rows", []),
            )
            for t in p.get("tables", [])
        ]
        pages.append(
            ParsedPage(
                page_number=p["page_number"],
                text=p.get("text", ""),
                char_count=p.get("char_count", 0),
                tables=tables,
                metadata=p.get("metadata", {}),
            )
        )

    backend_str = data.get("parser_backend", "unknown")
    try:
        backend = ParserBackend(backend_str)
    except ValueError:
        backend = ParserBackend.UNKNOWN

    all_tables = [t for page in pages for t in page.tables]

    return ParsedDocument(
        document_id=data.get("document_id", ""),
        original_filename=data.get("original_filename", ""),
        mime_type=data.get("mime_type", ""),
        page_count=data.get("page_count", len(pages)),
        pages=pages,
        full_text=data.get("full_text", ""),
        all_tables=all_tables,
        needs_ocr=data.get("needs_ocr", False),
        is_encrypted=data.get("is_encrypted", False),
        parser_backend=backend,
        parser_version=data.get("parser_version", ""),
        parse_warnings=data.get("parse_warnings", []),
        metadata=data.get("metadata", {}),
    )
