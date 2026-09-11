"""
Deterministic rules-based document classifier.

Strategy:
  Each DocumentType has a RuleSet containing:
    - required_patterns: ALL must match (AND logic) for a positive signal
    - bonus_patterns:    Each match adds bonus_weight to the score
    - negative_patterns: Any match reduces the score (anti-patterns)
    - file_extension_hints: Certain extensions give a small prior boost

Scoring:
  A score in [0.0, 1.0] is produced for each DocumentType.
  The type with the highest score wins.
  If the winner's score < MIN_CONFIDENCE the result is DocumentType.OTHER.
  If the top two scores are within AMBIGUITY_GAP, the result is flagged
  as ambiguous so the LLM classifier is invoked.

Text sampling:
  We do NOT send the entire document to the rules engine.
  We check:
    - first 3000 chars (title page, headers)
    - last 1000 chars (footers, signatures)
    - A sample of 2000 chars from the middle
  This keeps classification fast regardless of document length.

All patterns are case-insensitive and compiled once at module load.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.constants import DocumentType
from app.core.logging import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Thresholds
# --------------------------------------------------------------------------- #
MIN_CONFIDENCE: float = 0.30   # below this → OTHER
AMBIGUITY_GAP: float = 0.12    # top-2 within this → send to LLM


# --------------------------------------------------------------------------- #
# Rule definitions
# --------------------------------------------------------------------------- #

@dataclass
class RuleSet:
    """Rules for a single DocumentType."""
    doc_type: DocumentType
    required_patterns: list[str] = field(default_factory=list)   # ALL must match
    bonus_patterns: list[str] = field(default_factory=list)       # each adds bonus_weight
    negative_patterns: list[str] = field(default_factory=list)    # each subtracts penalty
    bonus_weight: float = 0.15
    penalty_weight: float = 0.20
    extension_hints: set[str] = field(default_factory=set)        # file extensions


# ACORD form numbers are the strongest signal — they appear in headers
_RULES: list[RuleSet] = [

    RuleSet(
        doc_type=DocumentType.ACORD_APPLICATION,
        required_patterns=[
            r"acord\s*125",
        ],
        bonus_patterns=[
            r"commercial\s+lines",
            r"applicant\s+information",
            r"nature\s+of\s+business",
            r"years?\s+in\s+business",
            r"prior\s+carrier",
            r"acord\s+125",
        ],
        negative_patterns=[r"acord\s*12[6-9]", r"acord\s*13\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.ACORD_GL,
        required_patterns=[
            r"acord\s*126",
        ],
        bonus_patterns=[
            r"general\s+liability",
            r"occurrence\s+limit",
            r"premises\s+and\s+operations",
            r"products.completed\s+operations",
            r"personal\s+and\s+advertising\s+injury",
            r"gl\s+coverage",
            r"each\s+occurrence",
        ],
        negative_patterns=[r"acord\s*12[57]", r"acord\s*14\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.ACORD_PROPERTY,
        required_patterns=[
            r"acord\s*140",
        ],
        bonus_patterns=[
            r"property\s+section",
            r"building\s+value",
            r"business\s+personal\s+property",
            r"replacement\s+cost",
            r"coinsurance",
            r"blanket\s+(limit|coverage)",
            r"scheduled\s+locations",
        ],
        negative_patterns=[r"acord\s*12[567]", r"acord\s*13\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.ACORD_AUTO,
        required_patterns=[
            r"acord\s*127",
        ],
        bonus_patterns=[
            r"business\s+auto",
            r"vehicle\s+schedule",
            r"vin\b",
            r"hired\s+(and\s+)?non.owned",
            r"radius\s+of\s+operation",
            r"fleet",
            r"auto\s+liability",
        ],
        negative_patterns=[r"acord\s*12[568]", r"personal\s+auto\s+policy"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.ACORD_WORKERS_COMP,
        required_patterns=[
            r"acord\s*130",
        ],
        bonus_patterns=[
            r"workers.?\s*comp",
            r"employer.s\s+liability",
            r"payroll",
            r"class\s+code",
            r"experience\s+mod",
            r"ncci",
            r"estimated\s+annual\s+remuneration",
        ],
        negative_patterns=[r"acord\s*12[5-9]", r"acord\s*14\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.ACORD_UMBRELLA,
        required_patterns=[
            r"acord\s*131",
        ],
        bonus_patterns=[
            r"umbrella",
            r"excess\s+(liability|coverage)",
            r"underlying\s+(insurance|policy|coverage)",
            r"self.insured\s+retention",
            r"sir\b",
            r"drop.down\s+coverage",
        ],
        negative_patterns=[r"acord\s*12[5-9]", r"acord\s*14\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.LOSS_RUN,
        required_patterns=[
            r"(loss\s+run|loss\s+history|claims?\s+history)",
        ],
        bonus_patterns=[
            r"date\s+of\s+(loss|claim)",
            r"(paid|incurred|reserve)\s+loss",
            r"(open|closed|pending)\s+claim",
            r"claim\s+number",
            r"claimant",
            r"adjuster",
            r"total\s+(incurred|paid)",
            r"policy\s+year",
            r"loss\s+ratio",
        ],
        negative_patterns=[r"acord\s*1[23]\d"],
        extension_hints={"pdf", "docx", "xlsx", "xls", "csv"},
    ),

    RuleSet(
        doc_type=DocumentType.FINANCIAL_STATEMENT,
        required_patterns=[
            r"(balance\s+sheet|income\s+statement|profit\s+(and|&)\s+loss|financial\s+statement)",
        ],
        bonus_patterns=[
            r"total\s+(assets|liabilities|revenue|equity)",
            r"(net\s+income|gross\s+profit|operating\s+income)",
            r"accounts\s+(payable|receivable)",
            r"(fiscal|financial)\s+year",
            r"audited|unaudited",
            r"(cash|accrual)\s+basis",
            r"retained\s+earnings",
        ],
        negative_patterns=[r"acord\s*1[23]\d", r"loss\s+run"],
        extension_hints={"pdf", "xlsx", "xls", "docx", "csv"},
    ),

    RuleSet(
        doc_type=DocumentType.BROKER_EMAIL,
        required_patterns=[
            r"(from:|to:|subject:|sent:|dear\s+\w)",
        ],
        bonus_patterns=[
            r"(please\s+find|attached|kindly|submission|quote|renewal|bind)",
            r"(broker|agent|producer|account\s+executive)",
            r"@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",   # email address pattern
            r"(regards|sincerely|best)",
        ],
        negative_patterns=[r"acord\s*1[23]\d", r"balance\s+sheet", r"loss\s+run"],
        extension_hints={"docx", "pdf", "txt"},
    ),

    RuleSet(
        doc_type=DocumentType.UNDERWRITING_GUIDELINE,
        required_patterns=[
            r"(underwriting\s+guideline|underwriting\s+manual|eligibility\s+criteria)",
        ],
        bonus_patterns=[
            r"(appetite|prohibited\s+(class|risk)|eligible|ineligible)",
            r"(minimum\s+premium|rate|tier)",
            r"(endorsement|exclusion|condition)",
            r"effective\s+date",
            r"(approved\s+by|revision\s+date)",
        ],
        negative_patterns=[r"acord\s*1[23]\d", r"loss\s+run"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.CLAIMS_DOCUMENT,
        required_patterns=[
            r"(claim\s+form|proof\s+of\s+loss|notice\s+of\s+claim|sworn\s+statement)",
        ],
        bonus_patterns=[
            r"(policy\s+number|claim\s+number|date\s+of\s+loss)",
            r"(description\s+of\s+(loss|damage|incident))",
            r"(signature\s+of\s+(insured|claimant))",
            r"(notary|witnessed\s+by)",
        ],
        negative_patterns=[r"loss\s+run\s+report", r"acord\s*1[23]\d"],
        extension_hints={"pdf", "docx"},
    ),

    RuleSet(
        doc_type=DocumentType.EVIDENCE_PHOTO,
        required_patterns=[],  # detected by MIME type / extension primarily
        bonus_patterns=[
            r"(photo|photograph|image|picture|exhibit)",
            r"(damage|inspection|survey)",
        ],
        negative_patterns=[r"acord", r"financial"],
        extension_hints={"jpg", "jpeg", "png"},
        bonus_weight=0.40,   # higher weight since extension is the main signal
    ),

    RuleSet(
        doc_type=DocumentType.IDENTITY_DOCUMENT,
        required_patterns=[
            r"(driver.s?\s+licen[sc]e|passport|state\s+id|identification\s+card)",
        ],
        bonus_patterns=[
            r"(date\s+of\s+birth|dob|expir(ation|y)\s+date)",
            r"(license\s+number|id\s+number|document\s+number)",
        ],
        negative_patterns=[r"acord", r"financial", r"loss\s+run"],
        extension_hints={"jpg", "jpeg", "png", "pdf"},
    ),
]


# Compile all patterns once at module load for performance
@dataclass
class _CompiledRule:
    doc_type: DocumentType
    required: list[re.Pattern]
    bonus: list[re.Pattern]
    negative: list[re.Pattern]
    bonus_weight: float
    penalty_weight: float
    extension_hints: set[str]


_COMPILED_RULES: list[_CompiledRule] = [
    _CompiledRule(
        doc_type=r.doc_type,
        required=[re.compile(p, re.IGNORECASE) for p in r.required_patterns],
        bonus=[re.compile(p, re.IGNORECASE) for p in r.bonus_patterns],
        negative=[re.compile(p, re.IGNORECASE) for p in r.negative_patterns],
        bonus_weight=r.bonus_weight,
        penalty_weight=r.penalty_weight,
        extension_hints=r.extension_hints,
    )
    for r in _RULES
]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

@dataclass
class RulesClassificationResult:
    document_type: DocumentType
    confidence: float          # 0.0–1.0
    reason: str
    alternative_type: Optional[DocumentType]
    is_ambiguous: bool         # True → send to LLM for confirmation
    scores: dict[str, float]   # all type scores for debugging


def classify_with_rules(
    text: str,
    extension: str = "",
    filename: str = "",
) -> RulesClassificationResult:
    """
    Classify a document using deterministic rules.

    Args:
        text:      Full document text (ParsedDocument.full_text).
        extension: Lowercase file extension (e.g. "pdf").
        filename:  Original filename (used for extension hint only).

    Returns:
        RulesClassificationResult with the best-matching DocumentType.
    """
    sample = _extract_sample(text)
    ext = extension.lower().lstrip(".")
    if not ext and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    scores: dict[str, float] = {}

    for rule in _COMPILED_RULES:
        score = _score_rule(sample, rule, ext)
        scores[rule.doc_type.value] = round(score, 4)

    # Sort descending by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_type_str, top_score = ranked[0]
    second_type_str, second_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    top_type = DocumentType(top_type_str)
    second_type = DocumentType(second_type_str) if second_type_str else None

    # Apply minimum confidence gate
    if top_score < MIN_CONFIDENCE:
        return RulesClassificationResult(
            document_type=DocumentType.OTHER,
            confidence=round(1.0 - top_score, 3),
            reason=f"No strong rule match (best score {top_score:.2f} < threshold {MIN_CONFIDENCE})",
            alternative_type=top_type if top_score > 0.1 else None,
            is_ambiguous=False,
            scores=scores,
        )

    # Ambiguity check
    gap = top_score - second_score
    is_ambiguous = gap < AMBIGUITY_GAP and second_score > 0.15

    # Build reason string
    matched_bonuses = _explain_matches(sample, _find_rule(top_type))
    reason = f"Rule match for {top_type.value}"
    if matched_bonuses:
        reason += f": {'; '.join(matched_bonuses[:4])}"
    if is_ambiguous and second_type:
        reason += f" (ambiguous with {second_type.value}, gap={gap:.2f})"

    return RulesClassificationResult(
        document_type=top_type,
        confidence=round(min(top_score, 1.0), 3),
        reason=reason,
        alternative_type=second_type if is_ambiguous else None,
        is_ambiguous=is_ambiguous,
        scores=scores,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _extract_sample(text: str) -> str:
    """Extract a representative sample from head + middle + tail."""
    if len(text) <= 6000:
        return text
    head = text[:3000]
    mid_start = max(3000, len(text) // 2 - 1000)
    middle = text[mid_start: mid_start + 2000]
    tail = text[-1000:]
    return f"{head}\n{middle}\n{tail}"


def _score_rule(sample: str, rule: _CompiledRule, ext: str) -> float:
    """Compute a score in [0, 1] for a single rule against the text sample."""
    score = 0.0

    # Extension hint gives a small prior
    if ext and ext in rule.extension_hints:
        score += 0.05

    # Required patterns: if any required pattern is missing, score = 0
    if rule.required:
        for pat in rule.required:
            if not pat.search(sample):
                return 0.0
        # All required matched — strong base signal
        score += 0.45

    # Bonus patterns
    matched_bonuses = sum(1 for p in rule.bonus if p.search(sample))
    # Cap bonus contribution so many bonuses don't massively over-score
    max_bonus_contribution = 0.50
    if rule.bonus:
        bonus_ratio = matched_bonuses / len(rule.bonus)
        score += min(bonus_ratio * max_bonus_contribution, max_bonus_contribution)
    elif matched_bonuses > 0:
        score += matched_bonuses * rule.bonus_weight

    # Negative patterns
    matched_negatives = sum(1 for p in rule.negative if p.search(sample))
    score -= matched_negatives * rule.penalty_weight

    return max(0.0, min(score, 1.0))


def _find_rule(doc_type: DocumentType) -> Optional[_CompiledRule]:
    for r in _COMPILED_RULES:
        if r.doc_type == doc_type:
            return r
    return None


def _explain_matches(sample: str, rule: Optional[_CompiledRule]) -> list[str]:
    """Return list of bonus pattern strings that matched (for reason text)."""
    if rule is None:
        return []
    matched = []
    for i, pat in enumerate(rule.bonus):
        if pat.search(sample):
            # Use original pattern string for readability
            matched.append(_RULES[_COMPILED_RULES.index(rule)].bonus_patterns[i]
                           if rule in _COMPILED_RULES else pat.pattern)
    return matched[:6]
