# -*- coding: utf-8 -*-

from senaite.fhir.api import to_fhir_resource
from senaite.fhir.converter import get_by_key
from senaite.fhir.datatype.identifier import Identifier
from senaite.fhir.interfaces import IBundleResource
from senaite.fhir.resource import FHIRResource
from zope.interface import implementer


def get_entry_id(entry):
    """Returns the id of the resource of the given raw bundle entry. A POSTed
    entry carries no `resource.id`, so it is the placeholder of the entry's
    `fullUrl` (e.g. `urn:uuid:<id>`), which the references between the
    entries of the same bundle point to

    :param entry: a raw bundle entry dict
    :returns: the id of the entry's resource, or None
    """
    resource = entry.get("resource") or {}
    if resource.get("id"):
        return resource["id"]
    full_url = entry.get("fullUrl") or ""
    return full_url.split("/")[-1].split(":")[-1] or None


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
            raw_resource = entry.get("resource")

            # TODO Only interested on resources resolving to our FHIRResource
            resource = to_fhir_resource(raw_resource, default=None)
            if resource:
                # the resource of a POSTed entry carries no id: take it from
                # the entry's fullUrl, so it can be referenced and looked up
                entry_id = get_entry_id(entry)
                if not resource.id and entry_id:
                    resource["id"] = entry_id
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

    def get_entry(self, resource):
        """Returns the raw entry (as submitted, keeping `fullUrl` and
        `request`) of the given (already-extracted) FHIRResource, or None.
        Matched by the entry's id, as the raw resource of a POSTed entry
        carries none (see `get_entry_id`)
        """
        for entry in self.get("entry") or []:
            if get_entry_id(entry) == resource.id:
                return entry
        return None

    def get_request(self, resource):
        """Returns the raw `request` dict (method/url/ifNoneExist/...)
        declared on the given (already-extracted) FHIRResource's bundle
        entry, or {} when the entry carries none.
        https://hl7.org/fhir/R5/bundle-definitions.html#Bundle.entry.request
        """
        entry = self.get_entry(resource) or {}
        return entry.get("request") or {}
