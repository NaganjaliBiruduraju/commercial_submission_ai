"""
Canonical field definitions for every DocumentType.

Each field has:
  name:     snake_case canonical identifier (matches ExtractedField.field_name)
  label:    Human-readable display label
  type:     Expected Python type as a string hint (for prompt generation)
  required: True if absence should raise a MISSING validation issue
  description: Used in the LLM prompt to explain what to look for

Design:
  - Fields are grouped by document type.
  - COMMON_FIELDS appear across all document types.
  - get_fields_for_type() merges common + type-specific fields.
  - The field list drives both the LLM prompt AND the validation phase.

Why a static definition instead of a DB table?
  The field schema changes slowly (tied to ACORD form versions and
  underwriting guidelines). Keeping it in code makes it versioned,
  reviewable, and testable. A DB-based config could be added later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.constants import DocumentType

FieldType = Literal["string", "number", "date", "boolean", "list", "currency"]


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    label: str
    type: FieldType
    required: bool = False
    description: str = ""


# --------------------------------------------------------------------------- #
# Common fields — present across all document types
# --------------------------------------------------------------------------- #

COMMON_FIELDS: list[FieldDefinition] = [
    FieldDefinition(
        name="applicant_name",
        label="Applicant / Named Insured",
        type="string",
        required=True,
        description="Legal name of the business or individual seeking insurance",
    ),
    FieldDefinition(
        name="policy_effective_date",
        label="Policy Effective Date",
        type="date",
        required=False,
        description="Date the requested coverage would begin (MM/DD/YYYY)",
    ),
    FieldDefinition(
        name="policy_expiration_date",
        label="Policy Expiration Date",
        type="date",
        required=False,
        description="Date the requested coverage would end",
    ),
    FieldDefinition(
        name="prior_carrier",
        label="Prior Insurance Carrier",
        type="string",
        required=False,
        description="Name of the current or most recent insurance carrier",
    ),
    FieldDefinition(
        name="prior_policy_number",
        label="Prior Policy Number",
        type="string",
        required=False,
        description="Policy number with the prior carrier",
    ),
]

# --------------------------------------------------------------------------- #
# ACORD 125 — Commercial Lines Application
# --------------------------------------------------------------------------- #

ACORD_APPLICATION_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True,
                    description="Legal business name as it should appear on the policy"),
    FieldDefinition("applicant_address", "Business Address", "string", required=True,
                    description="Primary business address including city, state, zip"),
    FieldDefinition("applicant_state", "State of Domicile", "string", required=True,
                    description="State where the business is incorporated or primarily operates"),
    FieldDefinition("fein", "Federal Employer Identification Number (FEIN)", "string",
                    description="9-digit FEIN / EIN in format XX-XXXXXXX"),
    FieldDefinition("sic_code", "SIC Code", "string",
                    description="Standard Industrial Classification code"),
    FieldDefinition("business_type", "Type of Business Entity", "string", required=True,
                    description="Corporation, LLC, Partnership, Sole Proprietor, etc."),
    FieldDefinition("nature_of_business", "Nature / Description of Business", "string", required=True,
                    description="What the business does — operations description"),
    FieldDefinition("years_in_business", "Years in Business", "number",
                    description="Number of years the business has been operating"),
    FieldDefinition("annual_revenue", "Annual Revenue / Gross Sales", "currency", required=True,
                    description="Total annual revenue or gross sales in dollars"),
    FieldDefinition("employee_count", "Number of Employees", "number",
                    description="Total full-time and part-time employees"),
    FieldDefinition("website", "Business Website URL", "string",
                    description="Company website if listed"),
    FieldDefinition("contact_name", "Primary Contact Name", "string",
                    description="Name of the primary contact person"),
    FieldDefinition("contact_phone", "Contact Phone Number", "string",
                    description="Best phone number for the contact"),
    FieldDefinition("contact_email", "Contact Email Address", "string",
                    description="Email address for the contact"),
    FieldDefinition("policy_effective_date", "Policy Effective Date", "date", required=True,
                    description="Requested policy start date"),
    FieldDefinition("policy_expiration_date", "Policy Expiration Date", "date",
                    description="Requested policy end date (typically 1 year)"),
    FieldDefinition("lines_requested", "Lines of Coverage Requested", "list", required=True,
                    description="List of coverage lines: GL, Property, Auto, WC, Umbrella, etc."),
    FieldDefinition("prior_carrier", "Prior Carrier", "string",
                    description="Prior insurance carrier name"),
    FieldDefinition("prior_premium", "Prior Year Premium", "currency",
                    description="Premium paid to the prior carrier"),
    FieldDefinition("prior_carrier_reason_leaving", "Reason for Leaving Prior Carrier", "string",
                    description="Why they are changing carriers"),
    FieldDefinition("loss_count_3yr", "Number of Losses (3 Years)", "number",
                    description="Total number of claims in the past 3 years"),
    FieldDefinition("total_losses_3yr", "Total Incurred Losses (3 Years)", "currency",
                    description="Total paid + reserved losses in the past 3 years"),
    FieldDefinition("location_count", "Number of Locations", "number",
                    description="Total number of business locations"),
]

# --------------------------------------------------------------------------- #
# ACORD 126 — General Liability
# --------------------------------------------------------------------------- #

ACORD_GL_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True),
    FieldDefinition("each_occurrence_limit", "Each Occurrence Limit", "currency", required=True,
                    description="Per-occurrence liability limit requested"),
    FieldDefinition("general_aggregate_limit", "General Aggregate Limit", "currency", required=True,
                    description="Total aggregate limit for the policy period"),
    FieldDefinition("products_aggregate_limit", "Products/Completed Operations Aggregate", "currency",
                    description="Aggregate for products and completed operations"),
    FieldDefinition("personal_injury_limit", "Personal & Advertising Injury Limit", "currency"),
    FieldDefinition("damage_to_premises_limit", "Damage to Rented Premises Limit", "currency"),
    FieldDefinition("medical_payments_limit", "Medical Payments Limit", "currency"),
    FieldDefinition("deductible", "Deductible Amount", "currency"),
    FieldDefinition("annual_revenue", "Annual Revenue (GL Basis)", "currency", required=True,
                    description="Gross sales / revenue used for GL rating"),
    FieldDefinition("square_footage", "Total Square Footage", "number",
                    description="Total sq ft of all premises occupied"),
    FieldDefinition("subcontractor_cost", "Subcontracted Work Cost", "currency",
                    description="Annual cost paid to subcontractors"),
    FieldDefinition("products_operations_description", "Products / Operations Description", "string",
                    description="Description of products sold or operations performed"),
    FieldDefinition("additional_insureds", "Additional Insureds", "list",
                    description="Names of parties to be listed as additional insureds"),
    FieldDefinition("policy_effective_date", "Effective Date", "date", required=True),
]

# --------------------------------------------------------------------------- #
# ACORD 140 — Property
# --------------------------------------------------------------------------- #

ACORD_PROPERTY_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True),
    FieldDefinition("property_address", "Property Address", "string", required=True,
                    description="Physical address of the insured property"),
    FieldDefinition("building_value", "Building Replacement Cost Value", "currency", required=True,
                    description="Replacement cost of the building structure"),
    FieldDefinition("bpp_value", "Business Personal Property Value", "currency",
                    description="Value of contents / business personal property"),
    FieldDefinition("bi_limit", "Business Income / BI Limit", "currency",
                    description="Business interruption coverage limit"),
    FieldDefinition("construction_type", "Construction Type", "string",
                    description="Frame, Masonry, Fire Resistive, etc."),
    FieldDefinition("year_built", "Year Built", "number"),
    FieldDefinition("square_footage", "Building Square Footage", "number"),
    FieldDefinition("number_of_stories", "Number of Stories", "number"),
    FieldDefinition("occupancy", "Occupancy / Use", "string",
                    description="How the building is used: Office, Retail, Warehouse, etc."),
    FieldDefinition("roof_type", "Roof Type / Material", "string"),
    FieldDefinition("roof_year", "Roof Year / Last Replaced", "number"),
    FieldDefinition("sprinkler_system", "Sprinkler System Present", "boolean"),
    FieldDefinition("alarm_system", "Alarm System Type", "string"),
    FieldDefinition("coinsurance_pct", "Coinsurance Percentage", "number"),
    FieldDefinition("deductible", "Property Deductible", "currency"),
    FieldDefinition("policy_effective_date", "Effective Date", "date", required=True),
]

# --------------------------------------------------------------------------- #
# ACORD 127 — Business Auto
# --------------------------------------------------------------------------- #

ACORD_AUTO_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True),
    FieldDefinition("fleet_size", "Number of Vehicles", "number", required=True),
    FieldDefinition("auto_liability_limit", "Auto Liability Limit (CSL)", "currency",
                    description="Combined single limit for auto liability"),
    FieldDefinition("hired_non_owned", "Hired & Non-Owned Auto Coverage", "boolean"),
    FieldDefinition("radius_of_operation", "Radius of Operation (miles)", "number"),
    FieldDefinition("vehicle_types", "Types of Vehicles", "list",
                    description="e.g. Passenger, Light Truck, Heavy Truck, Trailer"),
    FieldDefinition("driver_count", "Number of Drivers", "number"),
    FieldDefinition("annual_mileage", "Estimated Annual Mileage", "number"),
    FieldDefinition("garaging_state", "Primary Garaging State", "string"),
    FieldDefinition("policy_effective_date", "Effective Date", "date", required=True),
]

# --------------------------------------------------------------------------- #
# ACORD 130 — Workers Compensation
# --------------------------------------------------------------------------- #

ACORD_WORKERS_COMP_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True),
    FieldDefinition("state_of_operations", "State(s) of Operation", "list", required=True),
    FieldDefinition("total_payroll", "Total Annual Payroll", "currency", required=True),
    FieldDefinition("employee_count", "Number of Employees", "number", required=True),
    FieldDefinition("class_codes", "WC Class Codes and Payroll", "list",
                    description="List of NCCI class codes with associated payroll"),
    FieldDefinition("experience_mod", "Experience Modification Factor (EMF)", "number",
                    description="Experience mod factor — 1.00 is average"),
    FieldDefinition("employer_liability_limit", "Employer Liability Limit", "currency"),
    FieldDefinition("officers_included", "Officers Included/Excluded", "boolean",
                    description="Whether corporate officers are included in WC coverage"),
    FieldDefinition("subcontractors_used", "Subcontractors Used", "boolean"),
    FieldDefinition("policy_effective_date", "Effective Date", "date", required=True),
]

# --------------------------------------------------------------------------- #
# ACORD 131 — Umbrella / Excess
# --------------------------------------------------------------------------- #

ACORD_UMBRELLA_FIELDS: list[FieldDefinition] = [
    FieldDefinition("applicant_name", "Named Insured", "string", required=True),
    FieldDefinition("umbrella_limit", "Umbrella / Excess Limit", "currency", required=True),
    FieldDefinition("self_insured_retention", "Self-Insured Retention (SIR)", "currency"),
    FieldDefinition("underlying_gl_limit", "Underlying GL Each Occurrence Limit", "currency"),
    FieldDefinition("underlying_auto_limit", "Underlying Auto Liability Limit", "currency"),
    FieldDefinition("underlying_wc_limit", "Underlying WC Employer Liability Limit", "currency"),
    FieldDefinition("underlying_carrier", "Underlying Coverage Carrier", "string"),
    FieldDefinition("policy_effective_date", "Effective Date", "date", required=True),
]

# --------------------------------------------------------------------------- #
# Loss Run
# --------------------------------------------------------------------------- #

LOSS_RUN_FIELDS: list[FieldDefinition] = [
    FieldDefinition("policy_period", "Policy Period Covered", "string", required=True),
    FieldDefinition("prior_carrier", "Prior Carrier Name", "string", required=True),
    FieldDefinition("total_claims", "Total Number of Claims", "number", required=True),
    FieldDefinition("total_paid", "Total Paid Losses", "currency", required=True),
    FieldDefinition("total_incurred", "Total Incurred Losses", "currency"),
    FieldDefinition("open_claims_count", "Number of Open Claims", "number"),
    FieldDefinition("largest_claim_amount", "Largest Single Claim Amount", "currency"),
    FieldDefinition("loss_ratio", "Loss Ratio", "number",
                    description="Total incurred / premium as a percentage"),
    FieldDefinition("claims_detail", "Individual Claims Detail", "list",
                    description="List of individual claims with date, cause, amount, status"),
]

# --------------------------------------------------------------------------- #
# Financial Statement
# --------------------------------------------------------------------------- #

FINANCIAL_STATEMENT_FIELDS: list[FieldDefinition] = [
    FieldDefinition("fiscal_year", "Fiscal Year", "string", required=True),
    FieldDefinition("total_revenue", "Total Revenue / Net Sales", "currency", required=True),
    FieldDefinition("gross_profit", "Gross Profit", "currency"),
    FieldDefinition("net_income", "Net Income / Net Loss", "currency"),
    FieldDefinition("total_assets", "Total Assets", "currency"),
    FieldDefinition("total_liabilities", "Total Liabilities", "currency"),
    FieldDefinition("total_equity", "Total Equity / Net Worth", "currency"),
    FieldDefinition("cash_and_equivalents", "Cash and Cash Equivalents", "currency"),
    FieldDefinition("accounts_receivable", "Accounts Receivable", "currency"),
    FieldDefinition("long_term_debt", "Long-Term Debt", "currency"),
    FieldDefinition("audited", "Audited Financial Statement", "boolean",
                    description="Whether the statements are audited or unaudited"),
]

# --------------------------------------------------------------------------- #
# Broker Email
# --------------------------------------------------------------------------- #

BROKER_EMAIL_FIELDS: list[FieldDefinition] = [
    FieldDefinition("broker_name", "Broker / Agent Name", "string", required=True),
    FieldDefinition("broker_email", "Broker Email Address", "string"),
    FieldDefinition("broker_company", "Broker Agency / Company", "string"),
    FieldDefinition("applicant_name", "Applicant / Insured Name", "string"),
    FieldDefinition("coverage_type_requested", "Coverage Type Requested", "string"),
    FieldDefinition("renewal_date", "Renewal / Effective Date Requested", "date"),
    FieldDefinition("special_instructions", "Special Instructions or Notes", "string"),
]

# --------------------------------------------------------------------------- #
# Mapping: DocumentType → field list
# --------------------------------------------------------------------------- #

_TYPE_TO_FIELDS: dict[DocumentType, list[FieldDefinition]] = {
    DocumentType.ACORD_APPLICATION: ACORD_APPLICATION_FIELDS,
    DocumentType.ACORD_GL: ACORD_GL_FIELDS,
    DocumentType.ACORD_PROPERTY: ACORD_PROPERTY_FIELDS,
    DocumentType.ACORD_AUTO: ACORD_AUTO_FIELDS,
    DocumentType.ACORD_WORKERS_COMP: ACORD_WORKERS_COMP_FIELDS,
    DocumentType.ACORD_UMBRELLA: ACORD_UMBRELLA_FIELDS,
    DocumentType.LOSS_RUN: LOSS_RUN_FIELDS,
    DocumentType.FINANCIAL_STATEMENT: FINANCIAL_STATEMENT_FIELDS,
    DocumentType.BROKER_EMAIL: BROKER_EMAIL_FIELDS,
    DocumentType.UNDERWRITING_GUIDELINE: COMMON_FIELDS,
    DocumentType.CLAIMS_DOCUMENT: COMMON_FIELDS,
    DocumentType.EVIDENCE_PHOTO: [],
    DocumentType.IDENTITY_DOCUMENT: [],
    DocumentType.OTHER: COMMON_FIELDS,
}


def get_fields_for_type(doc_type: DocumentType) -> list[FieldDefinition]:
    """
    Return the canonical field list for a document type.
    Type-specific fields are returned directly (they include common fields
    where relevant). Falls back to COMMON_FIELDS for unrecognised types.
    """
    return _TYPE_TO_FIELDS.get(doc_type, COMMON_FIELDS)


def get_required_fields(doc_type: DocumentType) -> list[FieldDefinition]:
    """Return only the required fields for a document type."""
    return [f for f in get_fields_for_type(doc_type) if f.required]


def get_field_names(doc_type: DocumentType) -> list[str]:
    """Return a list of canonical field name strings."""
    return [f.name for f in get_fields_for_type(doc_type)]
