# -*- coding: utf-8 -*-

FHIR_BASE_URL = "https://fhir.senaite.org"
FHIR_STORAGE_KEY = "senaite.fhir.storage"

# Key of the content dict that IFHIRToContent converters use to hand over the
# secondary FHIR resources of the object being created or updated
SECONDARY_RESOURCES_KEY = "_fhir_secondary_resources"

# Mapping of FHIR resource type -> SENAITE portal type for objects that carry
# a separate FHIR resource ID (e.g. Patient, Specimen, etc.)
FHIR_RESOURCE_TO_PORTAL_TYPE = (
    ("Patient", "Patient"),
    ("Organization", "Client"),
    ("Practitioner", "Contact"),
    ("Observation", "Analysis"),
    ("DiagnosticReport", "ResultsReport"),
    ("Specimen", "SampleType"),
    ("ServiceRequest", "AnalysisRequest"),
    ("Device", "Instrument"),
)

SYSTEM_CODES = (
    ("AnalysisProfile", "http://loinc.org"),
    ("AnalysisService", "http://loinc.org"),
    ("Specimen", "http://snomed.info/sct"),
    ("SamplePoint", "http://snomed.info/sct"),
)

# Default NamingSystem ids (see converter.to_naming_system_url) for the
# internal identifier ("usual") of each FHIR resource type. Internal ids are
# always assigned by SENAITE after creation and may never be supplied by the
# API consumer -- see converter.reject_internal_identifier.
# https://fhir.senaite.org/identifiers.html
INTERNAL_ID_SYSTEMS = (
    ("Patient", "patient-id"),
    ("Practitioner", "practitioner-id"),
    ("Organization", "organization-id"),
    ("Specimen", "sample-id"),
)

# Default NamingSystem ids for the external identifier ("secondary") of each
# FHIR resource type, i.e. the id assigned by the API consumer's own system.
# See converter.validate_external_identifier.
EXTERNAL_ID_SYSTEMS = (
    ("Patient", "patient-mrn"),
    ("Practitioner", "practitioner-external-id"),
    ("Organization", "organization-external-id"),
    ("Specimen", "client-sample-id"),
)

UCUM_SYSTEM = "http://unitsofmeasure.org"

SERVICE_REQUEST_STATUSES = (
    # mapping between Sample status and ServiceRequest's FHIR statuses
    # FHIR ValueSet: draft | active | on-hold | revoked | completed |
    #                entered-in-error | unknown
    # https://hl7.org/fhir/R5/valueset-request-status.html
    ("sample_received", "active"),
    ("to_be_verified", "active"),
    ("published", "completed"),
    ("invalid", "entered-in-error"),
    ("rejected", "revoked"),
    ("cancelled", "revoked"),
    ("retracted", "entered-in-error"),
    ("dispatched", "completed"),
    # Default status if no match
    (None, "active")
)

INSTRUMENT_SERVICE_REQUEST_STATUSES = (
    # mapping between Analysis status and its instrument-scoped
    # ServiceRequest's (SenaiteInstrumentServiceRequest, intent=filler-order)
    # FHIR statuses
    # FHIR ValueSet: draft | active | on-hold | revoked | completed |
    #                entered-in-error | unknown
    # https://hl7.org/fhir/R5/codesystem-request-status.html
    ("registered", "active"),
    ("unassigned", "active"),
    ("assigned", "active"),
    ("to_be_verified", "active"),
    ("verified", "completed"),
    ("published", "completed"),
    ("retracted", "entered-in-error"),
    ("rejected", "revoked"),
    ("cancelled", "revoked"),
    # Default status if no match
    (None, "active"),
)

DIAGNOSTIC_REPORT_STATUSES = (
    # mapping between Sample status and DiagnosticReport's FHIR statuses
    # IMPORTANT: Note that SENAITE relies on Sample's status instead of the
    #            status of the ResultsReport!
    # FHIR ValueSet: registered | partial | preliminary | modified | final |
    #                amended | corrected | appended | cancelled |
    #                entered-in-error | unknown
    # https://hl7.org/fhir/R5/valueset-diagnostic-report-status.html
    ("sample_registered", None),
    ("scheduled_sampling", None),
    ("to_be_sampled", None),
    ("sample_due", None),
    ("sample_received", "preliminary"),
    ("to_be_verified", "preliminary"),
    ("to_be_preserved", None),
    ("verified", "preliminary"),
    ("published", "final"),
    ("rejected", "cancelled"),
    ("invalid", "entered-in-error"),
    ("cancelled", "cancelled"),
    ("dispatched", None),
    # Default status if no match
    (None, "registered"),
)

OBSERVATION_STATUSES = (
    # mapping between Analysis status and Observation's FHIR statuses
    # FHIR ValueSet: registered | preliminary | final | amended | corrected |
    #                cancelled | entered-in-error | unknown
    # https://hl7.org/fhir/R5/valueset-observation-status.html
    ("registered", "registered"),
    ("unassigned", "registered"),
    ("assigned", "registered"),
    ("cancelled", "cancelled"),
    ("to_be_verified", "preliminary"),
    ("retracted", "entered-in-error"),
    ("rejected", "cancelled"),
    ("verified", "preliminary"),
    ("published", "final"),
    # Default status if no match
    (None, "registered")
)

ANALYSIS_REPORTABLE_STATUSES = (
    # Analyses that are in this status will be reported as Observations
    "to_be_verified",
    "verified",
    "published",
)

DEFAULT_REPORT_PROFILE_CODE = {
    # TODO Make the default DiagnosticReport code configurable in setup
    # Default DiagnosticReport code for when the number of profiles/panels
    # assigned to a sample are different from 1
    "text": "Relevant diagnostic tests/laboratory data note",
    "coding": [{
        "code": "30954-2",
        "system": "http://loinc.org",
        "display": "Relevant diagnostic tests/laboratory data note"
      }]
}


DEFAULT_INSTRUMENT_SERVICE_REQUEST_CATEGORY = {
    "coding": [{
        "system": "http://snomed.info/sct",
        "code": "108252007",
        "display": "Laboratory procedure",
    }],
    "text": "Laboratory procedure",
}

DEFAULT_BUNDLE_PAGE_COUNT = 10

# Maps the resource type each search endpoint matches on to the `_include`
# specs it supports, along with the reference field each spec resolves. They
# are declared per resource type because a reference field only makes sense
# for the resource the endpoint matches on
INCLUDE_REFERENCE_FIELDS = (
    ("ServiceRequest", {
        "Patient:subject": "subject",
        "Specimen:specimen": "specimen",
    }),
    ("DiagnosticReport", {
        "Observation:result": "result",
    }),
)
