# -*- coding: utf-8 -*-
from senaite.fhir.config import ORGANIZATION_EXTERNAL_ID_SYSTEM
from senaite.fhir.datatype.backboneelement import BackboneElement
from senaite.fhir.datatype.extendedcontactdetail import ExtendedContactDetail
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import IOrganizationResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(IOrganizationResource)
class OrganizationResource(FHIRResource):

    external_id_system = ORGANIZATION_EXTERNAL_ID_SYSTEM

    @property
    def active(self):
        """Whether the organization's record is still in active use
        """
        return self.get("active", True)

    @property
    def type(self):
        """Kind of organization
        Value set: prov | dept | team | govt | ins | pay | edu | reli | crs |
                   cg | bus | other
        https://hl7.org/fhir/R5/valueset-organization-type.html
        """
        return self.get("type")

    @property
    def name(self):
        """Name used for the organization
        """
        return self.get("name")

    @property
    def description(self):
        """Additional details about the Organization that could be displayed as
        further information to identify the Organization beyond its name
        """
        # TODO markdown type
        return self.get("description")

    @property
    def contact(self):
        """Official contact details for the Organization
        http://hl7.org/fhir/R5/metadatatypes.html#ExtendedContactDetail
        """
        data = self.get("contact") or []
        return [ExtendedContactDetail(item) for item in data]

    @property
    def partOf(self):
        """The organization of which this organization forms a part
        http://hl7.org/fhir/R5/organization.html
        """
        data = self.get("partOf")
        return OrganizationResource(data) if data else None

    @property
    def qualification(self):
        """Qualifications, certifications, accreditations, licenses, training,
        etc. pertaining to the provision of care
        """
        data = self.get("qualification") or []
        return [BackboneElement(item) for item in data]

    @property
    def identifier(self):
        """Returns the Identifier that identifies the organization across
        multiple systems
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]
