# -*- coding: utf-8 -*-
from bika.lims.interfaces import IAnalysisRequest
from senaite.fhir.config import DEFAULT_REPORT_PROFILE_CODE
from senaite.fhir.config import SECONDARY_RESOURCES_KEY
from senaite.fhir.config import SPECIMEN_STATUSES
from senaite.fhir.converter import first_by
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.converter import to_fhir_identifier as to_fhir_id
from senaite.fhir.converter import to_naming_system_url
from senaite.fhir.converter.person import ResourceToPerson
from senaite.fhir.exceptions import ServiceRequestValidationError
from senaite.fhir.interfaces import IContentActionToFHIR
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IServiceRequestResource
from senaite.fhir.resource.servicerequestrevoked import (
    ServiceRequestRevokedResource)
from senaite.fhir.resource.specimen import SpecimenResource
from zope.component import adapter
from zope.interface import implementer
from bika.lims import api
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.catalog import CONTACT_CATALOG
from senaite.fhir import api as fapi
from plone.memoize.instance import memoize


# Priorities mapping
PRIORITIES = (
    ("stat", "1"),
    ("asap", "2"),
    ("urgent", "3"),
    ("routine", "5"),
)


@adapter(IAnalysisRequest)
@implementer(IContentActionToFHIR)
class AnalysisRequestRevokedToResource(object):

    def __init__(self, context):
        self.context = context

    def to_fhir_resource(self):
        data = {}
        if fapi.is_fhir_content(self.context):
            data = fapi.get_fhir_storage(self.context).get("data")

        modified = api.get_modification_date(self.context)
        modified = to_fhir_datetime(modified)
        profile_url = to_fhir_profile_url("SenaiteServiceRequestRevoked")
        data["resourceType"] = "ServiceRequest"
        data["id"] = str(fapi.get_uuid(self.context))
        data["status"] = "revoked"
        data["meta"] = {
            "profile": [profile_url],
            "versionId": api.get_version(self.context),
            "lastUpdated": modified,
        }
        # get the selected predefined reasons
        reasons = list(self.context.getSelectedRejectionReasons())
        # append custom/other reasons
        reasons.append(self.context.getOtherRejectionReasons())
        # remove empties/Nones
        reasons = list(filter(None, reasons))
        reasons = "; ".join(reasons)
        if reasons:
            data["note"] = [{"text": reasons}]

        return ServiceRequestRevokedResource(data)


@adapter(IAnalysisRequest)
@implementer(IContentToFHIR)
class AnalysisRequestToSpecimen(object):
    """Converts a native SENAITE AnalysisRequest to a FHIR Specimen resource
    """

    def __init__(self, context):
        self.context = context

    def to_fhir_resource(self):

        ar = self.context
        sample_type = ar.getSampleType()
        if not sample_type:
            return None

        specimen_id = str(fapi.get_uuid(api.get_uid(ar)))

        system = fapi.get_system_code("Specimen")
        data = {
            "resourceType": "Specimen",
            "id": specimen_id,
            "status": self.get_status(),
            "type": {
                "coding": [{
                    "system": system,
                    "display": sample_type.Title(),
                }]
            },
        }

        collection = {}

        date_sampled = ar.getDateSampled()
        if date_sampled:
            collection["collectedDateTime"] = to_fhir_datetime(date_sampled)
            # TODO: map getSampler() to collection["collector"]

        sample_point = ar.getSamplePoint()
        if sample_point:
            sp_system = fapi.get_system_code("SamplePoint")
            collection["bodySite"] = {
                "concept": {
                    "coding": [{
                        "system": sp_system,
                        "display": sample_point.Title(),
                    }]
                }
            }

        if collection:
            data["collection"] = collection

        identifiers = [
            to_fhir_id("sample-id", ar.getId(), use="usual"),
        ]
        client_sample_id = ar.getClientSampleID()
        if client_sample_id:
            identifiers.append(
                to_fhir_id(
                    "client-sample-id",
                    client_sample_id,
                    use="secondary",
                )
            )
        data["identifier"] = identifiers

        return SpecimenResource(data)

    def get_status(self):
        """Returns the FHIR Specimen status that maps to the current status
        of the Sample, as defined in `SPECIMEN_STATUSES`

        Falls back to the default status (the one keyed as `None`) when the
        status of the Sample has no explicit mapping

        :returns: available | unavailable | unsatisfactory | entered-in-error
        """
        status = api.get_review_status(self.context)
        mapping = dict(SPECIMEN_STATUSES)
        fhir_status = mapping.get(status)
        if fhir_status:
            return fhir_status
        # return default (None as the key)
        return mapping.get(None)


