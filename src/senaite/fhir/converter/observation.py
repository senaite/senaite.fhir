# -*- coding: utf-8 -*-

from bika.lims import api
from bika.lims.interfaces import IAnalysis
from DateTime import DateTime
from senaite.core.api import dtime
from senaite.core.api import workflow as wapi
from senaite.fhir import api as fapi
from senaite.fhir.config import OBSERVATION_STATUSES
from senaite.fhir.config import UCUM_SYSTEM
from senaite.fhir.converter import first_by
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.converter import to_code_system_url
from senaite.fhir.exceptions import ObservationValidationError
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IObservationResource
from senaite.fhir.resource.observation import ObservationResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IAnalysis)
@implementer(IContentToFHIR)
class AnalysisToObservation(object):
    """Convert a SENAITE Analysis into a FHIR Observation resource.
    """

    def __init__(self, analysis):
        self.analysis = analysis

    def to_fhir_resource(self):
        profile_url = to_fhir_profile_url("SenaiteObservation")
        data = {
            "resourceType": "Observation",
            "id": str(fapi.get_uuid(self.analysis)),
            "meta": {
                "profile": [profile_url],
                "lastUpdated": self.get_last_updated(),
            },
            "status": self.get_status(),
            "code": self.get_code(),
        }

        based_on = self.get_based_on()
        if based_on:
            data["basedOn"] = based_on

        performer = self.get_performer()
        if performer:
            data["performer"] = performer

        note = self.get_note()
        if note:
            data["note"] = note

        data.update(self.get_value())
        ref_range = self.get_reference_range()
        if ref_range:
            data["referenceRange"] = ref_range

        device = self.get_device()
        if device:
            data["device"] = device

        return ObservationResource(data)

    def get_last_updated(self):
        modified = api.get_modification_date(self.analysis)
        return dtime.to_localized_time(modified, long_format=True)

    def get_status(self):
        status = api.get_review_status(self.analysis)
        mapping = dict(OBSERVATION_STATUSES)
        fhir_status = mapping.get(status)
        if fhir_status:
            return fhir_status
        # return default (None as the key)
        return mapping.get(None)

    def get_sample(self):
        return self.analysis.getRequest()

    def get_source_data(self):
        sample = self.get_sample()
        if not fapi.is_fhir_content(sample):
            return {}
        storage = fapi.get_fhir_storage(sample)
        return storage.get("data") or {}

    def get_code(self):
        """ Here we build the code which will include the keyword
         and its corresponding LOINC code.
        """
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

        return {
            "coding": coding,
            "text": title,
        }

    def get_based_on(self):
        source_data = self.get_source_data()
        if source_data.get("basedOn"):
            return source_data.get("basedOn")

        sample = self.get_sample()
        if not fapi.is_fhir_content(sample):
            return []

        storage = fapi.get_fhir_storage(sample)
        uids = storage.get("uids")
        if not uids:
            return []

        service_request_uid = uids.get("ServiceRequest")
        if not service_request_uid:
            return []

        return [{
            "type": "ServiceRequest",
            "reference": "ServiceRequest/{}".format(
                fapi.get_uuid(service_request_uid)),
        }]

    def get_performer(self):
        verificators = self.analysis.getVerificators()
        userid = verificators[-1] if verificators else None
        if not userid:
            return []
        display = api.get_user_fullname(userid) or userid
        return [{
            "identifier": {"value": userid},
            "display": display,
        }]

    def get_value(self):
        if not self.is_quantitative():
            return {"valueString": self.analysis.getFormattedResult()}

        value_quantity = {
            "value": self.analysis.getResult(),
            "unit": self.analysis.getUnit(),
            "system": UCUM_SYSTEM,
            "code": self.analysis.getUnit(),
        }
        return {"valueQuantity": value_quantity}

    def get_note(self):
        remarks = api.safe_unicode(self.analysis.getRemarks())
        if not remarks:
            return []
        return [{"text": remarks}]

    def get_device(self):
        instrument = self.analysis.getInstrument()
        if not instrument:
            return None
        return {
            "reference": "Device/{}".format(fapi.get_fhir_id(instrument)),
        }

    def is_quantitative(self):
        """Returns whether the result of the analysis is quantitative
        """
        result_type = self.analysis.getResultType()
        return result_type == "numeric"

    def get_reference_range(self):
        # In FHIR, range only makes sense when the result is quantitative
        if not self.is_quantitative():
            return []

        rng = self.analysis.getResultsRange()
        if not rng:
            return []

        entry = {}
        for key, bound in (("low", "min"), ("high", "max")):
            value = rng.get(bound)
            if not api.is_floatable(value):
                continue

            entry[key] = {
                "value": value,
                "unit": self.analysis.getUnit(),
                "system": UCUM_SYSTEM,
                "code": self.analysis.getUnit(),
            }

        if not entry:
            return []

        return [entry]


