# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.catalog import CLIENT_CATALOG
from senaite.core.catalog import CONTACT_CATALOG
from senaite.fhir import api as fapi
from senaite.fhir.config import ORGANIZATION_EXTERNAL_ID_SYSTEM
from senaite.fhir.config import ORGANIZATION_ID_SYSTEM
from senaite.fhir.config import PATIENT_ID_SYSTEM
from senaite.fhir.config import PATIENT_MRN_SYSTEM
from senaite.fhir.config import PRACTITIONER_EXTERNAL_ID_SYSTEM
from senaite.fhir.config import PRACTITIONER_ID_SYSTEM
from senaite.fhir.converter import to_naming_system_url
from senaite.fhir.exceptions import ResourceValidationError
from senaite.patient.catalog import PATIENT_CATALOG

# Resource type -> (catalog id, internal NamingSystem id,
#                    external-identifier NamingSystem id, external index)
MATCH_TABLE = {
    "Patient": (
        PATIENT_CATALOG, PATIENT_ID_SYSTEM, PATIENT_MRN_SYSTEM,
        "patient_mrn"),
    "Practitioner": (
        CONTACT_CATALOG, PRACTITIONER_ID_SYSTEM,
        PRACTITIONER_EXTERNAL_ID_SYSTEM, "fhir_external_id"),
    "Organization": (
        CLIENT_CATALOG, ORGANIZATION_ID_SYSTEM,
        ORGANIZATION_EXTERNAL_ID_SYSTEM, "getClientID"),
}


def get_if_none_exist(resource):
    """Returns the raw `ifNoneExist` string declared on the bundle entry of
    the given resource, or None when absent, the resource type is not one
    SENAITE evaluates ifNoneExist for (Specimen/ServiceRequest carry
    `request.ifNoneExist 0..0` per the IG -- silently ignored here, same as
    every other resource type this module doesn't recognize), or the
    resource isn't part of a bundle at all (e.g. a standalone POST /Patient,
    which has no entry.request to begin with).

    :param resource: the FHIR resource being processed by post()
    :returns: the raw ifNoneExist value, or None
    """
    if resource.resourceType not in MATCH_TABLE:
        return None
    bundle = resource.get("_bundle")
    if not bundle:
        return None
    return bundle.get_request(resource).get("ifNoneExist")


def parse_if_none_exist(raw):
    """Parses an `ifNoneExist` value of the `identifier=<system>|<value>`
    form mandated by the SenaiteRequestBundle profile.

    :param raw: the raw ifNoneExist string
    :returns: (system, value) tuple; either half is "" when `raw` is
        malformed or doesn't use the `identifier` search parameter
    """
    param, eq, query = (raw or "").partition("=")
    if not eq or param != "identifier":
        return "", ""
    if "|" not in query:
        # FHIR token search: no "|" means a bare value with no system
        return "", query
    system, _, value = query.partition("|")
    return system, value


def find_by_if_none_exist(resource, raw):
    """Resolves the ifNoneExist conditional-create precondition for a
    Patient, Practitioner or Organization bundle entry.

    Business rules (per issue #60): zero matches means the caller should
    proceed to create as normal; exactly one match means the entry is
    already satisfied and the submitted body must be discarded; more than
    one match rejects the whole bundle with 412 Precondition Failed. A
    malformed precondition (missing or unrecognized system, or no value)
    rejects the whole bundle with 400 Bad Request.

    :param resource: the FHIR resource being processed (Patient, Practitioner
        or Organization -- caller must have already confirmed via
        get_if_none_exist that this type is supported)
    :param raw: the raw ifNoneExist string (from get_if_none_exist)
    :returns: the matched content object, or None for zero matches
    :raises ResourceValidationError: code="invalid" (HTTP 400) when the
        precondition is malformed, and code="multiple-matches" (mapped to
        HTTP 412 by post()) when more than one object matches
    """
    resource_type = resource.resourceType
    expression = ["{}.request.ifNoneExist".format(resource_type)]
    system, value = parse_if_none_exist(raw)
    catalog, internal_id, external_id, external_index = \
        MATCH_TABLE[resource_type]
    internal_system = to_naming_system_url(internal_id)
    external_system = to_naming_system_url(external_id)

    if not system:
        raise ResourceValidationError(
            "Missing identifier system in {}.request.ifNoneExist: {!r}"
            .format(resource_type, raw),
            expression=expression, code="invalid")
    if system not in (internal_system, external_system):
        raise ResourceValidationError(
            "Unsupported identifier system in {}.request.ifNoneExist: {}"
            .format(resource_type, system),
            expression=expression, code="invalid")
    if not value:
        raise ResourceValidationError(
            "Missing identifier value in {}.request.ifNoneExist: {!r}"
            .format(resource_type, raw),
            expression=expression, code="invalid")

    portal_type = fapi.get_portal_type(resource)
    index = "id" if system == internal_system else external_index
    brains = api.search({"portal_type": portal_type, index: value}, catalog)

    if len(brains) > 1:
        raise ResourceValidationError(
            "Multiple {} resources match ifNoneExist: {}"
            .format(resource_type, raw),
            expression=expression, code="multiple-matches")

    return api.get_object(brains[0]) if brains else None
