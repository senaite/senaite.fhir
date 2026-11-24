# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.fhir import logger
from senaite.fhir.setuphandlers import setup_behaviors
from senaite.fhir.setuphandlers import setup_catalogs


def setup_contact_behavior(tool):
    """Add the behavior that extends Contact with the FHIR external ID,
    along with the catalog index to search contacts by it
    """
    logger.info("Setup Contact behavior ...")
    portal = api.get_portal()
    setup_behaviors(portal)
    setup_catalogs(portal)
    logger.info("Setup Contact behavior [DONE]")


def add_sample_group_index(tool):
    """Install the Sample Client Order Number index used by requisitions
    """
    logger.info("Adding the FHIR sample group index ...")
    setup_catalogs(api.get_portal())
    logger.info("Adding the FHIR sample group index [DONE]")
