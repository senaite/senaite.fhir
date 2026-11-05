# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.catalog import CONTACT_CATALOG
from senaite.fhir.converter.contact import ResourceToContact
from senaite.fhir.interfaces import IContentFinder
from senaite.fhir.interfaces import IPractitionerResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IPractitionerResource)
@implementer(IContentFinder)
class ContactFinder(object):
    """Adapter in charge of searching the counterpart Contact object of a FHIR
    Practitioner resource
    """

    def __init__(self, resource):
        self.resource = resource

    def find(self):
        """Looks for the resource's counterpart Contact object
        """
        # search by the external identifier of the Practitioner
        identifier = self.resource.get_external_id()
        if not identifier or not identifier.value:
            return None

        # the contact must belong to the client (Organization) of the bundle
        client = ResourceToContact(self.resource).get_parent()
        if not client:
            return None

        query = {
            "portal_type": "Contact",
            "fhir_external_id": identifier.value,
            "path": {
                "query": api.get_path(client),
                "level": 0,
            },
        }
        brains = api.search(query, CONTACT_CATALOG)
        if len(brains) == 1:
            return api.get_object(brains[0])

        return None
