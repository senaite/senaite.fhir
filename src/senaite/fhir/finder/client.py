# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.catalog import CLIENT_CATALOG
from senaite.fhir.exceptions import ResourceValidationError
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
        """Looks for the resource's counterpart Client object by the external
        identifier of the Organization, the ClientID. Returns None when the
        Organization carries none, or when no Client has it

        The name is not a key: two Clients can share it, and a renamed one
        would no longer match

        :raises ResourceValidationError: when more than one Client has the
            ClientID, as the Organization cannot be resolved without guessing
        """
        identifier = self.resource.get_external_id()
        if not identifier or not identifier.value:
            return None

        query = dict(portal_type="Client", getClientID=identifier.value)
        brains = api.search(query, CLIENT_CATALOG)
        if len(brains) > 1:
            ids = ", ".join(sorted([api.get_id(brain) for brain in brains]))
            raise ResourceValidationError(
                "Multiple Clients with ClientID {}: {}"
                .format(identifier.value, ids),
                expression=["Organization.identifier"],
                code="multiple-matches")

        return api.get_object(brains[0]) if brains else None
