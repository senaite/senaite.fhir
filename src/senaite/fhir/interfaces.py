# -*- coding: utf-8 -*-
from senaite.core.interfaces import ISenaiteCatalogObject
from senaite.patient import ISenaitePatientLayer
from zope.interface import Interface


class ISenaiteFHIRLayer(ISenaitePatientLayer):
    """Zope 3 browser Layer interface specific for senaite.fhir
    This interface is referred in profiles/default/browserlayer.xml.
    All views and viewlets register against this layer will appear in the site
    only when the add-on installer has been run.
    """


class IFHIRResource(Interface):
    """Marker interface for a FHIR's resource
    """


class IBundleResource(IFHIRResource):
    """Marker interface for a FHIR's Bundle resource
    https://hl7.org/fhir/R5/bundle.html
    """


class IBundleResponseResource(IBundleResource):
    """Marker interface for FHIR's Senaite Bundle Response
    https://fhir.senaite.org/StructureDefinition-SenaiteBundleResponse.html
    """


class IServiceRequestBundleResource(IBundleResource):
    """Marker interface for FHIR's Senaite Service Request Bundle
    https://fhir.senaite.org/StructureDefinition-SenaiteRequestBundle.html
    """


class IOrganizationResource(IFHIRResource):
    """Marker interface for FHIR's Organization resource
    https://fhir.senaite.org/StructureDefinition-SenaiteOrganization.html
    """


class IClientResource(IOrganizationResource):
    """Marker interface for FHIR's Client artifact resource
    """
    # TODO This is not FHIR-compliant


class IPractitionerResource(IFHIRResource):
    """Marker interface for a FHIR's Practitioner resource
    https://fhir.senaite.org/StructureDefinition-SenaitePractitioner.html
    """


class IContactResource(IPractitionerResource):
    """Marker interface for a FHIR's Contact artifact resource
    """
    # TODO This is not FHIR-compliant


class IPatientResource(IFHIRResource):
    """Marker interface for a FHIR's Patient resource
    https://fhir.senaite.org/StructureDefinition-SenaitePatient.html
    """


class IServiceRequestResource(IFHIRResource):
    """Marker interface for a FHIR's ServiceRequest resource
    https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest.html
    """


class ISpecimenResource(IFHIRResource):
    """Marker interface for a FHIR's Specimen resource
    https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest.html
    """


class IDiagnosticReportResource(IFHIRResource):
    """Marker interface for a FHIR's DiagnosticReport resource
    https://fhir.senaite.org/StructureDefinition-SenaiteDiagnosticReport.html
    """


class IObservationResource(IFHIRResource):
    """Marker interface for a FHIR's Observation resource
    https://fhir.senaite.org/StructureDefinition-SenaiteObservation.html
    """


class IDeviceResource(IFHIRResource):
    """Marker interface for a FHIR's Device resource
    https://fhir.senaite.org/StructureDefinition-SenaiteDevice.html
    """


class IResultsBundleResource(IFHIRResource):
    """Marker interface for a FHIR searchset Bundle returned by the
    DiagnosticReport polling endpoint.
    https://fhir.senaite.org/StructureDefinition-SenaiteResultsBundle.html
    """


class IContentToFHIR(Interface):
    """Converter of AT/DX content to IFHIRResource
    """

    def to_fhir_resource(self):
        """Returns the conversion of the context
        """


class IContentActionToFHIR(Interface):
    """Converter of AT/DX content action/transition to IFHIRResource
    """

    def to_fhir_resource(self):
        """Returns the conversion of the context for a FHIR action
        """


class IFHIRToContent(Interface):
    """Converter of IFHIRResource to AT/DX info dict
    """

    def validate(self):
        """Raises a ResourceValidationError if the resource violates any of
        the validation rules. Called before the counterpart object of the
        resource is searched, so the rules apply whether the object is
        created, updated or matched
        """

    def to_content_dict(self):
        """Returns a dict suitable for the creation or update of a content
        type object
        :rtype: dict
        """


class IContentFinder(Interface):
    """Adapter in charge of searching the suitable content for the given
    resource
    """

    def find(self):
        """Returns the object that matches with the given resource or None
        """


class IFHIRContent(Interface):
    """Marker interface for objects that has a linked FHIR Resource
    """


class IFHIRCatalog(ISenaiteCatalogObject):
    """Marker interface for Senaite FHIR catalog
    """
