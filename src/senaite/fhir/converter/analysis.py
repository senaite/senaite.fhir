# -*- coding: utf-8 -*-

from bika.lims import api
from bika.lims.interfaces import IAnalysis
from senaite.fhir import api as fapi
from senaite.fhir.config import ANALYSIS_ID_SYSTEM
from senaite.fhir.config import DEFAULT_INSTRUMENT_SERVICE_REQUEST_CATEGORY
from senaite.fhir.config import INSTRUMENT_SERVICE_REQUEST_STATUSES
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_identifier as to_fhir_id
from senaite.fhir.converter import to_code_system_url
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.resource.servicerequest import ServiceRequestResource
from senaite.patient import api as papi
from zope.component import adapter
from zope.interface import implementer


@adapter(IAnalysis)
@implementer(IContentToFHIR)
class AnalysisToInstrumentServiceRequest(object):
    """Converts a SENAITE Analysis assigned to an Instrument into a FHIR
    SenaiteInstrumentServiceRequest resource
    """

    def __init__(self, analysis):
        self.analysis = analysis

    def to_fhir_resource(self):
        uid = fapi.get_fhir_uid(self.analysis, "ServiceRequest")
        if not uid:
            # never linked (no Instrument was ever assigned)
            return None

        sample = self.get_sample()
        profile_url = to_fhir_profile_url("SenaiteInstrumentServiceRequest")

        data = {
            "resourceType": "ServiceRequest",
            "id": str(fapi.get_uuid(uid)),
            "meta": {
                "profile": [profile_url],
                "lastUpdated": self.get_last_updated(),
            },
            "identifier": self.get_identifier(sample),
            "status": self.get_status(),
            "intent": "filler-order",
            "category": self.get_category(),
            "code": self.get_code(),
            "authoredOn": self.get_authored_on(),
        }

        based_on = self.get_based_on(sample)
        if based_on:
            data["basedOn"] = based_on

        subject = self.get_subject(sample)
        if subject:
            data["subject"] = subject

        performer = self.get_performer()
        if performer:
            data["performer"] = performer

        specimen = self.get_specimen(sample)
        if specimen:
            data["specimen"] = specimen

        note = self.get_note()
        if note:
            data["note"] = note

        return ServiceRequestResource(data)

    def get_sample(self):
        return self.analysis.getRequest()

    def get_last_updated(self):
        modified = api.get_modification_date(self.analysis)
        return to_fhir_datetime(modified)

    def get_identifier(self, sample):
        identifier = "{}_{}".format(sample.getId(), self.analysis.getId())
        return [to_fhir_id(ANALYSIS_ID_SYSTEM, identifier, use="usual")]

    def get_status(self):
        status = api.get_review_status(self.analysis)
        mapping = dict(INSTRUMENT_SERVICE_REQUEST_STATUSES)
        return mapping.get(status) or mapping.get(None)

    def get_category(self):
        return [DEFAULT_INSTRUMENT_SERVICE_REQUEST_CATEGORY]

    def get_code(self):
        title = api.safe_unicode(api.get_title(self.analysis))
        keyword = api.safe_unicode(self.analysis.getKeyword())
        description = api.safe_unicode(api.get_description(self.analysis))

        # LOINC goes first: the IG treats it as the interoperable coding and
        # the keyword as a SENAITE-internal convenience, so consumers reading
        # `coding[0]` get the interoperable one
        # TODO we rely on ProtocolID field for the LOINC code!
        coding = []
        protocol_id = api.safe_unicode(self.analysis.getProtocolID())
        if protocol_id:
            coding.append({
                "system": fapi.get_system_code("AnalysisService"),
                "code": protocol_id,
                "display": description if description else title,
            })

        # an analysis always carries a keyword
        coding.append({
            "system": to_code_system_url("analysis-keyword"),
            "code": keyword,
            "display": title,
        })

        return {"concept": {"coding": coding, "text": title}}

    def get_authored_on(self):
        """Returns the datetime the Analysis was (last) assigned to its
        Instrument, as tracked by the setInstrument monkey patch.
        """
        storage = fapi.get_fhir_storage(self.analysis)
        data = storage.get("data") or {}
        return data.get("authoredOn")

    def get_based_on(self, sample):
        if not fapi.is_fhir_content(sample):
            # not based on a FHIR resource, was generated internally
            return []

        service_request_uid = fapi.get_fhir_uids(sample).get("ServiceRequest")
        if not service_request_uid:
            return []

        return [{
            "type": "ServiceRequest",
            "reference": "ServiceRequest/{}".format(
                fapi.get_uuid(service_request_uid)),
        }]

    def get_subject(self, sample):
        patient = self.get_patient(sample)
        if not patient:
            return None

        return {"reference": "Patient/{}".format(
            fapi.get_fhir_id(patient, resource_type="Patient")),
        }

    def get_patient(self, sample):
        mrn = sample.getMedicalRecordNumberValue()
        if not mrn:
            return None
        return papi.get_patient_by_mrn(mrn, include_inactive=True)

    def get_performer(self):
        instrument = self.analysis.getInstrument()
        if not instrument:
            return []
        return [{"reference": "Device/{}".format(fapi.get_uuid(instrument))}]

    def get_specimen(self, sample):
        return [{"reference": "Specimen/{}".format(fapi.get_uuid(sample))}]

    def get_note(self):
        remarks = api.safe_unicode(self.analysis.getRemarks())
        if not remarks:
            return []
        return [{"text": remarks}]
