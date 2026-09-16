# -*- coding: utf-8 -*-

from AccessControl import ClassSecurityInfo
from plone.autoform.interfaces import IFormFieldProvider
from plone.supermodel import model
from Products.CMFCore import permissions
from senaite.core.interfaces import IContact
from senaite.fhir import _
from zope import schema
from zope.component import adapter
from zope.interface import implementer
from zope.interface import provider


@provider(IFormFieldProvider)
class IExtendedContactBehavior(model.Schema):

    external_id = schema.TextLine(
        title=_(u"External ID"),
        description=_(u""),
        required=False,
    )


@implementer(IExtendedContactBehavior)
@adapter(IContact)
class ExtendedContact(object):

    security = ClassSecurityInfo()

    def __init__(self, context):
        self.context = context

    @security.protected(permissions.View)
    def getExternalID(self):
        accessor = self.context.accessor("external_id")
        return accessor(self.context)

    @security.protected(permissions.ModifyPortalContent)
    def setExternalID(self, value):
        mutator = self.context.mutator("external_id")
        mutator(self.context, value)

    external_id = property(getExternalID, setExternalID)


def getExternalID(self):
    behavior = IExtendedContactBehavior(self)
    return behavior.getExternalID()


def setExternalID(self, value):
    behavior = IExtendedContactBehavior(self)
    behavior.setExternalID(value)
