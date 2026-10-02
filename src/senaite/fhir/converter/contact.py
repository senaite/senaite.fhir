# -*- coding: utf-8 -*-

from senaite.fhir import api as fapi
from bika.lims import api
from senaite.fhir.converter import reject_internal_identifier
from senaite.fhir.converter import to_naming_system_url
from senaite.fhir.converter import validate_external_identifier
from senaite.fhir.converter.person import ResourceToPerson
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IPractitionerResource
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
        reject_internal_identifier(self.resource, "Practitioner")
        validate_external_identifier(
            self.resource, "Practitioner",
            to_naming_system_url("practitioner-external-id"))

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
