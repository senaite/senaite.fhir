# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.catalog import CLIENT_CATALOG
from senaite.fhir.interfaces import IContentFinder
from senaite.fhir.interfaces import IOrganizationResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IOrganizationResource)
@implementer(IContentFinder)
class ClientFinder(object):
    """Adapter in charge of searching the counterpart Client object of a FHIR
    Organization resource
    """

    def __init__(self, resource):
        self.resource = resource

    def find(self):
        """Looks for the resource's counterpart Client object
        """
        # search by client ID, the external identifier of the Organization
        identifier = self.resource.get_external_id()
        if identifier and identifier.value:
            query = dict(portal_type="Client", getClientID=identifier.value)
            brains = api.search(query, CLIENT_CATALOG)
            if len(brains) == 1:
                return api.get_object(brains[0])

        # fallback to search by title (ignorecase)
        name = self.resource.name
        query = dict(portal_type="Client", sortable_title=name)
        brains = api.search(query, CLIENT_CATALOG)
        if len(brains) == 1:
            return api.get_object(brains[0])

        return None
