# -*- coding: utf-8 -*-

from senaite.core.api import dtime
from senaite.fhir.config import PRACTITIONER_EXTERNAL_ID_SYSTEM
from senaite.fhir.datatype.address import Address
from senaite.fhir.datatype.backboneelement import BackboneElement
from senaite.fhir.datatype.contactpoint import ContactPoint
from senaite.fhir.datatype.humanname import HumanName
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import IPractitionerResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(IPractitionerResource)
class PractitionerResource(FHIRResource):

    external_id_system = PRACTITIONER_EXTERNAL_ID_SYSTEM

    @property
    def active(self):
        """Whether this practitioner's record is in active use
        """
        return self.get("active", True)

    @property
    def name(self):
        """The name(s) associated with the practitioner
        """
        items = self.get("name") or []
        return [HumanName(item) for item in items]

    @property
    def identifier(self):
        """An identifier for the person as this agent
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def telecom(self):
        """A contact detail for the practitioner (that apply to all roles)
        """
        data = self.get("telecom") or []
        return [ContactPoint(item) for item in data]

    @property
    def gender(self):
        """The administrative gender of the practitioner
        Value set: male | female | other | unknown
        https://hl7.org/fhir/R5/valueset-administrative-gender.html
        """
        return self.get("gender")

    @property
    def birthDate(self):
        """The date on which the practitioner was born
        """
        return dtime.to_dt(self.get("birthDate"))

    @property
    def address(self):
        """Address(es) of the practitioner that are not role specific
        (typically home address)
        """
        data = self.get("address") or []
        return [Address(item) for item in data]

    @property
    def photo(self):
        """Image of the person
        """
        # TODO should return a list of Attachment data types
        return self.get("photo") or []

    @property
    def qualification(self):
        """Qualifications, certifications, accreditations, licenses, training,
        etc. pertaining to the provision of care
        """
        data = self.get("qualification") or []
        return [BackboneElement(item) for item in data]

    @property
    def communication(self):
        """	A language which may be used to communicate with the practitioner
        """
        data = self.get("communication") or []
        return [BackboneElement(item) for item in data]
