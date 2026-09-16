# -*- coding: utf-8 -*-

from senaite.fhir import api as fapi
from bika.lims import api
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
        # contact should belong to a client (Organization)
        parent = self.get_parent()
        if not parent:
            raise ValueError("%r: Cannot infer parent" % self.resource)

        # build the dict
        data = super(ResourceToContact, self).to_content_dict()
        data.update({
            "portal_type": "Contact",
            "parent_path": api.get_path(parent),
            "external_id": self.get_external_id(),
        })
        return data

    def get_external_id(self):
        """Return the identifier assigned by the FHIR API consumer
        """
        identifier = self.resource.get_external_id()
        return identifier.value if identifier else None
