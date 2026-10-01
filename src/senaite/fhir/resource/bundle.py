# -*- coding: utf-8 -*-

from senaite.fhir.api import to_fhir_resource
from senaite.fhir.converter import get_by_key
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import IBundleResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


@implementer(IBundleResource)
class Bundle(FHIRResource):
    """A container for a collection of resources.
    https://hl7.org/fhir/R5/bundle-definitions.html#Bundle
    """

    __cardinality = (
        ("identifier", "0..1"),
        ("type", "1"),
        ("timestamp", "0..1"),
        ("total", "0..1"),
        ("link", "0..*"),
        ("entry", "0..*"),
        ("signature", "0..1"),
        ("issues", "0..1"),
    )

    @property
    def identifier(self):
        """A persistent identifier for the bundle that won't change as a bundle
        is copied from server to server.
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.identifier
        """
        data = self.get("identifier") or []
        return [Identifier(item) for item in data]

    @property
    def type(self):
        """Indicates the purpose of this bundle, how it is intended to be used.
        Value set: document | message | transaction | transaction-response |
                   batch | batch-response | history | searchset | collection |
                   subscription-notification
                   https://hl7.org/fhir/R5/valueset-bundle-type.html
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.type
        """
        return self["type"]

    @property
    def issues(self):
        """Captures issues and warnings that relate to the construction of the
        Bundle and the content within it.
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.issues
        """
        records = self.get("issues") or []
        return [FHIRResource(record) for record in records]

    @property
    def entry(self):
        """An entry in a bundle resource - will either contain a resource or
        information about a resource (transactions and history only).
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.entry
        """
        entries = self.get("entry") or []
        resources = []
        for entry in entries:
            # TODO fullUrl (e.g. urn:uuid:ddaf107d-a44d-4b7b-966b-65d82de495cc)
            # full_url = entry.get("fullUrl")
            raw_resource = entry.get("resource")

            # TODO Only interested on resources resolving to our FHIRResource
            resource = to_fhir_resource(raw_resource, default=None)
            if resource:
                # keep track of the bundle the resource belongs to, so that
                # the references to its siblings can be resolved
                resource["_bundle"] = self
                resources.append(resource)
        # return the FHIR resources
        return resources

    def first_entry(self, key, value):
        """Search the first entry whose value for the given key matches with
        the value passed-in
        """
        return get_by_key(self.entry, key, value)

    def first_raw_entry(self, key, value):
        """Search the first RAW JSON entry (as submitted, keeping `fullUrl`
        and `request`) whose embedded resource has the given key/value.

        Unlike `entry`/`first_entry`, which rebuild each entry by converting
        `entry["resource"]` through `to_fhir_resource`, this matches directly
        against the raw `entry["resource"]` mapping, keeping entry-level data
        such as `request.ifNoneExist` reachable.
        """
        for entry in self.get("entry") or []:
            resource = entry.get("resource") or {}
            if resource.get(key) == value:
                return entry
        return None

    def get_request(self, resource):
        """Returns the raw `request` dict (method/url/ifNoneExist/...)
        declared on the given (already-extracted) FHIRResource's bundle
        entry, or {} when the entry carries none.
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.entry.request
        """
        entry = self.first_raw_entry("id", resource.id)
        if not entry:
            return {}
        return entry.get("request") or {}
