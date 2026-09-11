"""
Classification layer — document type identification.

Public API:
  classify_document(text, extension, filename, use_llm) → ClassificationResult
"""
from app.classification.classifier import ClassificationResult, classify_document
from app.classification.rules_classifier import RulesClassificationResult, classify_with_rules

__all__ = [
    "ClassificationResult",
    "classify_document",
    "RulesClassificationResult",
    "classify_with_rules",
]
