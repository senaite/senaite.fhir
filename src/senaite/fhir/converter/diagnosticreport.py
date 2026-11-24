# -*- coding: utf-8 -*-

import base64

from bika.lims import api
from senaite.core.interfaces import IResultsReport
from senaite.fhir import api as fapi
from senaite.fhir.config import CLIENT_SAMPLE_ID_SYSTEM
from senaite.fhir.config import DEFAULT_REPORT_PROFILE_CODE
from senaite.fhir.config import DIAGNOSTIC_REPORT_STATUSES
from senaite.fhir.config import SAMPLE_GROUP_ID_SYSTEM
from senaite.fhir.config import SAMPLE_ID_SYSTEM
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

    def get_samples(self):
        """Returns every sample covered by the report
        """
        samples = list(self.report.getContainedSamples() or [])
        sample = self.get_sample()
        if sample not in samples:
            samples.insert(0, sample)
        return samples

    def get_last_updated(self):
        sample = self.get_sample()
        modified = api.get_modification_date(sample)
        return to_fhir_datetime(modified)

    def get_status(self):
        mapping = dict(DIAGNOSTIC_REPORT_STATUSES)
        sample = self.get_sample()
        status = api.get_review_status(sample)
        fhir_status = mapping.get(status) or mapping.get(None)
        published = (
            api.get_review_status(sample) == "published"
            for sample in self.get_samples()
        )
        if fhir_status == "final" and not all(published):
            return "preliminary"
        return fhir_status

    def get_identifier(self):
        identifiers = []
        group_ids = set()
        for sample in self.get_samples():
            identifiers.append(
                to_fhir_id(SAMPLE_ID_SYSTEM, sample.getId(), use="usual"),
            )
            client_sample_id = sample.getClientSampleID()
            if client_sample_id:
                identifiers.append(
                    to_fhir_id(
                        CLIENT_SAMPLE_ID_SYSTEM,
                        client_sample_id,
                        use="secondary")
                )

            group_id = sample.getClientOrderNumber()
            if group_id and group_id not in group_ids:
                identifiers.append(
                    to_fhir_id(SAMPLE_GROUP_ID_SYSTEM, group_id)
                )
                group_ids.add(group_id)
        return identifiers

    def get_based_on(self):
        references = []
        for sample in self.get_samples():
            if not fapi.is_fhir_content(sample):
                continue

            service_request_uid = fapi.get_fhir_uids(sample).get(
                "ServiceRequest")
            if not service_request_uid:
                continue

            references.append({
                "type": "ServiceRequest",
                "reference": "ServiceRequest/{}".format(
                    fapi.get_uuid(service_request_uid)),
            })

        return references

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
        references = []
        for sample in self.get_samples():
            for analysis in sample.getAnalyses(full_objects=True):
                if not fapi.is_reportable(analysis):
                    continue
                references.append({
                    "reference": "Observation/{}".format(
                        fapi.get_uuid(analysis)),
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
