# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.api import dtime
from senaite.fhir.config import PATIENT_MRN_SYSTEM
from senaite.fhir.converter import get_by_key
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.datatype.address import Address
from senaite.fhir.datatype.codeableconcept import CodeableConcept
from senaite.fhir.datatype.contactpoint import ContactPoint
from senaite.fhir.datatype.humanname import HumanName
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import IPatientResource
from senaite.fhir.resource import FHIRResource
from senaite.patient.config import GENDERS
from zope.interface import implementer

_marker = object()


@implementer(IPatientResource)
class PatientResource(FHIRResource):

    external_id_system = PATIENT_MRN_SYSTEM

    @property
    def name(self):
        items = self.get("name") or []
        return [HumanName(item) for item in items]

    @property
    def identifier(self):
        """Returns the Identifier that identifies the organization across
        multiple systems
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def gender(self):
        """The administrative gender of the patient
        Value set: male | female | other | unknown
        https://hl7.org/fhir/R5/valueset-administrative-gender.html
        """
        return self.get("gender")

    @property
    def birthDate(self):
        """The date on which the patient was born
        """
        return dtime.to_dt(self.get("birthDate"))

    @property
    def estimatedDateBirth(self):
        url = to_fhir_profile_url("EstimatedDateBirth")
        ext = get_by_key(self.extension, key="url", value=url, default={})
        return bool(ext.get("valueBoolean", False))

    @property
    def address(self):
        """Returns a list of Address resources
        """
        data = self.get("address") or []
        return [Address(item) for item in data]

    @property
    def maritalStatus(self):
        """Marital (civil) status of a patient
        """
        data = self.get("maritalStatus")
        return CodeableConcept(data) if data else None

    @property
    def telecom(self):
        """A contact detail for the person, e.g. a telephone number or an
        email address.
        """
        data = self.get("telecom") or []
        return [ContactPoint(item) for item in data]

    def get_identifier(self, use):
        return get_by_key(self.identifier, key="use", value=use)

    def get_name(self, use):
        return get_by_key(self.name, key="use", value=use)

    def get_address(self, use):
        return get_by_key(self.address, key="use", value=use)

    def to_object_info(self):
        """Returns a dict representation of the Patient resource, suitable for
        the creation and edition of SENAITE Patient objects
        """
        sexes = dict(GENDERS)
        mrn = self.get_mrn()
        sex = sexes.get(self.get("gender")) or ""
        fullname = self.get_fullname()
        # If no "official" name found, use the first available name
        if not fullname:
            patient_names = self.get("name")
            if patient_names:
                fullname = patient_names[0]

        givenname = self.get_givenname()
        firstname = givenname[0] if givenname != "" else ""
        middlename = (
            givenname[1]
            if givenname != "" and len(givenname) == 2 else ""
        )
        lastname = fullname.get("family", "") if fullname else ""
        birthdate = self.get("birthDate")
        address = self.get_address()

        if address:
            address_line = address.get("line", [""])
            address = list([{
                "type": api.safe_unicode(address.get("type", "")),
                "address": (
                    api.safe_unicode(address_line[0]) if address_line else ""
                ),
                "city": api.safe_unicode(address.get("city", "")),
            }])

        return {
            "mrn": mrn,
            "sex": sex,
            "birthdate": birthdate,
            "address": address,
            "gender": "",
            "firstname": api.safe_unicode(firstname),
            "middlename": api.safe_unicode(middlename),
            "lastname": api.safe_unicode(lastname),
            "portal_type": "Patient",
        }
