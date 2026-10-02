# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.schema.addressfield import BILLING_ADDRESS
from senaite.core.schema.addressfield import PHYSICAL_ADDRESS
from senaite.core.schema.addressfield import POSTAL_ADDRESS
from senaite.fhir.converter import group_by
from senaite.fhir.converter import reject_internal_identifier
from senaite.fhir.converter import to_content_address
from senaite.fhir.converter import to_naming_system_url
from senaite.fhir.converter import validate_external_identifier
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IOrganizationResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IOrganizationResource)
@implementer(IFHIRToContent)
class ResourceToOrganisation(object):

    def __init__(self, resource):
        self.resource = resource

    def to_content_dict(self):
        reject_internal_identifier(self.resource, "Organization")
        validate_external_identifier(
            self.resource, "Organization",
            to_naming_system_url("organization-external-id"))

        name = self.get_name()
        if not name:
            raise ValueError("%r: No Name" % self.resource)

        data = {"Name": name}

        # Addresses
        address = self.get_address()
        if address.get("type") == PHYSICAL_ADDRESS:
            data["PhysicalAddress"] = address
        elif address.get("type") == POSTAL_ADDRESS:
            data["PostalAddress"] = address
        elif address.get("type") == BILLING_ADDRESS:
            data["BillingAddress"] = address

        # Phone(s)
        phone = self.get_phone()
        if phone:
            data["Phone"] = api.safe_unicode(phone)

        # Fax
        fax = self.get_fax()
        if fax:
            data["Fax"] = api.safe_unicode(fax)

        # Email
        email = self.get_email()
        if email:
            data["EmailAddress"] = api.safe_unicode(email)

        return data

    def get_name(self):
        return self.resource.name

    def get_contact_resource(self):
        return self.resource.contact

    def get_address_element(self):
        """Returns the main address of this organization resource, if any
        """
        contacts = self.resource.contact
        # TODO We pick the address of the first contact
        return contacts[0].address if contacts else None

    def get_telecom_element(self):
        """Returns the main telecom information of this organization resource
        """
        contacts = self.resource.contact
        # TODO We pick the telecom of the first contact
        return contacts[0].telecom if contacts else None

    def get_address(self):
        """Returns a content dict representation of the resource address
        """
        address = self.get_address_element()
        return to_content_address(address, default_type=PHYSICAL_ADDRESS)

    def get_telecom_elements(self, system):
        # get all phones of this organization
        telecom = self.get_telecom_element()
        grouped = group_by(telecom, key="system")
        return grouped.get(system) or []

    def get_phone(self):
        """Returns the phone of this organization
        """
        phones = self.get_telecom_elements("phone")
        grouped = group_by(phones, key="use")
        element = grouped.get("work")
        return element[0].value if element else None

    def get_fax(self):
        """Returns the fax of this organization
        """
        faxes = self.get_telecom_elements("fax")
        grouped = group_by(faxes, key="use")
        element = grouped.get("work")
        return element[0].value if element else None

    def get_email(self):
        """Returns the email of this organization
        """
        emails = self.get_telecom_elements("email")
        grouped = group_by(emails, key="use")
        element = grouped.get("work")
        return element[0].value if element else None
