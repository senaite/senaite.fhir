# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.schema.addressfield import PHYSICAL_ADDRESS
from senaite.core.schema.addressfield import POSTAL_ADDRESS
from senaite.fhir.converter import get_by_key
from senaite.fhir.converter import get_emails
from senaite.fhir.converter import get_phones
from senaite.fhir.converter import group_by
from senaite.fhir.converter import ResourceToContent
from senaite.fhir.converter import to_content_address
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IOrganizationResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IOrganizationResource)
@implementer(IFHIRToContent)
class ResourceToPerson(ResourceToContent):

    def to_content_dict(self):
        # Person name
        salutation = self.get_salutation()
        firstname = self.get_firstname()
        middlename = self.get_middlename()
        lastname = self.get_lastname()
        if not any([firstname, lastname]):
            raise ValueError("%r: No valid name" % self.resource)

        # Email(s)
        primary_email = self.get_primary_email()

        # Phone(s)
        home_phone = self.get_home_phone()
        work_phone = self.get_work_phone()
        mobile_phone = self.get_mobile_phone()

        # Addresses
        physical_address = self.get_physical_address()
        postal_address = self.get_postal_address()

        return {
            "Salutation": api.safe_unicode(salutation),
            "Firstname": api.safe_unicode(firstname),
            "Middlename": api.safe_unicode(middlename),
            "Surname": api.safe_unicode(lastname),
            "EmailAddress": api.safe_unicode(primary_email),
            "BusinessPhone": api.safe_unicode(work_phone),
            "HomePhone": api.safe_unicode(home_phone),
            "MobilePhone": api.safe_unicode(mobile_phone),
            "PhysicalAddress": physical_address,
            "PostalAddress": postal_address,
            # TODO Shall we get Person.JobTitle from qualification element?
            "JobTitle": "",
            # TODO Shall we get Person.Department from qualification element?
            "Department": "",
        }

    def get_human_name(self):
        """Returns a dict that represents the name of the Person
        """
        name = get_by_key(self.resource.name, key="use", value="official")
        if name:
            return name

        # no official name, pick the first one
        name = self.resource.name
        return name[0] if name else None

    def get_salutation(self):
        name = self.get_human_name()
        prefix = name.prefix
        return prefix[0] if prefix else ""

    def get_firstname(self):
        name = self.get_human_name()
        given = name.given
        return given[0] if given else ""

    def get_middlename(self):
        name = self.get_human_name()
        given = name.given
        return given[1] if len(given) > 1 else ""

    def get_lastname(self):
        name = self.get_human_name()
        return name.family if name else ""

    def get_primary_email(self):
        """Returns the primary email address
        """
        # get all emails and group them by use
        all_emails = get_emails(self.resource.telecom)
        by_use = group_by(all_emails, key="use")

        # get the first email based on these use priorities
        uses = ["work", "home", "temp", "old"]
        for use in uses:
            emails = by_use.get(use)
            if emails:
                return emails[0].value

        return None

    def get_home_phone(self):
        """Returns the Home phone of this person
        """
        home = get_phones(self.resource.telecom, use="home")
        return home[0].value if home else None

    def get_work_phone(self):
        """Returns the Home phone of this person
        """
        work = get_phones(self.resource.telecom, use="work")
        return work[0].value if work else None

    def get_mobile_phone(self):
        """Returns the first mobile phone of this person
        """
        mobile = get_phones(self.resource.telecom, use="mobile")
        return mobile[0].value if mobile else None

    def get_primary_address(self, address_type, uses):
        """Returns the primary address of the given type with the priority
        defined by uses, if any
        """
        # group addresses by type
        by_type = group_by(self.resource.address, key="type")
        addresses_of_type = by_type.get(address_type)
        if not addresses_of_type:
            # TODO fallback to all addresses regardless of type
            addresses_of_type = self.resource.address

        # group addresses by use
        by_use = group_by(addresses_of_type, key="use")

        # get the first one based on these use priorities
        for use in uses:
            addresses_of_use = by_use.get(use)
            if addresses_of_use:
                return addresses_of_use[0]

        return None

    def get_physical_address(self):
        """Returns the primary physical address of this person
        """
        uses = ["work", "home", "temp", "billing", "old"]
        address = self.get_primary_address("physical", uses)
        return to_content_address(address, default_type=PHYSICAL_ADDRESS)

    def get_postal_address(self):
        """Returns the primary postal address of this person
        """
        uses = ["work", "home", "temp", "billing", "old"]
        address = self.get_primary_address("postal", uses)
        return to_content_address(address, default_type=POSTAL_ADDRESS)
