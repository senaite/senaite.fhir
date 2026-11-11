# -*- coding: utf-8 -*-

from senaite.fhir.datatype.element import Element
from senaite.fhir import api as fapi
from senaite.fhir.config import URN_UUID_PREFIX


class Reference(Element):
    """The Reference type contains at least one of a reference (literal
    reference), an identifier (logical reference), and a display (text
    description of target). In addition, it may contain a target type.
    https://hl7.org/fhir/R5/references.html#Reference
    """

    @property
    def reference(self):
        """Literal reference, Relative, internal or absolute URL
        https://hl7.org/fhir/R5/references-definitions.html#Reference.reference
        """
        return self.get("reference")

    @property
    def type(self):
        """Type the reference refers to (e.g. "Patient") - must be a resource
        in resources.
        https://hl7.org/fhir/R5/references-definitions.html#Reference.type
        Value set at https://hl7.org/fhir/R5/valueset-resource-types.html
        """
        return self.get("type")

    def is_urn_uuid(self):
        """Returns whether this is a `urn:uuid:<id>` reference, which points
        to the entry of the same bundle whose `fullUrl` is the reference
        """
        return self.reference.startswith(URN_UUID_PREFIX)

    def UUID(self):
        """Handy accessor that returns the UUID of the reference
        """
        if not self.reference:
            return None
        # remove the resource type, if any
        raw_id = self.reference.split("/")[-1]
        # remove the urn:uuid:
        raw_id = raw_id.split(":")[-1]
        try:
            return fapi.get_uuid(raw_id)
        except (TypeError, ValueError):
            return None

    def UID(self):
        """Handy accessor that returns the UID hex form of the reference
        Mimics the default behavior of AT/DX
        """
        uuid = self.UUID()
        return uuid.hex if uuid else None