@adapter(IServiceRequestResource)
@implementer(IFHIRToContent)
class ResourceToAnalysisRequest(object):

    def __init__(self, resource):
        self.resource = resource

    def validate(self):
        """Runs all the validators here. Can be extended
        """
        self.validate_identifiers()

    def _reject_object_identifier(self, obj, obj_name):
        """Reject resource that mandates internal identifier"""
        object_id = obj.get_object_id()
        if object_id:
            msg = (
                "Cannot specify usual identifier externally in incoming "
                "{}:{}"
            ).format(obj_name, object_id.value)
            raise ServiceRequestValidationError(
                msg,
                expression=["{}.identifier".format(obj_name)],
                code="invalid",
            )

    def _validate_external_identifier(self, obj, obj_name,
                                      valid_system=None):
        """Reject resource with invalid external identifier"""
        external_id = obj.get_external_id()
        if external_id:
            if valid_system is None:
                msg = (
                    "Cannot specify external identifier in "
                    "{}:{}"
                ).format(obj_name, external_id.value)
                raise ServiceRequestValidationError(
                    msg,
                    expression=["{}.identifier".format(obj_name)],
                    code="invalid",
                )
            if external_id.system != valid_system:
                msg = (
                    "Unsupported identifier system in {}: {}"
                ).format(obj_name, external_id.system)
                raise ServiceRequestValidationError(
                    msg,
                    expression=["{}.identifier".format(obj_name)],
                    code="invalid",
                )

    def validate_identifiers(self):
        """Validates identifiers"""
        self._reject_object_identifier(self.resource, "ServiceRequest")
        self._validate_external_identifier(self.resource, "ServiceRequest")

        specimen = self.get_specimen()
        if specimen:
            self._reject_object_identifier(specimen, "Specimen")
            self._validate_external_identifier(
                specimen,
                "Specimen",
                to_naming_system_url("client-sample-id"),
            )

    def to_content_dict(self):
        # TODO We don't validate category + SNOMED code (is necessary?)
        self.validate()

        sample_type = self.get_sample_type()
        client = self.get_client()
        client_sample_id = self.get_client_sample_id()
        contact = self.get_requester()
        specs = self.get_specifications()
        sample_point = self.get_sample_point()
        date_sampled = self.get_date_sampled()
        profile = self.get_profile()
        services = self.get_services()
        priority = self.get_priority()

        data = {
            "portal_type": "AnalysisRequest",
            "parent_path": api.get_path(client),
            "Client": client,
            "Contact": contact,
            "SampleType": sample_type,
            "SamplePoint": sample_point,
            "DateSampled": date_sampled,
            "Profiles": [api.get_uid(profile)] if profile else [],
            "Priority": priority,
            # "Sampler": collector,
            # "Remarks": remarks,
            "Specification": specs,
            "Analyses": services,
            "ClientSampleID": client_sample_id,
        }

        # update with patient information
        patient_info = self.get_patient_info()
        data.update(patient_info)

        # link the Specimen to the sample as a secondary resource, as there
        # is no counterpart content type in senaite for "Specimen"
        data[SECONDARY_RESOURCES_KEY] = [self.get_specimen()]

        return data

    def get_reference(self, key):
        """Returns the single Reference the resource holds under the given key

        The references resolved through this helper are all 1..1 in the SENAITE
        profiles, so a missing reference and a repeated one are both violations
        of the profile rather than internal errors, and are reported back as an
        OperationOutcome.

        :param key: name of the reference element, e.g. ``"specimen"``
        :returns: the Reference data type
        :raises ServiceRequestValidationError: if missing or repeated
        """
        expression = "%s.%s" % (self.resource.resourceType, key)

        ref = getattr(self.resource, key, None)
        if not ref:
            raise ServiceRequestValidationError(
                "%s is required" % expression,
                expression=[expression],
                code="required",
            )

        if api.is_list(ref):
            if len(ref) > 1:
                raise ServiceRequestValidationError(
                    "%s accepts a single reference only" % expression,
                    expression=[expression],
                    code="structure",
                )
            return ref[0]

        return ref

    def get_reference_obj(self, key, **kwargs):
        ref = self.get_reference(key)
        uid = ref.UID()
        return api.get_object_by_uid(uid, default=None)

    def get_bundle_sibling(self, ref):
        bundle = self.resource.get("_bundle")
        if not bundle:
            return None
        return bundle.first_entry("id", str(ref.UUID()))

    @memoize
    def get_specimen(self):
        """Returns the Specimen resource of this ServiceRequest

        ``ServiceRequest.specimen`` is 1..1 in the SenaiteServiceRequest
        profile, so ``get_reference`` rejects both a missing and a repeated
        reference:
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest.html
        """
        ref = self.get_reference("specimen")
        return self.get_bundle_sibling(ref)

    @memoize
    def get_sample_type(self):
        """Returns the SampleType object associated to this ServiceRequest
        """
        sibling = self.get_specimen()
        obj = fapi.find_object_for(sibling, default=None)
        if obj:
            return obj
        raise ServiceRequestValidationError(
            "Specimen has no matching SampleType in SENAITE",
            expression=["Specimen.type"],
            code="not-found",
        )

    @memoize
    def get_requester(self):
        """Returns the contact who requested the sample
        """
        # Try with the reference UID first
        ref = self.get_reference("requester")
        uid = ref.UID()
        obj = fapi.get_object(uid, default=None)
        if obj:
            return obj

        # get the sibling from the bundle, if any
        sibling = self.get_bundle_sibling(ref)
        if not sibling:
            raise ValueError("%r: No Contact for %s" % (self.resource, uid))

        # search the counterpart contact of the practitioner, by its external
        # id (use=secondary) within the client (see ContactFinder)
        contact = fapi.find_object_for(sibling, default=None)
        if contact:
            return contact

        # fallback to search by fullname, within the client the sample is
        # registered for
        client = self.get_client()
        fullname = self.get_practitioner_fullname(sibling)
        if fullname:
            contact = self.search_contact(client, getFullname=fullname)
            if contact:
                return contact

        raise ValueError("%r: No Contact for %s" % (self.resource, uid))

    def get_practitioner_fullname(self, practitioner):
        """Returns the fullname of the practitioner, built the same way the
        fullname of a Contact is (see `Person.getFullname`), or None
        """
        if not practitioner.name:
            return None
        person = ResourceToPerson(practitioner)
        names = [
            person.get_firstname(),
            person.get_middlename(),
            person.get_lastname(),
        ]
        return " ".join(filter(None, names))

    def search_contact(self, client, **query):
        """Returns the contact from the given client that matches the query,
        or None if no contact, or more than one, matches
        """
        query.update({
            "portal_type": "Contact",
            "path": {
                "query": api.get_path(client),
                "level": 0,
            },
        })
        brains = api.search(query, CONTACT_CATALOG)
        if len(brains) == 1:
            return api.get_object(brains[0])
        return None

    @memoize
    def get_patient(self):
        """Returns the patient assigned to this ServiceRequest
        """
        ref = self.resource.subject
        sibling = self.get_bundle_sibling(ref)
        obj = fapi.find_object_for(sibling, default=None)
        if obj:
            return obj
        raise ValueError("%r: No Patient for %r" % (self.resource, sibling))

    @memoize
    def get_client(self):
        """Returns the client the sample where the sample has to be created
        """
        ref = self.resource.client
        sibling = self.get_bundle_sibling(ref)
        obj = fapi.find_object_for(sibling, default=None)
        if obj:
            return obj
        raise ValueError("%r: No Client for %r" % (self.resource, sibling))

    @memoize
    def get_client_sample_id(self):
        """Returns the client sample id from Specimen
        """
        specimen = self.get_specimen()
        if not specimen:
            return None
        external = specimen.get_external_id()
        return external.value if external else None

    @memoize
    def get_specifications(self):
        """Returns the analysis specification for this sample
        """
        sample_type = self.get_sample_type()
        if not sample_type:
            return None

        query = {
            "portal_type": "AnalysisSpec",
            "sampletype_uid": api.get_uid(sample_type),
            "is_active": True,
        }
        # TODO What to do when more than one spec per sample type?
        brains = api.search(query, SETUP_CATALOG)
        if len(brains) == 1:
            return api.get_object(brains[0])
        return None

    @memoize
    def get_date_sampled(self):
        """Returns the date when the specimen was collected
        """
        specimen = self.get_specimen()
        return specimen.collectedDateTime

    @memoize
    def get_sample_point(self):
        """Returns the sample point from where this specimen was collected
        """
        specimen = self.get_specimen()
        if not specimen:
            return None

        # get the bodySite coding element
        if not specimen.bodySite:
            return None

        system = fapi.get_system_code("SamplePoint")
        site = first_by(specimen.bodySite.coding, system=system)
        if not site:
            return None

        # TODO Consider to add a search function in fapi and use adapters
        external_id = site.code
        if external_id:
            # TODO New field External ID in SamplePoint to search by
            query = dict(portal_type="SamplePoint", getExternalID=site.code)
            # brains = api.search(query, SETUP_CATALOG)
            brains = []
            if len(brains) == 1:
                return api.get_object(brains[0])

        # fallback to search by title
        display = site.display
        if display:
            # use sortable_title for an ignore case search
            title = display.lower()
            query = dict(portal_type="SamplePoint", sortable_title=title)
            brains = api.search(query, SETUP_CATALOG)
            if len(brains) == 1:
                return api.get_object(brains[0])

        return None

    def is_default_panel(self):
        """Returns True when the FHIR resource carries the default panel code
        """
        # the panel is always stored in code.concept
        code = getattr(self.resource, "code", None)
        panel = code.concept if code else None
        if not panel:
            return False

        # extract the first coding for the expected system
        system = fapi.get_system_code("AnalysisProfile")
        coding = first_by(panel.coding, system=system)
        if not coding:
            return False

        # find a match with default profile code(s)
        default_codings = DEFAULT_REPORT_PROFILE_CODE.get("coding")
        default_codes = [default.get("code") for default in default_codings]
        return coding.code in default_codes

    @memoize
    def get_services(self):
        """Returns the list of services to assign to this sample
        """
        services = []
        system = fapi.get_system_code("AnalysisService")
        for param in self.resource.orderDetail:
            # get the coding info
            concept = param.valueCodeableConcept
            coding = first_by(concept.coding, system=system)
            # search by code
            service = self.get_service(coding.code)
            if service:
                services.append(service)

        # if default panel set, orderDetail must have at least one test
        if self.is_default_panel():
            if not services:
                default = DEFAULT_REPORT_PROFILE_CODE.get("coding")[0]
                msg = (
                    "orderDetail must be present and contain at least one "
                    "test code when ServiceRequest.code is the default "
                    "panel ({}). There is no panel definition to fall "
                    "back on."
                ).format(default.get("code"))

                raise ServiceRequestValidationError(
                    message=msg,
                    expression=["ServiceRequest.orderDetail"],
                )
            # No panel-membership validation for the default code
            return services

        # if orderDetail is absent, defer to the panel entirely
        if not services:
            return []

        # orderDetail is present, every test defined in the panel must appear
        profile = self.get_profile()
        if profile:
            missing = set(profile.getServices()) - set(services)
            if missing:
                # build the message
                tests = ["%s %s" % (
                    api.safe_unicode(test.getProtocolID()),
                    api.safe_unicode(api.get_title(test))
                ) for test in missing]
                msg = (
                    "orderDetail is a partial subset of panel "
                    "{panel_key} ({panel_name}). Missing tests: "
                    "[{tests}]. Either omit orderDetail to use the "
                    "full panel definition, or include all panel tests."
                ).format(
                    panel_key=api.safe_unicode(profile.getProfileKey()),
                    panel_name=api.safe_unicode(api.get_title(profile)),
                    tests=", ".join(tests))

                raise ServiceRequestValidationError(
                    message=msg,
                    expression=["ServiceRequest.orderDetail"],
                )

        return services

    def get_service(self, code):
        # search by keyword
        query = dict(portal_type="AnalysisService", getKeyword=code)
        brains = api.search(query, SETUP_CATALOG)
        if len(brains) == 1:
            return api.get_object(brains[0])

        # TODO New field External ID in AnalysisService to search by
        matches = []
        query = dict(portal_type="AnalysisService")
        brains = api.search(query, SETUP_CATALOG)
        services = [api.get_object(brain) for brain in brains]
        for obj in services:
            if obj.getProtocolID() == code:
                matches.append(obj)
        if len(matches) == 1:
            return matches[0]
        return None

    @memoize
    def get_profile(self):
        """Returns an analysis profile, or None when the ServiceRequest does
        not reference a panel we can resolve. The panel (``code.concept``) and
        its codings/text are all optional, so each is guarded against None.
        """
        code = getattr(self.resource, "code", None)
        panel = code.concept if code else None
        if not panel:
            return None

        system = fapi.get_system_code("AnalysisProfile")
        coding = None
        if panel.coding:
            coding = first_by(panel.coding, system=system)

        # search by profile_key
        if coding and coding.code:
            query = dict(portal_type="AnalysisProfile",
                         profile_key=coding.code)
            brains = api.search(query, SETUP_CATALOG)
            if len(brains) == 1:
                return api.get_object(brains[0])

        # search by title (from concept.coding.display)
        display = coding.display if coding else None
        if display:
            # use sortable_title for an ignore case search
            query = dict(portal_type="AnalysisProfile",
                         sortable_title=display.lower())
            brains = api.search(query, SETUP_CATALOG)
            if len(brains) == 1:
                return api.get_object(brains[0])

        # search by title (from concept.text)
        if panel.text:
            query = dict(portal_type="AnalysisProfile",
                         sortable_title=panel.text.lower())
            brains = api.search(query, SETUP_CATALOG)
            if len(brains) == 1:
                return api.get_object(brains[0])

        return None

    def get_priority(self):
        """Returns the priority
        """
        #  routine | urgent | asap | stat
        priority = self.resource.priority
        return dict(PRIORITIES).get(priority, "5")

    def get_patient_info(self):
        patient = self.get_patient()
        patient_mrn = patient.getMRN()
        patient_dob = patient.getBirthdate()
        patient_sex = patient.getSex()
        return {
            "PatientFullName": {
                "firstname": patient.getFirstname(),
                "middlename": patient.getMiddlename(),
                "lastname": patient.getLastname(),
            },
            "DateOfBirth": patient_dob,
            "Sex": patient_sex,
            "MedicalRecordNumber": {"value": patient_mrn}
        }
