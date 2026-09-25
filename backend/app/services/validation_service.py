"""
ValidationService — DB-aware validation orchestration.

Pipeline:
  1. Load all current-version Document records for the submission.
  2. Load all ExtractedField records grouped by document.
  3. Convert to FieldInput objects for the pure validator.
  4. Run run_validation() — deterministic Python, no LLM.
  5. Delete previous unresolved ValidationIssue records for this submission
     (re-validation replaces them; resolved issues are preserved).
  6. Persist new ValidationIssue records.
  7. Update Submission status to READY_FOR_REVIEW if no ERROR-level issues,
     else keep at VALIDATING_DATA.
  8. Caller commits the session.

Re-validation is fully safe and idempotent:
  - Resolved issues (is_resolved=True) are NEVER deleted — they stay
    for audit purposes.
  - Unresolved issues are replaced on each run.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DocumentProcessingStatus,
    DocumentType,
    SubmissionStatus,
    ValidationIssueType,
    ValidationSeverity,
)
from app.core.logging import StageLogger, get_logger
from app.core.constants import ProcessingStage
from app.models.extraction import ExtractedField
from app.models.validation import ValidationIssue
from app.repositories.document_repository import DocumentRepository
from app.validation.validator import FieldInput, ValidationReport, run_validation

logger = get_logger(__name__)


class ValidationService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = DocumentRepository(db)

    async def validate_submission(
        self,
        submission_id: UUID,
    ) -> ValidationReport:
        """
        Run full deterministic validation on a submission.

        Returns ValidationReport with all violations found.
        """
        async with StageLogger(
            stage=ProcessingStage.VALIDATION,
            submission_id=str(submission_id),
        ):
            # 1. Load documents
            docs = await self.doc_repo.get_by_submission(
                submission_id, current_only=True
            )

            present_doc_types: set[DocumentType] = set()
            for doc in docs:
                if doc.document_type:
                    try:
                        present_doc_types.add(DocumentType(doc.document_type))
                    except ValueError:
                        pass

            # 2. Load extracted fields
            result = await self.db.execute(
                select(ExtractedField)
                .where(ExtractedField.submission_id == submission_id)
            )
            extracted_fields = result.scalars().all()

            # Build doc_type lookup
            doc_type_map: dict[str, DocumentType] = {}
            for doc in docs:
                if doc.document_type:
                    try:
                        doc_type_map[str(doc.id)] = DocumentType(doc.document_type)
                    except ValueError:
                        pass

            # Convert to FieldInput
            field_inputs: list[FieldInput] = []
            for ef in extracted_fields:
                doc_type = doc_type_map.get(str(ef.document_id))
                if doc_type is None:
                    continue
                field_inputs.append(FieldInput(
                    document_id=str(ef.document_id),
                    document_type=doc_type,
                    field_name=ef.field_name,
                    value=ef.field_value,
                    confidence=ef.confidence or 0.0,
                ))

            # 3. Run validation
            report = run_validation(
                fields=field_inputs,
                present_doc_types=present_doc_types,
            )

            # 4. Delete previous unresolved issues
            await self.db.execute(
                delete(ValidationIssue)
                .where(ValidationIssue.submission_id == submission_id)
                .where(ValidationIssue.is_resolved == False)  # noqa: E712
            )
            await self.db.flush()

            # 5. Persist new issues
            for violation in report.violations:
                issue = ValidationIssue(
                    submission_id=submission_id,
                    issue_type=violation.issue_type.value,
                    severity=violation.severity.value,
                    field_name=violation.field_name,
                    title=violation.title[:255],
                    description=violation.description[:4000],
                    affected_documents=violation.affected_document_ids or None,
                    conflicting_values=violation.conflicting_values or None,
                    suggested_action=violation.suggested_action[:2000]
                    if violation.suggested_action else None,
                    is_resolved=False,
                )
                self.db.add(issue)

            await self.db.flush()

            # 6. Update submission status
            await self._update_submission_status(submission_id, report)

            logger.info(
                "Validation issues persisted",
                submission_id=str(submission_id),
                total=report.total_issues,
                errors=report.error_count,
                conflicts=report.conflict_count,
                missing=report.missing_count,
            )

            return report

    async def _update_submission_status(
        self, submission_id: UUID, report: ValidationReport
    ) -> None:
        """
        Advance the submission status based on validation results.

        No ERRORs → READY_FOR_REVIEW
        Has ERRORs → VALIDATING_DATA (stay for broker follow-up)
        """
        from app.models.submission import Submission

        result = await self.db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            return

        if report.error_count == 0:
            sub.status = SubmissionStatus.READY_FOR_REVIEW.value
        else:
            sub.status = SubmissionStatus.VALIDATING_DATA.value

        await self.db.flush()

    async def get_validation_summary(
        self, submission_id: UUID
    ) -> dict:
        """Return a summary of current validation issues for a submission."""
        result = await self.db.execute(
            select(ValidationIssue)
            .where(ValidationIssue.submission_id == submission_id)
            .order_by(
                ValidationIssue.severity,
                ValidationIssue.issue_type,
                ValidationIssue.created_at.desc(),
            )
        )
        issues = result.scalars().all()

        total = len(issues)
        unresolved = [i for i in issues if not i.is_resolved]
        resolved = [i for i in issues if i.is_resolved]

        return {
            "total_issues": total,
            "unresolved": len(unresolved),
            "resolved": len(resolved),
            "errors": sum(1 for i in unresolved if i.severity == ValidationSeverity.ERROR.value),
            "warnings": sum(1 for i in unresolved if i.severity == ValidationSeverity.WARNING.value),
            "conflicts": sum(1 for i in unresolved if i.issue_type == ValidationIssueType.CONFLICT.value),
            "missing": sum(1 for i in unresolved if i.issue_type == ValidationIssueType.MISSING.value),
            "invalid": sum(1 for i in unresolved if i.issue_type == ValidationIssueType.INVALID.value),
            "issues": [
                {
                    "id": str(i.id),
                    "type": i.issue_type,
                    "severity": i.severity,
                    "field": i.field_name,
                    "title": i.title,
                    "description": i.description,
                    "suggested_action": i.suggested_action,
                    "is_resolved": i.is_resolved,
                    "resolution_note": i.resolution_note,
                    "affected_documents": i.affected_documents,
                    "conflicting_values": i.conflicting_values,
                }
                for i in issues
            ],
        }
