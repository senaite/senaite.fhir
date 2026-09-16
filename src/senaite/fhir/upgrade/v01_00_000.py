# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.fhir import logger
from senaite.fhir.setuphandlers import setup_behaviors
from senaite.fhir.setuphandlers import setup_catalogs


def setup_contact_behavior(tool):
    """Add patient behavior
    """
    logger.info("Setup Contact behavior ...")
    portal = api.get_portal()
    setup_behaviors(portal)
    setup_catalogs(portal)
    logger.info("Setup Contact behavior [DONE]")
