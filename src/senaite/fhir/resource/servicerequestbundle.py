# -*- coding: utf-8 -*-

from senaite.fhir.interfaces import IServiceRequestBundleResource
from senaite.fhir.resource.bundle import Bundle
from senaite.fhir.resource.operationoutcome import OperationOutcome
from zope.interface import implementer


@implementer(IServiceRequestBundleResource)
class ServiceRequestBundleResource(Bundle):
    """A transaction Bundle used to submit a laboratory service request.
    https://fhir.senaite.org/StructureDefinition-SenaiteRequestBundle.html
    """

    __fixed_values = (
        ("type", "transaction")
    )

    @property
    def id(self):
        """Returns the logical id of the artifact
        https://fhir.senaite.org/StructureDefinition-SenaiteRequestBundle-definitions.html#key_Bundle.id
        """
        return self["id"]

    @property
    def implicitRules(self):
        """A set of rules under which this content was created
        https://fhir.senaite.org/StructureDefinition-SenaiteBundleResponse-definitions.html#key_Bundle.implicitRules
        """
        return self.get("implicitRules") or []

    @property
    def type(self):
        """Indicates the purpose of this bundle, how it is intended to be used.
        Fixed Value: transaction
                     https://hl7.org/fhir/valueset-bundle-type.html
        https://fhir.senaite.org/StructureDefinition-SenaiteBundleResponse-definitions.html#key_Bundle.type
        """
        return self["type"]

    @property
    def issues(self):
        """Captures issues and warnings that relate to the construction of the
        Bundle and the content within it.
        https://fhir.senaite.org/StructureDefinition-SenaiteBundleResponse-definitions.html#key_Bundle.issues
        """
        records = self.get("issues") or []
        return [OperationOutcome(record) for record in records]

    @property
    def entry(self):
        """An entry in a bundle resource - will either contain a resource or
        information about a resource (transactions and history only).
        https://fhir.senaite.org/StructureDefinition-SenaiteBundleResponse-definitions.html#key_Bundle.entry
        """
        resources = super(ServiceRequestBundleResource, self).entry
        # Keep the request position while sorting for dependency processing
        for index, resource in enumerate(resources):
            resource["entry_index"] = index

        # TODO Sorting of entries inside a ServiceRequestBundle is not neat
        # Sort only for processing, never for the response order.
        order = ["Organization", "Practitioner", "Specimen", "Patient",
                 "ServiceRequest"]
        return sorted(
            resources,
            key=lambda en: order.index(en.resourceType)
            if en.resourceType in order else len(order)
        )
