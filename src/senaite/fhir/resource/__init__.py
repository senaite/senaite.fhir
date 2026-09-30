# -*- coding: utf-8 -*-
import copy
import sys

from senaite.core.api import dtime
from senaite.fhir.converter import first_by
from senaite.fhir.converter import get_by_key
from senaite.fhir.datatype.extension import Extension
from senaite.fhir.datatype.meta import Meta
from senaite.fhir.interfaces import IFHIRResource
from zope.interface import implementer

_marker = object()


@implementer(IFHIRResource)
class FHIRResource(dict):

    __cardinality = (
        ("id", "0..1"),
        ("meta", "0..1"),
        ("implicitRules", "0..1"),
        ("language", "0..1"),
    )

    __fixed_values = tuple()

    def __init__(self, seq=None, **kwargs):
        super(FHIRResource, self).__init__(seq, **kwargs)
        self._initialize()
        self._validate()

    @property
    def resourceType(self):
        """Returns the resource type
        """
        return self.get("resourceType")

    @property
    def id(self):
        """Returns the logical id of the artifact
        https://hl7.org/fhir/R5/resource.html#id
        """
        return self.get("id")

    @property
    def meta(self):
        """Returns the metadata about the resource
        """
        data = self.get("meta") or {}
        return Meta(data)

    @property
    def implicitRules(self):
        """A set of rules under which this content was created
        """
        return self.get("implicitRules") or []

    @property
    def language(self):
        """Language of the resource content
        """
        return self.get("language")

    @property
    def modified(self):
        """Returns the last modification date of this resource
        Mimics te behaviour of DX and AT types
        """
        return dtime.to_dt(self.meta.lastUpdated)

    @property
    def extension(self):
        """Returns a list of Extension data types, if any
        """
        data = self.get("extension") or []
        return [Extension(item) for item in data]

    def get_extension(self, url):
        """Returns an Extension of this resource by url, if any
        """
        return get_by_key(self.extension, key="url", value=url)

    def get_external_id(self):
        """Returns the Identifier object representing the identifier
        originating from the API's consumer system (e.g. the ordering EHR or
        middleware)
        https://fhir.senaite.org/identifiers.html
        """
        # TODO Move this function to fapi.resource
        identifiers = getattr(self, "identifier", [])
        return first_by(identifiers, use="secondary")

    def get_object_id(self):
        """Returns the Identifier object representing the internal identifier
        created and assigned by SENAITE
        https://fhir.senaite.org/identifiers.html
        """
        # TODO Move this function to fapi.resource
        identifiers = getattr(self, "identifier", [])
        return first_by(identifiers, use="usual")

    def __deepcopy__(self, memo):
        """Returns a deep copy of this resource. The internal keys (prefixed
        with an underscore, e.g. `_bundle`) are not FHIR elements but context,
        so they are shared with the copy instead of being copied
        """
        # skip __init__, as the default deep copy does, so values assigned on
        # initialization (e.g. a new id) are not reset
        klass = self.__class__
        clone = klass.__new__(klass)
        memo[id(self)] = clone
        for key, value in self.items():
            if not key.startswith("_"):
                value = copy.deepcopy(value, memo)
            dict.__setitem__(clone, key, value)
        clone.__dict__.update(copy.deepcopy(self.__dict__, memo))
        return clone

    def to_dict(self):
        """Returns a copy of this resource as a plain dict, without the
        internal keys (prefixed with an underscore, e.g. `_bundle`), as they
        are not FHIR elements
        """
        data = dict([(key, value) for key, value in self.items()
                     if not key.startswith("_")])
        return copy.deepcopy(data)

    def _get(self, data_type, name, as_list=False, default=None):
        value = self.get(name, _marker)
        if value is _marker:
            return default
        if as_list:
            return [data_type(record) for record in value]
        return data_type(value)

    def _initialize(self):
        pass

    def _validate(self):
        """Looks through all properties and validates any constraint
        """
        # TODO Implement (loop through attr and use decorators for constraints)

        # Validate fixed values
        for name, value in self.__fixed_values:
            val = getattr(self, name, value)
            if val != value:
                raise ValueError(
                    "%r: No valid value for '%s': %r" %
                    (self, name, val)
                )
            self[name] = value

        # Validate cardinality
        for name, exp in self.__cardinality:
            # get the low and high valies
            low, high = exp.strip().split("..")
            low = int(low)
            high = sys.maxsize if high == "*" else int(high)
            # get the value of each attr and check if in-range
            val = getattr(self, name, [])
            if not isinstance(val, (list, tuple)):
                val = list(filter(None, [val]))
            card = len(val)
            if card < low or card > high:
                raise ValueError(
                    "%r: No valid cardinality for '%s': %s (expected: %s)" %
                    (self, name, card, exp)
                )

    def __str__(self):
        id = self.get("id") or "--no-id--"
        return "<%s %s>" % (self.__class__.__name__, id)

    def __repr__(self):
        return self.__str__()
