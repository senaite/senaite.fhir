# -*- coding: utf-8 -*-

from senaite.fhir import api as fapi
from bika.lims import api
from senaite.core.interfaces import IContact
from senaite.fhir.converter import to_fhir_address
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_identifier as to_fhir_id
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.converter.person import ResourceToPerson
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IPractitionerResource
from senaite.fhir.resource.practitioner import PractitionerResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IPractitionerResource)
@implementer(IFHIRToContent)
class ResourceToContact(ResourceToPerson):

    def get_parent(self):
        """Returns the parent object to which the counterpart object should
        belong to
        """
        bundle = self.resource.get("_bundle")
        if not bundle:
            return None
        org = bundle.first_entry("resourceType", "Organization")
        return fapi.get_object(org, default=None)

    def to_content_dict(self):
        # contact should belong to a client (Organization)
        parent = self.get_parent()
        if not parent:
            raise ValueError("%r: Cannot infer parent" % self.resource)

        # build the dict
        data = super(ResourceToContact, self).to_content_dict()
        data.update({
            "portal_type": "Contact",
            "parent_path": api.get_path(parent),
        })

        # only set the external id when the practitioner carries one, so an
        # update without it does not wipe the one the contact already has
        external_id = self.get_external_id()
        if external_id:
            data["fhir_external_id"] = external_id

        return data

    def get_external_id(self):
        """Return the identifier assigned by the FHIR API consumer
        """
        identifier = self.resource.get_external_id()
        return identifier.value if identifier else None


@adapter(IContact)
@implementer(IContentToFHIR)
class ContactToPractitioner(object):
    """Converts a SENAITE Contact into a FHIR Practitioner resource
    https://fhir.senaite.org/StructureDefinition-SenaitePractitioner.html
    """

    def __init__(self, contact):
        self.contact = contact

    def to_fhir_resource(self):
        modified = api.get_modification_date(self.contact)
        data = {
            "resourceType": "Practitioner",
            "id": fapi.get_fhir_id(self.contact, "Practitioner"),
            "meta": {
                "profile": [to_fhir_profile_url("SenaitePractitioner")],
                "lastUpdated": to_fhir_datetime(modified),
            },
            "identifier": self.get_identifiers(),
            "active": api.is_active(self.contact),
            "name": [self.get_name()],
        }

        telecom = self.get_telecom()
        if telecom:
            data["telecom"] = telecom

        address = self.get_addresses()
        if address:
            data["address"] = address

        return PractitionerResource(data)

    def get_identifiers(self):
        """Returns the internal identifier assigned by SENAITE (usual) and the
        one assigned by the system of the API consumer (secondary), if any
        https://fhir.senaite.org/identifiers.html
        """
        external_id = api.safe_unicode(self.contact.getFHIRExternalID())
        identifiers = [
            to_fhir_id("practitioner-id", self.contact.getId(), use="usual"),
            to_fhir_id("practitioner-external-id", external_id,
                       use="secondary"),
        ]
        return list(filter(None, identifiers))

    def get_name(self):
        """Returns the official HumanName of the contact
        """
        given = [self.contact.getFirstname(), self.contact.getMiddlename()]
        name = {
            "use": "official",
            "family": api.safe_unicode(self.contact.getSurname()),
            "given": [api.safe_unicode(val) for val in filter(None, given)],
        }
        salutation = self.contact.getSalutation()
        if salutation:
            name["prefix"] = [api.safe_unicode(salutation)]
        return name

    def get_telecom(self):
        """Returns the list of ContactPoint elements of the contact, the
        counterpart of the ones `ResourceToPerson` reads on creation
        """
        points = [
            ("email", "work", self.contact.getEmailAddress()),
            ("phone", "work", self.contact.getBusinessPhone()),
            ("phone", "home", self.contact.getHomePhone()),
            ("phone", "mobile", self.contact.getMobilePhone()),
        ]
        return [{
            "system": system,
            "value": api.safe_unicode(value),
            "use": use,
        } for system, use, value in points if value]

    def get_addresses(self):
        """Returns the list of Address elements of the contact
        """
        addresses = [
            to_fhir_address(self.contact.getPhysicalAddress(), use="work"),
            to_fhir_address(self.contact.getPostalAddress(), use="work"),
        ]
        return list(filter(None, addresses))
