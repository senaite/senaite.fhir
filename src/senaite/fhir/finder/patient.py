# -*- coding: utf-8 -*-

from senaite.fhir.interfaces import IContentFinder
from senaite.fhir.interfaces import IPatientResource
from senaite.patient import api as papi
from zope.component import adapter
from zope.interface import implementer


@adapter(IPatientResource)
@implementer(IContentFinder)
class PatientFinder(object):
    """Adapter in charge of searching the counterpart Patient object of a FHIR
    Patient resource
    """

    def __init__(self, resource):
        self.resource = resource

    def find(self):
        """Looks for the resource's counterpart Patient object
        """
        # search by MRN, the external identifier of the Patient
        identifier = self.resource.get_external_id()
        if identifier and identifier.value:
            return papi.get_patient_by_mrn(identifier.value,
                                           include_inactive=True)

        return None
