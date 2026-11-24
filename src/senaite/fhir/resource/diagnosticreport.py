# -*- coding: utf-8 -*-

from senaite.fhir.datatype.codeableconcept import CodeableConcept
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.datatype.reference import Reference
from senaite.fhir.interfaces import IDiagnosticReportResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(IDiagnosticReportResource)
class DiagnosticReportResource(FHIRResource):
    """FHIR DiagnosticReport resource.
    https://fhir.senaite.org/StructureDefinition-SenaiteDiagnosticReport.html
    """

    __cardinality = (
        ("id", "1..1"),
        ("identifier", "0..*"),
        ("basedOn", "0..*"),
        ("status", "1..1"),
        ("code", "1..1"),
        ("subject", "0..1"),
        ("result", "0..*"),
        ("presentedForm", "0..1"),
    )

    @property
    def identifier(self):
        """Returns the Identifier that identifies the organization across
        multiple systems
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.identifier
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def basedOn(self):
        """What this diagnostic report is based on.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.basedOn
        """
        data = self.get("basedOn") or []
        return [Reference(item) for item in data]

    @property
    def status(self):
        """The status of the diagnostic report.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.status
        """
        return self.get("status")

    @property
    def code(self):
        """Name or code for this diagnostic report.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.code
        """
        element = self.get("code")
        return CodeableConcept(element) if element else None

    @property
    def subject(self):
        """The subject of the report, usually the patient.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.subject
        """
        element = self.get("subject")
        return Reference(element) if element else None

    @property
    def result(self):
        """Observations that form the basis of this diagnostic report.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.result
        """
        data = self.get("result") or []
        return [Reference(item) for item in data]

    @property
    def presentedForm(self):
        """Entire report as issued, including the PDF attachment.
        https://www.hl7.org/fhir/R5/diagnosticreport-definitions.html#DiagnosticReport.presentedForm
        """
        return self.get("presentedForm") or []
