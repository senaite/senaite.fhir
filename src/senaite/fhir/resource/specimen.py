# -*- coding: utf-8 -*-

from senaite.core.api import dtime
from senaite.fhir import api as fapi
from senaite.fhir.config import CLIENT_SAMPLE_ID_SYSTEM
from senaite.fhir.converter import get_by_key
from senaite.fhir.datatype.codeableconcept import CodeableConcept
from senaite.fhir.datatype.codeablereference import CodeableReference
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import ISpecimenResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(ISpecimenResource)
class SpecimenResource(FHIRResource):

    external_id_system = CLIENT_SAMPLE_ID_SYSTEM

    @property
    def type(self):
        data = self.get("type")
        return CodeableConcept(data) if data else data

    @property
    def collection(self):
        return self.get("collection")

    @property
    def identifier(self):
        """Returns the Identifier(s) that identify this specimen across
        multiple systems
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def collectedDateTime(self):
        data = self.collection or {}
        return dtime.to_dt(data.get("collectedDateTime"))

    @property
    def bodySite(self):
        element = self.collection.get("bodySite")
        if not element:
            return None
        reference = CodeableReference(element)
        return reference.concept

    def get_code(self, system=None):
        """Returns the code for the given system. If no system is set, uses
        the default system
        """
        if not system:
            system = fapi.get_system_code("Specimen")
        return get_by_key(self.type.coding, key="system", value=system)
