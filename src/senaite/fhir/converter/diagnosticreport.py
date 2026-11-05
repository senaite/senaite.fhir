# -*- coding: utf-8 -*-

import base64

from bika.lims import api
from senaite.core.interfaces import IResultsReport
from senaite.fhir import api as fapi
from senaite.fhir.config import CLIENT_SAMPLE_ID_SYSTEM
from senaite.fhir.config import DEFAULT_REPORT_PROFILE_CODE
from senaite.fhir.config import DIAGNOSTIC_REPORT_STATUSES
from senaite.fhir.converter import to_fhir_identifier as to_fhir_id
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.resource.diagnosticreport import DiagnosticReportResource
from senaite.patient import api as papi
from zope.component import adapter
from zope.interface import implementer


@adapter(IResultsReport)
@implementer(IContentToFHIR)
class ResultsReportToResource(object):
    """
    Convert a local ResultsReport into a FHIR DiagnosticReport.
    """

    def __init__(self, report):
        self.report = report

    def to_fhir_resource(self):
        profile_url = to_fhir_profile_url("SenaiteDiagnosticReport")
        data = {
            "resourceType": "DiagnosticReport",
            "id": str(fapi.get_uuid(self.report)),
            "meta": {
                "profile": [profile_url],
                "lastUpdated": self.get_last_updated(),
            },
            "status": self.get_status(),
            "code": self.get_code(),
            "identifier": self.get_identifier(),
            "subject": self.get_subject(),
            "result": self.get_result(),
            "presentedForm": self.get_presented_form(),
        }

        based_on = self.get_based_on()
        if based_on:
            data["basedOn"] = based_on

        return DiagnosticReportResource(data)

    def get_sample(self):
        return self.report.getSample()

    def get_last_updated(self):
        sample = self.get_sample()
        modified = api.get_modification_date(sample)
        return to_fhir_datetime(modified)

    def get_status(self):
        sample = self.get_sample()
        status = api.get_review_status(sample)
        mapping = dict(DIAGNOSTIC_REPORT_STATUSES)
        fhir_status = mapping.get(status)
        if fhir_status:
            return fhir_status
        # return default (None as the key)
        return mapping.get(None)

    def get_identifier(self):
        sample = self.get_sample()
        identifiers = [
            to_fhir_id("sample-id", sample.getId(), use="usual"),
        ]
        client_sample_id = sample.getClientSampleID()
        if client_sample_id:
            identifiers.append(
                to_fhir_id(
                    CLIENT_SAMPLE_ID_SYSTEM,
                    client_sample_id,
                    use="secondary")
            )
        return identifiers

    def get_based_on(self):
        sample = self.get_sample()
        if not fapi.is_fhir_content(sample):
            # not based on a FHIR resource, was generated internally
            return []

        uids = fapi.get_fhir_uids(sample)
        service_request_uid = uids.get("ServiceRequest")

        if not service_request_uid:
            return []

        return [{
            "type": "ServiceRequest",
            "reference": "ServiceRequest/{}".format(
                fapi.get_uuid(service_request_uid)),
        }]

    def get_code(self):
        sample = self.get_sample()
        profiles = sample.getProfiles()
        if len(profiles) != 1:
            # Return the default DiagnosticReport code when 0 or more than 1
            return dict(DEFAULT_REPORT_PROFILE_CODE)

        profile = profiles[0]
        system = fapi.get_system_code("AnalysisProfile")
        profile_key = profile.getProfileKey()
        title = api.get_title(profile)
        return {
            "coding": [{
                "system": system,
                "code": profile_key,
                "display": title,
            }],
            "text": title,
        }

    def get_subject(self):
        patient = self.get_patient()
        if not patient:
            return None

        return {
            "reference": "Patient/{}".format(
                fapi.get_fhir_id(patient, resource_type="Patient")
            ),
        }

    def get_result(self):
        sample = self.get_sample()
        references = []
        for analysis in sample.getAnalyses(full_objects=True):
            if not fapi.is_reportable(analysis):
                continue
            references.append({
                "reference": "Observation/{}".format(fapi.get_uuid(analysis)),
                "display": api.get_title(analysis),
            })
        return references

    def get_patient(self):
        sample = self.get_sample()
        mrn = sample.getMedicalRecordNumberValue()
        if not mrn:
            return None
        return papi.get_patient_by_mrn(mrn, include_inactive=True)

    def get_presented_form(self):
        pdf = self.report.getPdf()
        data = base64.b64encode(pdf.data)
        if not isinstance(data, str):
            data = data.decode("ascii")

        title = getattr(pdf, "filename", None)
        if not title:
            sample = self.get_sample()
            title = api.get_id(sample)

        return [{
            "contentType": "application/pdf",
            "language": "en",
            "data": data,
            "title": title,
        }]