@adapter(IObservationResource)
@implementer(IFHIRToContent)
class ResourceToAnalysisResult(object):
    """Converts an incoming SenaiteObservation FHIR resource into a content
    dict carrying the result to apply to its Analysis.

    The Analysis is not referenced directly: ``Observation.basedOn`` points
    to the instrument-scoped ``SenaiteInstrumentServiceRequest`` (see
    ``AnalysisToInstrumentServiceRequest``) that was handed to the analyzer,
    so the counterpart Analysis is resolved through that ServiceRequest's
    FHIR uid instead of the Observation's own id. This is also how
    ``AnalysisFinder`` resolves the pre-existing counterpart object for
    ``update()`` -- resolved again here since ``to_content_dict`` only
    receives the resource, not the object ``find_object_for`` already found.

    Submitting the Analysis once the result is applied is handled as a
    post-processing step in the ``POST`` route, the same way
    ``process_bundle_specimen`` is for ServiceRequest.
    """

    def __init__(self, resource):
        self.resource = resource

    def validate(self):
        """Does nothing. The rules of an Observation (identity, status, code
        and device) need the Analysis the result is for, so they are checked
        while the resource is converted (see `to_content_dict`)
        """

    def to_content_dict(self):
        analysis = self.get_analysis()
        self.validate_status()
        self.validate_code(analysis)
        self.validate_device(analysis)
        value = self.get_value(analysis)
        self.validate_identity(analysis)
        self.validate_submittable(analysis, value)

        content = {
            "Result": value,
            "ResultCaptureDate": DateTime(),
        }

        remarks = self.get_remarks()
        if remarks:
            content["Remarks"] = remarks

        return content

    def get_remarks(self):
        """Returns the incoming Observation notes as Analysis remarks
        """
        notes = self.resource.note
        if not notes:
            return None
        return u"\n".join(note.text for note in notes if note.text)

    def get_analysis(self):
        """Resolves the Analysis referenced by Observation.basedOn[0]
        """
        based_on = self.resource.basedOn
        if not based_on:
            raise ObservationValidationError(
                "Observation.basedOn is required to locate the Analysis "
                "this result belongs to",
                expression=["Observation.basedOn"],
                code="required",
            )

        uid = based_on[0].UID()
        analysis = fapi.get_object_by_fhir_uid(
            uid, portal_type="Analysis", default=None) if uid else None

        if not analysis:
            raise ObservationValidationError(
                "No Analysis found for the ServiceRequest referenced by "
                "Observation.basedOn",
                expression=["Observation.basedOn"],
                code="not-found",
            )

        return analysis

    def validate_identity(self, analysis):
        """The Observation id must not be bound to a different Analysis

        `link_fhir_resource` binds an Observation id to the Analysis it first
        updated, and `get_object` resolves it back through the FHIR catalog.
        Two Analyses sharing one id would make that lookup ambiguous, and the
        notes the Observation carries would claim two different `Remarks`
        values under a single identity.
        """
        # `get_object` resolves a FHIR resource scoped to its mapped portal
        # type, so whatever is found here is an Analysis
        existing = fapi.get_object(self.resource, default=None)
        if existing and existing.UID() != analysis.UID():
            raise ObservationValidationError(
                "Observation.id is already linked to different Analysis",
                expression=["Observation.id"],
                code="conflict",
            )

    def validate_submittable(self, analysis, value):
        """The Analysis must still accept a submitted result

        Once an Analysis has already been submitted, "submit" is no longer
        a valid workflow transition and its result can no longer be overwritten
        through this endpoint.
        """
        analysis.setResult(value)
        if not wapi.is_transition_allowed(analysis, "submit"):
            state = api.get_review_status(analysis)
            raise ObservationValidationError(
                "Observation or DiagnosticReport is locked because it is "
                "state: {} and the value cannot be updated".format(state),
                expression=["Observation.value[x]"],
                code="conflict",
            )

    def validate_status(self):
        if self.resource.status != "final":
            raise ObservationValidationError(
                "Observation.status must be 'final'",
                expression=["Observation.status"],
            )

    def validate_code(self, analysis):
        """The code must match the ProtocolID-based code sent in the
        Analysis' SenaiteInstrumentServiceRequest
        """
        service = analysis.getAnalysisService()
        protocol_id = service.getProtocolID() if service else None

        system = fapi.get_system_code("AnalysisService")
        code = self.resource.code
        coding = first_by(code.coding, system=system) if code else None

        if not protocol_id or not coding or coding.code != protocol_id:
            raise ObservationValidationError(
                "Observation.code does not match the Analysis service",
                expression=["Observation.code"],
            )

    def validate_device(self, analysis):
        """The device must match the Instrument assigned to the Analysis
        """
        device = self.resource.device
        instrument = analysis.getInstrument()
        if (
            not device
            or not instrument
            or device.UID() != fapi.get_uid(instrument)
        ):
            raise ObservationValidationError(
                "Observation.device does not match the Instrument assigned "
                "to the Analysis",
                expression=["Observation.device"],
            )

    def get_value(self, analysis):
        if self.resource.valueQuantity:
            return self.get_quantity_value(analysis)

        if self.resource.valueString is not None:
            return self.resource.valueString

        raise ObservationValidationError(
            "Unsupported Observation.value[x]. Only valueQuantity and "
            "valueString are supported for now",
            expression=["Observation.value[x]"],
        )

    def get_quantity_value(self, analysis):
        value_quantity = self.resource.valueQuantity
        unit = analysis.getUnit()

        if (
            value_quantity.get("system") != UCUM_SYSTEM
            or value_quantity.get("code").lower() != unit.lower()
        ):

            raise ObservationValidationError(
                "Observation.valueQuantity unit does not match the "
                "Analysis' unit ({})".format(unit),
                expression=["Observation.valueQuantity"],
            )

        return value_quantity.get("value")
