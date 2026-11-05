# -*- coding: utf-8 -*-

from senaite.fhir import api as fapi
from bika.lims import api
from senaite.fhir.converter.person import ResourceToPerson
from senaite.fhir.exceptions import ResourceValidationError
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IPractitionerResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IPractitionerResource)
@implementer(IFHIRToContent)
class ResourceToContact(ResourceToPerson):

    def validate(self):
        """Raises a ResourceValidationError if the resource violates any of
        the validation rules. The external identifier is required, as it is
        the only key the Practitioner is matched to its Contact by: without
        it, every request would create another Contact
        """
        super(ResourceToContact, self).validate()
        identifier = self.resource.get_external_id()
        if not identifier or not identifier.value:
            raise ResourceValidationError(
                "Missing external identifier in Practitioner",
                expression=["Practitioner.identifier"], code="invalid")

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
        self.validate()

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
