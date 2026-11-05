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
    SENAITE evaluates ifNoneExist for (see `validate_if_none_exist`), or the
    resource isn't part of a bundle at all (e.g. a standalone POST /Patient,
    which has no entry.request to begin with).

    :param resource: the FHIR resource being processed by post()
    :returns: the raw ifNoneExist value, or None
    """
    if resource.resourceType not in MATCH_TABLE:
        return None
    return get_raw_if_none_exist(resource)


def get_raw_if_none_exist(resource):
    """Returns the raw `ifNoneExist` string declared on the bundle entry of
    the given resource, whatever its type, or None when absent or when the
    resource isn't part of a bundle

    :param resource: the FHIR resource of a bundle entry
    :returns: the raw ifNoneExist value, or None
    """
    bundle = resource.get("_bundle")
    if not bundle:
        return None
    return bundle.get_request(resource).get("ifNoneExist")


def validate_if_none_exist(resource):
    """Raises a ResourceValidationError if the bundle entry of the resource
    declares an `ifNoneExist` but its type does not support conditional
    create. Only the types in `MATCH_TABLE` do: the profile does not allow
    `request.ifNoneExist` for the others (e.g. ServiceRequest and Specimen,
    `0..0`), as they are created on every order

    :param resource: the FHIR resource of a bundle entry
    """
    if resource.resourceType in MATCH_TABLE:
        return
    if not get_raw_if_none_exist(resource):
        return
    resource_type = resource.resourceType
    raise ResourceValidationError(
        "ifNoneExist is not supported for {}".format(resource_type),
        expression=["{}.request.ifNoneExist".format(resource_type)],
        code="invalid")


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


def get_if_none_exist_warning(resource, obj):
    """Returns an OperationOutcome issue warning that the external identifier
    of the resource differs from the one of the object its ifNoneExist
    matched, or None when they are the same or the resource carries none.

    A match discards the resource, so the identifier it carries is not
    applied. That may be on purpose (e.g. the consumer corrected the MRN on
    its side and matches by the old one) or a mistake in the condition, which
    links the bundle to another Patient. SENAITE cannot tell one from the
    other, so it accepts the match and warns the consumer.

    :param resource: the FHIR resource whose ifNoneExist matched `obj`
    :param obj: the content object matched by `find_by_if_none_exist`
    :returns: an OperationOutcome issue dict, or None
    """
    external_id = resource.get_external_id()
    if not external_id:
        return None

    # read the identifier the same way the match does: from the index
    resource_type = resource.resourceType
    catalog_id, _, _, external_index = MATCH_TABLE[resource_type]
    catalog = api.get_tool(catalog_id)
    index_data = catalog.getIndexDataForUID(api.get_path(obj))
    matched_value = index_data.get(external_index) or None
    if matched_value == external_id.value:
        return None

    return {
        "severity": "warning",
        "code": "business-rule",
        "details": {
            "text": "ifNoneExist matched an existing {0} with identifier "
                    "{1}, but the {0} in the request carries {2}. The {0} in "
                    "the request was not applied"
                    .format(resource_type, matched_value, external_id.value),
        },
        "expression": ["{}.identifier".format(resource_type)],
    }
