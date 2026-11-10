# -*- coding: utf-8 -*-
import itertools

from senaite.fhir.config import CLIENT_EXTENSION_URL
from senaite.fhir.datatype.annotation import Annotation
from senaite.fhir.datatype.codeableconcept import CodeableConcept
from senaite.fhir.datatype.codeablereference import CodeableReference
from senaite.fhir.datatype.extension import Extension
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.datatype.orderdetail.parameter import OrderDetailParameter
from senaite.fhir.datatype.reference import Reference
from senaite.fhir.interfaces import IServiceRequestResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(IServiceRequestResource)
class ServiceRequestResource(FHIRResource):

    @property
    def identifier(self):
        """Identifiers assigned to this order instance by the orderer and/or
        the receiver and/or order fulfiller.
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.identifier
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def status(self):
        """The status of the order
        Value set: draft | active | on-hold | revoked | entered-in-error |
                   unknown
        https://hl7.org/fhir/R5/valueset-request-status.html
        """
        return self.get("status")

    @property
    def contained(self):
        """Contained, inline resources
        """
        # TODO Revisit ServiceRequest.contained
        return self.get("contained") or []

    @property
    def intent(self):
        """Whether the request is a proposal, plan, an original order or a
        reflex order.
        Value set: proposal | plan | directive | order +
        https://hl7.org/fhir/R5/valueset-request-intent.html
        """
        return self.get("intent")

    @property
    def category(self):
        """This will always be a Laboratory procedure
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.category
        """
        items = self.get("category")
        return [CodeableConcept(item) for item in items]

    @property
    def priority(self):
        """Indicates how quickly the ServiceRequest should be addressed with
        respect to other requests. If missing, this task should be performed
        with normal priority
        Value set: routine | urgent | asap | stat
        https://hl7.org/fhir/R5/valueset-request-priority.html
        """
        return self.get("priority")

    @property
    def doNotPerform(self):
        """True if service/procedure should not be performed
        If missing, the request is a positive request e.g. "do perform"
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.doNotPerform
        """
        return bool(self.get("doNotPerform", False))

    @property
    def code(self):
        """A code or reference that identifies a particular service (i.e.,
        procedure, diagnostic investigation, or panel of investigations) that
        have been requested.
        The codes SHOULD be taken from http://loinc.org
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.code
        """
        element = self.get("code")
        return CodeableReference(element) if element else None

    @property
    def orderDetail(self):
        """Individual test codes that make up the ordered panel.
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#ServiceRequest.orderDetail
        """
        data = self.get("orderDetail") or []
        # get all parameter dicts
        params = [item.get("parameter") for item in data]
        # flatten the list
        params = list(itertools.chain.from_iterable(params))
        # return OrderedDetailParameter instances
        return [OrderDetailParameter(param) for param in params if param]

    @property
    def subject(self):
        """Individual or Entity the service is ordered for
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.subject
        """
        element = self.get("subject")
        return Reference(element) if element else None

    @property
    def specimen(self):
        """Procedure Samples
        https://fhir.senaite.org/StructureDefinition-SenaiteServiceRequest-definitions.html#key_ServiceRequest.specimen
        """
        data = self.get("specimen") or []
        return [Reference(item) for item in data]

    @property
    def requester(self):
        """The individual who initiated the request and has responsibility for
        its activation.
        https://hl7.org/fhir/R5/servicerequest-definitions.html#ServiceRequest.requester
        """
        element = self.get("requester")
        return Reference(element) if element else None

    @property
    def note(self):
        """Any other notes and comments made about the service request. For
        example, internal billing notes.
        https://hl7.org/fhir/R5/servicerequest-definitions.html#ServiceRequest.note
        """
        items = self.get("note") or []
        return [Annotation(item) for item in items]

    @property
    def extension(self):
        items = self.get("extension") or []
        return [Extension(item) for item in items]

    @property
    def client(self):
        """The submitting client organisation
        A direct reference to the Organisation that is placing this laboratory
        request. In SENAITE this maps to the Client registered in the LIMS. If
        the client is not yet known, it will be created on receipt.
        """
        for ext in self.extension:
            if ext.url == CLIENT_EXTENSION_URL:
                ref = ext.get("valueReference")
                if ref:
                    return Reference(ref)
        return None
