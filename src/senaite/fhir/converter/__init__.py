# -*- coding: utf-8 -*-
import collections
import copy

from bika.lims import api
from senaite.core.api import dtime
from senaite.core.api import geo
from senaite.core.schema.addressfield import OTHER_ADDRESS
from senaite.core.schema.addressfield import PHYSICAL_ADDRESS
from senaite.core.schema.addressfield import POSTAL_ADDRESS
from senaite.fhir.config import FHIR_BASE_URL
from senaite.fhir.exceptions import ServiceRequestValidationError
from zope.deprecation import deprecate


def to_naming_system_url(system_id):
    """Returns the canonical NamingSystem URI for an identifier namespace

    `system_id` is the NamingSystem id as published in the implementation
    guide, e.g. `sample-id`, `analysis-id` or `client-sample-id`. The URI it
    builds is what a FHIR `Identifier.system` has to carry for a consumer to
    tell one namespace from another, so it serves both to stamp outgoing
    identifiers (see `to_fhir_identifier`) and to check the system of the
    incoming ones.
    https://fhir.senaite.org/identifiers.html
    """
    return "%s/NamingSystem/%s" % (FHIR_BASE_URL, system_id)


def to_code_system_url(system_id):
    """Returns the canonical CodeSystem URI
    Please see: https://fhir.senaite.org/artifacts.html#terminology
    """
    return "%s/CodeSystem/%s" % (FHIR_BASE_URL, system_id)


def to_fhir_identifier(system_id, value, use=None):
    if not value:
        return None
    data = {
        "system": to_naming_system_url(system_id),
        "value": value,
    }
    if use:
        data["use"] = use
    return data


def reject_internal_identifier(resource, resource_name):
    """Raise if the incoming resource carries an internal (usual)
    identifier - these are assigned by SENAITE only after creation and
    may never be supplied by the API consumer
    """
    object_id = resource.get_object_id()
    if object_id:
        msg = (
            "Cannot specify usual identifier externally in incoming "
            "{}:{}"
        ).format(resource_name, object_id.value)
        raise ServiceRequestValidationError(
            msg,
            expression=["{}.identifier".format(resource_name)],
            code="invalid",
        )


def validate_external_identifier(resource, resource_name, valid_system=None):
    """Raise if the incoming resource's external (secondary) identifier,
    if any, has no system or a system other than `valid_system`.

    Pass `valid_system=None` when the resource must not carry an external
    identifier at all (e.g. ServiceRequest)
    """
    external_id = resource.get_external_id()
    if external_id:
        if valid_system is None:
            msg = (
                "Cannot specify external identifier in "
                "{}:{}"
            ).format(resource_name, external_id.value)
            raise ServiceRequestValidationError(
                msg,
                expression=["{}.identifier".format(resource_name)],
                code="invalid",
            )
        if external_id.system != valid_system:
            msg = (
                "Unsupported identifier system in {}: {}"
            ).format(resource_name, external_id.system)
            raise ServiceRequestValidationError(
                msg,
                expression=["{}.identifier".format(resource_name)],
                code="invalid",
            )


def reject_any_identifier(resource, resource_name):
    """Raise if the incoming resource carries any identifier at all,
    regardless of its `use`.

    `reject_internal_identifier`/`validate_external_identifier` only
    recognize `use="usual"`/`use="secondary"`; this is the backstop for a
    resource that must not carry an identifier under any `use` (e.g. an
    identifier with `use="official"`, or none at all), such as
    ServiceRequest.
    """
    identifiers = getattr(resource, "identifier", None)
    if identifiers:
        msg = "Cannot specify any identifier in {}".format(resource_name)
        raise ServiceRequestValidationError(
            msg,
            expression=["{}.identifier".format(resource_name)],
            code="invalid",
        )


def to_fhir_profile_url(resource_type):
    if not resource_type:
        return None
    return "%s/StructureDefinition/%s" % (FHIR_BASE_URL, resource_type)


def to_fhir_datetime(dt):
    """Serialize a date as a FHIR dateTime in the configured portal timezone.
    """
    dt = dtime.to_dt(dt)
    if dt is None:
        return None

    timezone = api.get_registry_record("plone.portal_timezone")
    if dtime.is_valid_timezone(timezone):
        dt = dtime.to_zone(dt, timezone)
    elif dtime.is_timezone_naive(dt):
        dt = dtime.to_zone(dt, dtime.get_os_timezone())

    return dt.replace(microsecond=0).isoformat()


@deprecate("Use first_by instead")
def get_by_key(items, key, value, default=None):
    kwargs = {key: value}
    return first_by(items, default=default, **kwargs)


def first_by(items, default=None, **kwargs):
    items = items if items else []
    matches = [copy.deepcopy(item) for item in items]
    for key, val in kwargs.items():
        matches = [item for item in matches if item.get(key) == val]
    return matches[0] if matches else default


def group_by(items, key):
    groups = collections.OrderedDict()
    items = items if items else []
    for item in items:
        val = item.get(key)
        groups.setdefault(val, []).append(item)
    return groups


def to_content_address(address, default_type=POSTAL_ADDRESS):
    """Converts the FHIR Address element to a dict representation suitable for
    Address fields of AT/DX contents
    """
    if not address:
        return None

    # resolve the address type
    address_type = address.type or default_type
    supported = [PHYSICAL_ADDRESS, POSTAL_ADDRESS, OTHER_ADDRESS]
    if address_type not in supported:
        address_type = default_type

    # resolve the address lines
    lines = ", ".join(address.line or [])

    # resolve the country
    country = geo.get_country(address.country, default=None)
    country = country.name if country else ""

    # resolve the state (as a sub-unit of country)
    state = address.state or ""
    if country and state:
        sub = geo.get_subdivision(state, parent=country)
        state = sub.name if sub else state

    # resolve the district
    district = address.district or ""
    if country and state:
        sub = geo.get_subdivision(district, parent=state, default=None)
        if not sub:
            sub = geo.get_subdivision(district, parent=country, default=None)
        district = sub.name if sub else district

    # resolve the postal code
    postal_code = address.postalCode or ""

    # resolve the city
    city = address.city or ""

    return {
        "address": api.safe_unicode(lines),
        "zip": api.safe_unicode(postal_code),
        "city": api.safe_unicode(city),
        "country": api.safe_unicode(country),
        # Suport for DX types
        "type": address_type,
        "subdivision2": api.safe_unicode(district),
        "subdivision1": api.safe_unicode(state),
        # support for AT types
        "district": api.safe_unicode(district),
        "state": api.safe_unicode(state),
    }


def get_telecom_elements(telecom, system, use=None):
    """Returns the element from the telecom (ContactPoint) provided for the
    given system and use
    """
    by_system = group_by(telecom, key="system")
    elements = by_system.get(system) or []
    if use is None:
        return elements
    by_use = group_by(elements, key="use")
    return by_use.get(use) or []


def get_emails(telecom, use=None):
    """Returns the email elements from the telecom (ContactPoint) provided
    """
    return get_telecom_elements(telecom, "email", use=use)


def get_phones(telecom, use=None):
    """Returns the phone elements from the telecom (ContactPoint) provided
    """
    return get_telecom_elements(telecom, "phone", use=use)
