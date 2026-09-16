# -*- coding: utf-8 -*-

import json
from plone.indexer import indexer
from Products.CMFCore.interfaces import IContentish
from senaite.core.interfaces import IContact
from senaite.core.interfaces.catalog import IContactCatalog
from senaite.fhir.behaviors.contact import getExternalID
from senaite.fhir.interfaces import IFHIRCatalog
from senaite.fhir import api as fapi


# TODO Replace IContentish by IFHIRContentish (not IFHIRContent)
@indexer(IContentish, IFHIRCatalog)
def fhir_uids(obj):
    """Return a list with the counterpart FHIR uids of the given object
    """
    # get the uids grouped by resource type
    uids = fapi.get_fhir_uids(obj)
    return uids.values()


# TODO Replace IContentish by IFHIRContentish (not IFHIRContent)
@indexer(IContentish, IFHIRCatalog)
def fhir_resource_types(obj):
    """Returns a json dict wih resourceTypes as keys and uids as values
    """
    uids = fapi.get_fhir_uids(obj) or {}
    return json.dumps(uids)


@indexer(IContact, IContactCatalog)
def contact_external_id(instance):
    """Indexes the external id assigned by the FHIR API consumer, so
    Practitioner resources can be matched to an existing Contact by it
    """
    return getExternalID(instance) or ""
