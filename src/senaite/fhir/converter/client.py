# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.fhir import api as fapi
from senaite.fhir.config import ORGANIZATION_EXTERNAL_ID_SYSTEM
from senaite.fhir.converter.organisation import ResourceToOrganisation
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IOrganizationResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IOrganizationResource)
@implementer(IFHIRToContent)
class ResourceToClient(ResourceToOrganisation):

    def to_content_dict(self):
        # get the basics from the org
        data = super(ResourceToClient, self).to_content_dict()

        # Portal type and Container path
        data["portal_type"] = "Client"
        data["parent_path"] = self.get_parent_path()

        # Client ID
        client_id = self.get_client_id()
        if client_id:
            data["ClientID"] = api.safe_unicode(client_id)

        return data

    def get_parent_path(self):
        portal = api.get_portal()
        return "%s/clients" % api.get_path(portal)

    def get_client_id(self):
        identifier = fapi.get_external_identifier(
            self.resource, ORGANIZATION_EXTERNAL_ID_SYSTEM)
        return identifier.value if identifier else None
