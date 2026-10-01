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


def to_fhir_address(address, use=None):
    """Converts the dict representation of an Address field of AT/DX contents
    to a FHIR Address element, the counterpart of `to_content_address`.
    Returns None when the address carries no content
    """
    if not address:
        return None

    def get_value(*keys):
        # DX and AT types name some of the address keys differently
        for key in keys:
            value = api.safe_unicode(address.get(key) or u"").strip()
            if value:
                return value
        return u""

    lines = get_value("address")
    city = get_value("city")
    postal_code = get_value("zip")
    state = get_value("subdivision1", "state")
    district = get_value("subdivision2", "district")
    country = get_value("country")
    if not any([lines, city, postal_code, state, district, country]):
        return None

    # FHIR expects the ISO 3166 code of the country, rather than its name
    if country:
        found = geo.get_country(country, default=None)
        country = api.safe_unicode(found.alpha_2) if found else country

    data = {}
    if use:
        data["use"] = use
    address_type = address.get("type")
    if address_type in [PHYSICAL_ADDRESS, POSTAL_ADDRESS]:
        data["type"] = address_type
    if lines:
        data["line"] = [lines]
    if city:
        data["city"] = city
    if district:
        data["district"] = district
    if state:
        data["state"] = state
    if postal_code:
        data["postalCode"] = postal_code
    if country:
        data["country"] = country
    return data


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
