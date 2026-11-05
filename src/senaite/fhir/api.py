# -*- coding: utf-8 -*-

import json
import re
from uuid import UUID

from bika.lims import api
from bika.lims.api import _marker  # noqa
from bika.lims.api.security import check_permission
from bika.lims.interfaces import IInternalUse
from bika.lims.utils.analysisrequest import create_analysisrequest
from persistent.dict import PersistentDict
from plone.uuid.interfaces import IUUIDGenerator
from Products.Archetypes.utils import mapply
from Products.CMFCore.permissions import ModifyPortalContent
from senaite.fhir import logger
from senaite.fhir.catalog import FHIR_CATALOG
from senaite.fhir.config import ANALYSIS_REPORTABLE_STATUSES
from senaite.fhir.config import FHIR_BASE_URL
from senaite.fhir.config import FHIR_RESOURCE_TO_PORTAL_TYPE
from senaite.fhir.config import FHIR_STORAGE_KEY
from senaite.fhir.config import SECONDARY_RESOURCES_KEY
from senaite.fhir.config import SERVER_OWNED_ELEMENTS
from senaite.fhir.config import SYSTEM_CODES
from senaite.fhir.exceptions import FHIRAPIError
from senaite.fhir.exceptions import IdentifierValidationError
from senaite.fhir.exceptions import LogicalIdValidationError
from senaite.fhir.interfaces import IContentActionToFHIR
from senaite.fhir.interfaces import IContentFinder
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.interfaces import IFHIRContent
from senaite.fhir.interfaces import IFHIRResource
from senaite.fhir.interfaces import IFHIRToContent
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from zope.component import queryAdapter
from zope.deprecation import deprecate
from zope.interface import alsoProvides


def fail(msg, status=500):
    """Raises a ``FHIRAPIError`` carrying the given message and HTTP status.

    :param msg: the error message (a default is used when ``None``)
    :param status: the HTTP status code to attach (500 by default)
    :raises FHIRAPIError: always
    """
    if msg is None:
        msg = "Reason not given."
    raise FHIRAPIError(status, "{}".format(msg))


def is_fhir_content(obj):
    """Returns whether the object passed in was created from a FHIR resource
    """
    return IFHIRContent.providedBy(obj)


def is_fhir_resource(obj):
    """Returns whether the thing is a FHIR Resource object
    """
    return IFHIRResource.providedBy(obj)


def is_reportable(analysis):
    """Returns whether the analysis has to be exposed in FHIR results
    """
    if analysis.getHidden():
        return False
    if IInternalUse.providedBy(analysis):
        return False

    status = api.get_review_status(analysis)
    return status in ANALYSIS_REPORTABLE_STATUSES


def get_fhir_storage(obj):
    """Get or creates the FHIR annotation storage for the given object

    :param obj: Content object
    :returns: PersistentDict
    """
    annotation = IAnnotations(obj)
    if annotation.get(FHIR_STORAGE_KEY) is None:
        annotation[FHIR_STORAGE_KEY] = PersistentDict()
    return annotation[FHIR_STORAGE_KEY]


def is_uuid(thing):
    try:
        get_uuid(thing)
        return True
    except (TypeError, ValueError):
        return False


def get_uuid(thing):
    """Returns the UUID object
    """
    if isinstance(thing, UUID):
        return thing
    if is_fhir_resource(thing):
        return UUID(thing.id)
    if api.is_object(thing):
        return UUID(api.get_uid(thing))
    return UUID(thing)


def get_uid(obj):
    """Returns the UUID in hex format
    """
    if is_fhir_resource(obj):
        return get_uuid(obj).hex
    return api.get_uid(obj)


def get_resource_type(obj):
    """Returns the FHIR resource type associated to the given object.

    If a FHIR resource is passed in, its own ``resourceType`` is returned.
    For a SENAITE content object (or a brain/UID resolving to one), the
    resource type is resolved by reverse-looking-up the object's portal type
    in ``FHIR_RESOURCE_TO_PORTAL_TYPE`` (which maps resource type -> portal
    type), falling back to the portal type itself when no mapping is defined.

    When several resource types map to the same portal type, the first one in
    alphabetical order is returned for determinism.

    :param obj: FHIR resource, content object, catalog brain or UID
    :returns: the FHIR resource type, e.g. ``"Patient"``
    :rtype: str
    """
    if is_fhir_resource(obj):
        return obj.resourceType

    # reverse-lookup the resource type for the object's portal type
    if api.is_string(obj) and not is_uuid(obj):
        portal_type = obj
    else:
        obj = api.get_object(obj)
        portal_type = api.get_portal_type(obj)

    # looks for the first match
    mapping = sorted(FHIR_RESOURCE_TO_PORTAL_TYPE)
    for resource_type, mapped_portal_type in mapping:
        if mapped_portal_type == portal_type:
            return resource_type

    # fall back to the portal type itself when no mapping is defined
    return portal_type


def get_portal_type(obj):
    """Returns the SENAITE portal type associated to the given object.

    This is the inverse of ``get_resource_type``. If a FHIR resource is passed
    in, the portal type is looked up from its ``resourceType`` through
    ``FHIR_RESOURCE_TO_PORTAL_TYPE`` (which maps resource type -> portal type),
    falling back to the resource type itself when no mapping is defined. For a
    content object (or a brain/UID resolving to one), its portal type is
    returned.

    :param obj: FHIR resource, content object, catalog brain or UID
    :returns: the SENAITE portal type, e.g. ``"Patient"``
    :rtype: str
    """
    if is_fhir_resource(obj):
        # lookup the portal_type for the resource's resourceType
        resource_type = obj.resourceType
        mapping = dict(FHIR_RESOURCE_TO_PORTAL_TYPE)
        return mapping.get(resource_type, resource_type)

    # an object, return the portal type
    obj = api.get_object(obj)
    return api.get_portal_type(obj)


def get_fhir_uid(obj, resource_type=None):
    """Returns the FHIR UID (hex) of the counterpart resource of the given
    object for the given resource type.

    When ``resource_type`` is not provided, it defaults to the resource type
    associated to the object (see ``get_resource_type``).

    If the object has no separately-linked FHIR resource for that type, this
    falls back to the object's own SENAITE UID, so a FHIR resource derived
    from it keeps a stable identity (see ``get_fhir_uids``). Returns ``None``
    when the object has no UID associated to the requested resource type.

    :param obj: FHIR resource, content object, catalog brain or UID
    :param resource_type: FHIR resource type to look up, e.g. ``"Patient"``;
        defaults to the object's own resource type
    :returns: the FHIR UID in hex format, or ``None``
    :rtype: str
    """
    if resource_type is None:
        resource_type = get_resource_type(obj)

    # return the FHIR uid for the given object and resource type
    uids = get_fhir_uids(obj)
    return uids.get(resource_type)


def get_fhir_id(obj, resource_type=None):
    """Returns the FHIR id of the counterpart resource of the given object for
    the given resource type, in canonical dashed UUID form.

    This is the string form of ``get_fhir_uid`` (which returns the UID in hex
    format). When ``resource_type`` is not provided, it defaults to the
    resource type associated to the object (see ``get_resource_type``).

    Like ``get_fhir_uid``, it falls back to the object's own SENAITE UID when
    no separate FHIR resource is linked for that type, and returns ``None``
    when the object has no UID associated to the requested resource type.

    :param obj: FHIR resource, content object, catalog brain or UID
    :param resource_type: FHIR resource type to look up, e.g. ``"Patient"``;
        defaults to the object's own resource type
    :returns: the FHIR id in canonical dashed UUID form, or ``None``
    :rtype: str
    """
    uid = get_fhir_uid(obj, resource_type=resource_type)
    return str(get_uuid(uid)) if uid else None


def get_fhir_uids(obj):
    """Returns the FHIR UIDs (hex) assigned to the given object, grouped by
    resource type.

    For a FHIR resource, a single-entry mapping ``{resourceType: uid}`` is
    returned.

    For a brain coming from the FHIR catalog, the precomputed mapping is read
    directly from its ``fhir_resource_types`` metadata (no object wake-up).

    For a content object (or a brain/UID resolving to one), the persisted FHIR
    UIDs are read from the object's annotation storage (without creating it, to
    avoid a write-on-read) and grouped by resource type. The object's own
    SENAITE UID is then injected for both its FHIR resource type and its portal
    type when no entry exists yet, so a resource derived from the object always
    resolves to a stable identity.

    :param obj: FHIR resource, content object, catalog brain or UID
    :returns: mapping of resource type -> FHIR UID (hex)
    :rtype: dict
    """
    if is_fhir_resource(obj):
        # TODO Include uids of references from inside the resource maybe?
        return {obj.resourceType: get_uid(obj)}

    if api.is_brain(obj):
        # if is a brain from fhir_catalog, rely on fhir_resources_types
        resource_types = getattr(obj, "fhir_resource_types", None)
        if resource_types:
            return json.loads(resource_types)

    # get object's FHIR annotations storage, but don't use get_fhir_storage to
    # not do a write-on-read
    obj = api.get_object(obj)
    annotation = IAnnotations(obj)
    storage = annotation.get(FHIR_STORAGE_KEY) or {}
    uids = dict(storage.get("uids") or {})

    # inject the uid for the counterpart FHIR resource if not present
    resource_type = get_resource_type(obj)
    if resource_type and resource_type not in uids:
        uids[resource_type] = api.get_uid(obj)

    # inject the object's uid if no entry for object's portal_type
    portal_type = api.get_portal_type(obj)
    if portal_type not in uids:
        uids[portal_type] = api.get_uid(obj)

    return uids


def set_fhir_uids(obj, **kwargs):
    """Persists FHIR UIDs against the given object, keyed by resource type, and
    (re)indexes it in the FHIR catalog.

    Each keyword argument maps a FHIR resource type to the UID (hex) of its
    counterpart FHIR resource, e.g. ``set_fhir_uids(sample, Specimen=uid1,
    ServiceRequest=uid2)``. Stored entries for resource types not passed in are
    kept; entries for the passed resource types are overwritten.

    The object is then indexed in the FHIR catalog so it can be resolved back
    via ``search_by_fhir_uid``.

    :param obj: content object, catalog brain or UID
    :param kwargs: mapping of resource type -> FHIR UID (hex)
    """
    obj = api.get_object(obj)
    storage = get_fhir_storage(obj)
    # Reassign "uids" as a whole (rather than mutating the dict returned by
    # storage.setdefault("uids", {}) in place) so the PersistentDict's
    # __setitem__ fires and the change is actually persisted. An in-place
    # mutation of the nested dict doesn't mark ``storage`` as changed, so a
    # second resource type linked in a later transaction (e.g. an Analysis'
    # instrument-scoped ServiceRequest followed by an incoming Observation)
    # would silently fail to persist.
    uids = dict(storage.get("uids") or {})
    uids.update(kwargs)
    storage["uids"] = uids

    # index/reindex object in fhir_catalog. Use the low-level _indexObject so
    # the object is forced into the FHIR catalog: the high-level indexObject
    # goes through the CatalogMultiplexProcessor, which only routes to the
    # catalogs mapped to the object's portal type (api.get_catalogs_for) and
    # would therefore skip this catalog.
    cat = api.get_tool(FHIR_CATALOG)
    cat._indexObject(obj)


def search_by_fhir_uid(fhir_uid, portal_type=None, as_brains=True):
    """Searches the FHIR catalog for the objects holding the given FHIR UID.

    Looks up the ``fhir_uids`` index of the FHIR catalog. The value is
    harmonized to a hex UID first, so either a FHIR id (dashed) or a hex UID
    can be passed in. Optionally constrained to a given portal type.

    :param fhir_uid: FHIR UID (hex) or FHIR id (dashed UUID) to look up
    :param portal_type: optional portal type to constrain the search
    :param as_brains: when True (default) returns catalog brains, otherwise
        returns the woken-up content objects
    :returns: the matching catalog brains, or content objects when
        ``as_brains`` is False (an empty list when nothing matches)
    :rtype: list
    """
    # prevent circular imports
    from senaite.fhir.catalog import FHIR_CATALOG  # noqa

    # harmonize just in case it was a fhir_id
    uid = get_uuid(fhir_uid).hex

    # build the search query
    query = {"fhir_uids": uid}
    if portal_type:
        query["portal_type"] = portal_type

    # search to fhir_catalog by fhir_uids
    fc = api.get_tool(FHIR_CATALOG)
    brains = fc(**query)
    if as_brains:
        return brains

    # wake-up the objects
    return [api.get_object(brain) for brain in brains]


def get_object_by_fhir_uid(fhir_uid, portal_type=None, default=_marker):
    """Returns the SENAITE object holding the given FHIR UID.

    Resolves through the FHIR catalog (see ``search_by_fhir_uid``). The
    ``fhir_uid`` can be a hex UID or a dashed FHIR id, as it is harmonized
    before searching. The lookup can be constrained to a ``portal_type``; when
    none is given, all portal types are searched (less performant).

    Primary match: the UID belongs to the object's own portal/resource type.
    Secondary match: the UID was stored for a different resource type on the
    same object (e.g. a Specimen UID stored on an AnalysisRequest).

    :param fhir_uid: FHIR UID (hex) or FHIR id (dashed UUID) to look up
    :param portal_type: optional portal type to constrain the search
    :param default: value to return when no object holds the UID; when omitted,
        a ``FHIRAPIError`` is raised instead
    :returns: the matching content object, or ``default``
    """
    # harmonize just in case it was a fhir_id
    fhir_uid = get_uuid(fhir_uid).hex

    # do the search
    brains = search_by_fhir_uid(fhir_uid, portal_type=portal_type)

    secondary = []
    for brain in brains:
        uids = get_fhir_uids(brain)
        portal_type = get_portal_type(brain)
        # primary match: uid belongs to the object's own portal/resource type
        if uids.get(portal_type) == fhir_uid:
            return api.get_object(brain)
        resource_type = get_resource_type(portal_type)
        if uids.get(resource_type) == fhir_uid:
            return api.get_object(brain)
        # secondary match: uid stored for a different resource type
        if fhir_uid in uids.values():
            secondary.append(brain)

    if secondary:
        return api.get_object(secondary[0])

    if default is _marker:
        fail("No object found for FHIR UID {}".format(fhir_uid))
    return default


def get_object(thing, default=_marker):
    """Resolves the given thing into a SENAITE content object.

    Resolution order:

    1. A content object, catalog brain or SENAITE UID is resolved through the
       core ``bika.lims.api.get_object``.
    2. If that misses (or a FHIR resource is passed), the counterpart object is
       resolved through the FHIR catalog by its FHIR UID (see
       ``get_object_by_fhir_uid``). A bare FHIR id/UID string is resolved this
       way too, by searching across all portal types; a FHIR resource narrows
       the search to its mapped portal type.

    :param thing: FHIR resource, content object, catalog brain, SENAITE UID or
        FHIR UID/id
    :param default: value to return when not found; when omitted, a
        ``FHIRAPIError`` is raised
    :returns: the resolved content object, or ``default``
    """
    # a FHIR resource: resolve its counterpart, narrowed to the mapped type.
    # This must be checked before the ``is_uuid`` branch below, as a resource
    # also satisfies ``is_uuid`` (its id is a UUID) and would otherwise be
    # searched across all portal types, resolving e.g. a Specimen to the
    # AnalysisRequest that cross-references its UID instead of a SampleType.
    if is_fhir_resource(thing):
        fhir_uid = get_uid(thing)
        portal_type = get_portal_type(thing)
        return get_object_by_fhir_uid(fhir_uid, portal_type, default=default)

    # a content object, catalog brain or SENAITE UID: delegate to core's api
    obj = api.get_object(thing, default=None)
    if obj:
        return obj

    # a bare FHIR id/UID string: search across all portal types (type unknown)
    if is_uuid(thing):
        fhir_uid = get_uuid(thing).hex
        return get_object_by_fhir_uid(fhir_uid, default=default)

    # not resolvable
    if default is _marker:
        fail(msg="Not Found", status=404)
    return default


def find_object_for(resource, default=_marker):
    """Finds the SENAITE object that corresponds to the given FHIR resource.

    The counterpart is always an object of the resource's mapped portal type
    (see ``get_portal_type``), e.g. a Specimen resolves to a SampleType, an
    Organization to a Client. Resolution happens in two steps, both scoped to
    that portal type:

    1. an exact match by FHIR UID through the FHIR catalog (see
       ``get_object``, which narrows the lookup to that portal type);
    2. when that misses, the ``IContentFinder`` adapter registered for the
       resource (if any) is asked to find a suitable counterpart by business
       keys (e.g. ``ClientFinder`` matches a Client by its ``ClientID``,
       ``SampleTypeFinder`` matches a SampleType by its display).

    Constraining the UID lookup to the mapped portal type is what makes this
    reliable for resources whose FHIR UID is cross-referenced elsewhere: a
    Specimen's UID is stored on the AnalysisRequest that owns it, so an
    unconstrained lookup (see ``get_object``) would resolve a Specimen to that
    AnalysisRequest instead of to its SampleType counterpart. Callers can rely
    on the result being of the mapped portal type without knowing any of these
    FHIR-to-SENAITE mapping details.

    This is used by the bundle POST endpoint to resolve existing content
    (so it gets updated instead of duplicated) before falling back to create.

    :param resource: the FHIR resource to find a counterpart for
    :param default: value to return when ``resource`` is not a FHIR resource;
        when omitted, a ``FHIRAPIError`` is raised instead
    :returns: the matching content object, or ``None`` when none is found
    :raises FHIRAPIError: if ``resource`` is not a FHIR resource and no
        ``default`` was provided
    """
    if not is_fhir_resource(resource):
        if default is _marker:
            fail("Type is not supported: %r" % resource)
        return default

    # exact match by FHIR UID, scoped to the resource's mapped portal type
    match = get_object(resource, default=None)
    if match:
        return match

    # search using a content finder adapter
    adapter = queryAdapter(resource, IContentFinder)
    if not adapter:
        logger.debug("No ContentFinder adapter available: %r" % resource)
        return None

    return adapter.find()


def get_available_reasons():
    """Returns available rejection reasons
    """
    setup = api.get_senaite_setup()
    return setup.getRejectionReasons()


def to_fhir_resource(thing, default=_marker, resource_type=None):
    """Converts the given thing into a FHIR resource.

    Accepts several inputs:

    - a FHIR resource: returned as-is;
    - a ``dict``: dispatched to the ``IFHIRResource`` adapter named after its
      ``resourceType``;
    - a content object, catalog brain or UID: resolved (see ``get_object``)
      and converted through its ``IContentToFHIR`` adapter, named after
      ``resource_type`` when given (falling back to the default, unnamed
      adapter) — this lets a single object be represented as more than one
      resource type, e.g. an Analysis as either an Observation (default) or
      a ServiceRequest (named).

    Empty/falsy input returns ``None``. On any other failure (missing/
    unsupported resource type, object not found, no adapter, or the adapter
    itself returning ``None``) a ``FHIRAPIError`` is raised unless
    ``default`` is provided.

    :param thing: FHIR resource, dict, content object, catalog brain or UID
    :param default: value to return instead of raising on failure
    :param resource_type: optional resource type used to select a named
        ``IContentToFHIR`` adapter for a content object, or as a hint when
        resolving a bare UID that is a FHIR id rather than a SENAITE UID
    :returns: the FHIR resource, ``None`` for empty input, or ``default``
    """
    if not thing:
        return None

    if is_fhir_resource(thing):
        return thing

    if isinstance(thing, dict):
        rtype = thing.get("resourceType")
        if not rtype:
            if default is _marker:
                fail(msg="Not well formed resource. Resource type is missing")
            return default

        # Look for FHIRResource named adapters (wrappers)
        resource = queryAdapter(thing, IFHIRResource, rtype)
        if not resource:
            if default is _marker:
                fail(msg="Resource type is not supported: %s" % rtype)
            return default

        return resource

    # get the object to build the FHIR Resource from
    obj = get_object(thing, default=None)
    if not obj:
        if default is _marker:
            fail(msg="Not Found", status=404)
        return default

    # rely on the unnamed adapter if resource type matches with object's
    obj_rtype = get_resource_type(obj)
    if not resource_type or obj_rtype == resource_type:
        # rely on default's IContentToFHIR adapter
        # TODO: We might consider to make all IContentToFHIR as named adapters
        adapter = queryAdapter(obj, IContentToFHIR)
    else:
        # rely on named IContentToFHIR adapter
        adapter = queryAdapter(obj, IContentToFHIR, name=resource_type)

    if not adapter:
        if default is _marker:
            fail(msg="Type is not supported: %r" % obj)
        return default

    resource = adapter.to_fhir_resource()
    if not resource:
        if default is _marker:
            fail(msg="Not Found", status=404)
        return default

    return resource


def to_fhir_action_resource(thing, fhir_action, default=_marker):
    """Converts the object action/transition to a FHIR resource
    """
    obj = api.get_object(thing)
    name = "senaite.fhir.action.%s" % fhir_action
    adapter = queryAdapter(obj, IContentActionToFHIR, name=name)
    if not adapter:
        if default is _marker:
            fail(msg="Action is not supported: %s for %r" % (fhir_action, obj))
        return default
    return adapter.to_fhir_resource()


def to_content_dict(resource, default=_marker):
    """Converts a FHIR resource into a content dict for the creation or
    edition of the AT/DX content whose portal type matches the resource type.

    The conversion is delegated to the ``IFHIRToContent`` adapter registered
    for the resource. When no such adapter exists, a ``ValueError`` is raised
    unless ``default`` is provided, in which case ``default`` is returned.

    :param resource: the FHIR resource to convert
    :param default: value to return instead of raising when no adapter exists
    :returns: a dict of field name -> value (including ``portal_type`` and
        ``parent_path``), or ``default``
    :rtype: dict
    """
    # convert the resource to a content dict
    adapter = queryAdapter(resource, IFHIRToContent)
    if not adapter:
        msg = "Missing IFHIRToContent adapter for %r" % resource
        if default is _marker:
            raise ValueError(msg)
        logger.warn("Missing IFHIRToContent adapter for %r" % resource)
        return default

    # use the adapter to convert the resource to a content-suitable dict
    return adapter.to_content_dict()


def validate(resource):
    """Raises a ResourceValidationError if the resource violates any of the
    validation rules of its IFHIRToContent converter

    :param resource: the incoming FHIR resource to validate
    """
    adapter = queryAdapter(resource, IFHIRToContent)
    if not adapter:
        raise ValueError("Missing IFHIRToContent adapter for %r" % resource)
    adapter.validate()


def can_create_or_update(resource):
    """Returns whether the creation of counterpart objects for the given
    resources is supported
    """
    if not is_fhir_resource(resource):
        raise ValueError("Type not supported: {}".format(repr(type(resource))))

    # TODO Make this configurable with a senaite.fhir-specific control panel
    supported_types = [
        "ServiceRequest", "Patient", "Practitioner", "Organization",
        "Observation",
    ]
    if resource.resourceType not in supported_types:
        return False

    # Check if there is a FHIRToContent adapter registered
    adapter = queryAdapter(resource, IFHIRToContent)
    if not adapter:
        logger.warn("Can create or update, but FHIRToContent missing: %r" %
                    resource)
        return False
    return True


def to_naming_system_url(system_id):
    """Returns the canonical NamingSystem URI for an identifier namespace

    `system_id` is the NamingSystem id as published in the implementation
    guide, e.g. `sample-id`, `analysis-id` or `client-sample-id`. The URI it
    builds is what a FHIR `Identifier.system` has to carry for a consumer to
    tell one namespace from another, so it serves both to stamp outgoing
    identifiers and to check the system of the incoming ones.
    https://fhir.senaite.org/identifiers.html
    """
    return "%s/NamingSystem/%s" % (FHIR_BASE_URL, system_id)


def validate_identifiers(resource):
    """Raises an IdentifierValidationError if the identifiers of the incoming
    resource do not follow the identifiers pattern. A resource whose type
    supports no external identifier cannot carry any identifier at all,
    whatever its `use`
    https://fhir.senaite.org/identifiers.html

    :param resource: the incoming FHIR resource to validate
    """
    if not resource.external_id_system:
        validate_no_identifier(resource)
        return

    validate_internal_identifier(resource)
    validate_external_identifier(resource)


def validate_no_identifier(resource):
    """Raises an IdentifierValidationError if the resource carries any
    identifier at all, whatever its `use`. For resources that support no
    identifier, such as ServiceRequest

    :param resource: the incoming FHIR resource to validate
    """
    if resource.identifier:
        msg = "Cannot specify any identifier in {}".format(
            resource.resourceType)
        raise IdentifierValidationError(resource, msg)


def validate_no_logical_id(resource):
    """Raises a LogicalIdValidationError if the bundle entry of the resource
    carries a `resource.id`. The logical id is assigned by SENAITE: a POSTed
    entry is only identified by the placeholder of its `fullUrl`, which the
    other entries of the bundle refer to

    :param resource: the FHIR resource of a bundle entry
    """
    bundle = resource.get("_bundle")
    if not bundle:
        return
    index = bundle.get_entry_index(resource)
    if index is None:
        return
    entry = bundle["entry"][index]
    if "id" in (entry.get("resource") or {}):
        raise LogicalIdValidationError(index)


def validate_internal_identifier(resource):
    """Raises an IdentifierValidationError if the resource carries an
    internal (usual) identifier. These are assigned by SENAITE only after
    creation and can never be supplied by the API consumer

    :param resource: the incoming FHIR resource to validate
    """
    object_id = resource.get_object_id()
    if object_id:
        msg = (
            "Cannot specify usual identifier externally in incoming {}:{}"
        ).format(resource.resourceType, object_id.value)
        raise IdentifierValidationError(resource, msg)


def validate_external_identifier(resource):
    """Raises an IdentifierValidationError if any of the identifiers of the
    resource other than the internal (usual) one is not an external one, with
    `use="secondary"` and the NamingSystem its type supports. A resource can
    only carry external identifiers of that system, whatever their position

    The internal (usual) identifier is validated by
    `validate_internal_identifier`

    :param resource: the incoming FHIR resource to validate
    """
    system = to_naming_system_url(resource.external_id_system)
    identifiers = getattr(resource, "identifier", None) or []
    for identifier in identifiers:
        if identifier.use == "usual":
            continue

        if not identifier.use:
            msg = "Missing identifier use in {}".format(resource.resourceType)
            raise IdentifierValidationError(resource, msg)

        if identifier.use != "secondary":
            msg = (
                "Unsupported identifier use in {}: {}"
            ).format(resource.resourceType, identifier.use)
            raise IdentifierValidationError(resource, msg)

        if not identifier.system:
            msg = "Missing identifier system in {}".format(
                resource.resourceType)
            raise IdentifierValidationError(resource, msg)

        if identifier.system != system:
            msg = (
                "Unsupported identifier system in {}: {}"
            ).format(resource.resourceType, identifier.system)
            raise IdentifierValidationError(resource, msg)


def update(obj, resource):
    """Updates an existing object with the data carried by the FHIR resource.

    The caller is expected to resolve the counterpart object first (e.g. via
    ``get_object`` or ``find_object_for``). Each writable, permitted field
    present in the resource's content dict is set, the resource is linked
    (see ``link_fhir_resource``) and the object is re-cataloged.

    :param obj: the existing content object to update
    :param resource: the FHIR resource carrying the new field values
    :returns: the updated object
    """
    # convert the resource to a dict suitable for updating AT/DX contents
    data = to_content_dict(resource)

    # get the secondary FHIR resources to be linked to the object, if any
    resources = get_secondary_resources(data)

    # loop through data and set field values
    fields = api.get_fields(obj)
    for name, value in data.items():
        # check if there is a field
        field = fields.get(name, None)
        if not field:
            continue
        # check if readonly
        readonly = getattr(field, "readonly", False)
        if readonly:
            continue
        # check permissions
        perm = getattr(field, "write_permission", ModifyPortalContent)
        if perm and not check_permission(perm, obj):
            continue

        # Set the value
        if hasattr(field, "getMutator"):
            mutator = field.getMutator(obj)
            mapply(mutator, value)
        else:
            field.set(obj, value)

    # link the FHIR resource to the obj
    link_fhir_resource(obj, resource)

    # link the secondary FHIR resources to the object
    for secondary in resources:
        link_fhir_resource(obj, secondary, secondary=True)

    # re-catalog the object
    obj.reindexObject()
    return obj


def get_secondary_resources(data):
    """Returns the secondary FHIR resources declared in the given content dict.

    Converters use the ``_fhir_secondary_resources`` key of the content dict
    (``SECONDARY_RESOURCES_KEY``) to hand over the resources that have to be
    linked to the object alongside the primary one, e.g. the ``Specimen`` of a
    ``ServiceRequest``, which has no counterpart content type in SENAITE.

    A single resource is accepted as well as a list of them. This is not just
    for convenience: FHIR resources are ``dict`` subclasses, so iterating a
    bare resource would silently yield its keys instead of the resource itself.

    The content dict is left untouched. The key is not a content field name --
    field names are public, and always come with an accessor and a mutator --
    so it is simply ignored when the rest of the dict is applied.

    :param data: the content dict to read the secondary resources from
    :returns: the list of secondary FHIR resources, empty when there are none
    :rtype: list
    """
    resources = data.get(SECONDARY_RESOURCES_KEY) or []
    if is_fhir_resource(resources):
        return [resources]
    return list(filter(is_fhir_resource, resources))


def create(resource):
    """Creates a counterpart SENAITE object for the given FHIR resource.

    The resource is converted to a content dict (see ``to_content_dict``) and
    the object is created under the ``parent_path`` it resolves to
    (AnalysisRequest samples are created through ``create_analysisrequest``).
    The resource is then linked to the new object via ``link_fhir_resource``.

    :param resource: the FHIR resource to create a counterpart for
    :returns: the newly created content object
    :raises ValueError: if a counterpart object already exists
    """
    # check if already exists
    obj = get_object(resource, default=None)
    if obj:
        raise ValueError("Counterpart object already exists: %r" % resource)

    # get the content dict
    data = to_content_dict(resource)

    # get the secondary FHIR resources to be linked to the object, if any
    resources = get_secondary_resources(data)

    # create the object
    portal_type = data.pop("portal_type")
    container = data.pop("parent_path")
    container = api.get_object_by_path(container)

    # AnalysisRequest objects are created differently
    # TODO Consider an adapter for create
    if portal_type == "AnalysisRequest":
        request = api.get_request()
        obj = create_analysisrequest(data["Client"], request, data)
    else:
        obj = api.create(container, portal_type, **data)

    # link the FHIR resource to the obj
    link_fhir_resource(obj, resource)

    # link the secondary FHIR resources to the object
    for secondary in resources:
        link_fhir_resource(obj, secondary, secondary=True)

    return obj


def link_fhir_resource(obj, resource, secondary=False):
    """Links a FHIR resource to the given SENAITE object.

    Marks the object with ``IFHIRContent`` and records the resource's UID in
    the object's ``uids`` mapping (keyed by resource type, via
    ``set_fhir_uids``, which also indexes it in the FHIR catalog). The
    serialized resource is also stored under ``data`` for offline use --
    unless that slot already holds a snapshot of a *different* resource type,
    in which case it is left untouched (see below).

    Pass `secondary=True` for a resource that has no counterpart content type
    in SENAITE, e.g. the `Specimen` of an AnalysisRequest. There is no live
    content to rebuild such a resource from, so it is snapshotted in the
    type-keyed `resources` slot instead of `data`, and `get_fhir_resource`
    serves it back from there. Resources that *do* have a counterpart must not
    be stored there: they are always re-synthesized by their `IContentToFHIR`
    adapter, and a stale snapshot would shadow the live one.

    :param obj: the content object to link the resource to
    :param resource: the FHIR resource to link
    :param secondary: whether the resource has no counterpart content type
    :raises ValueError: if `resource` is not a FHIR resource
    """
    if not is_fhir_resource(resource):
        raise ValueError("Type not supported: {}".format(repr(type(resource))))

    # mark the object with IFHIRContent, so we can always know beforehand if
    # this object has counterpart FHIR resources
    if not IFHIRContent.providedBy(obj):
        alsoProvides(obj, IFHIRContent)

    # get the uid and resourceType
    resource_uid = get_uid(resource)
    resource_type = resource.resourceType

    # link the resource's UID to the given object
    kwargs = {resource_type: resource_uid}
    set_fhir_uids(obj, **kwargs)

    annotation = get_fhir_storage(obj)

    if secondary:
        # Snapshot the resource in the type-keyed ``resources`` slot. It is the
        # only source of truth for this resource, so ``get_fhir_resource``
        # serves it back from here rather than from an IContentToFHIR adapter.
        # Reassign "resources" as a whole, for the same reason as in
        # ``set_fhir_uids``: mutating the nested dict in place does not mark
        # the PersistentDict as changed, so the write can get lost.
        resources = dict(annotation.get("resources") or {})
        resources[resource_type] = resource.to_dict()
        annotation["resources"] = resources
        return

    # TODO Remove (kept for backwards compatibility)
    # assign the FHIR UID, along with current data so we can always use the
    # original information, even when connection with source is lost.
    # ``data`` is a single slot, but an object can carry more than one linked
    # FHIR identity (e.g. an Analysis carries both its instrument-scoped
    # ServiceRequest, linked when an Instrument is assigned, and an incoming
    # Observation result), so whichever resource type got there first keeps
    # it; only overwrite when the slot is empty or already of this same type.
    existing_type = (annotation.get("data") or {}).get("resourceType")
    if not existing_type or existing_type == resource_type:
        annotation["data"] = resource.to_dict()


def slugify(value, repl="-"):
    """Slugifies the given value.

    Lowercases the input, strips non-word characters and collapses runs of
    whitespace, underscores and hyphens into a single separator, trimming
    leading/trailing separators.

    :param value: the string to slugify
    :param repl: separator to collapse runs into (``-`` by default; pass an
        empty string to remove separators altogether)
    :returns: the slugified string
    :rtype: str
    """
    repl = repl if repl else ""
    slug = value.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", repl, slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug


def get_system_code(resource_type, default=_marker):
    """Returns the system code supported for the given resource type
    """
    # TODO Get this from control panel/registry settings instead
    system = dict(SYSTEM_CODES).get(resource_type)
    if system:
        return system
    if default is _marker:
        raise ValueError("No system code defined for %s" % resource_type)
    return default


@deprecate("Use link_fhir_resource(obj, resource, secondary=True) instead")
def store_fhir_resource(obj, resource):
    """Persists a secondary FHIR resource against a SENAITE object.

    :param obj: content object, catalog brain or UID
    :param resource: the FHIR resource to store
    """
    return link_fhir_resource(api.get_object(obj), resource, secondary=True)


@deprecate("Use get_fhir_resource instead")
def get_stored_fhir_resource(obj, resource_type):
    """Returns a previously stored secondary FHIR resource from the object's
    annotation storage, or ``None`` when none is found.

    Reads from the type-keyed slot written by ``store_fhir_resource`` without
    waking up the object unnecessarily.

    :param obj: content object, catalog brain or UID
    :param resource_type: FHIR resource type to retrieve, e.g. ``"Specimen"``
    :returns: the FHIR resource, or ``None``
    """
    obj = api.get_object(obj)
    annotation = IAnnotations(obj)
    storage = annotation.get(FHIR_STORAGE_KEY) or {}
    resources = storage.get("resources") or {}
    data = resources.get(resource_type)
    if not data:
        return None
    return to_fhir_resource(data, default=None)


def get_server_owned_elements(obj, resource_type):
    """Returns the elements of a secondary FHIR resource that are owned by
    SENAITE, synthesized from the live content of the given object.

    These are the elements a consumer cannot supply (e.g. the internal
    Sample ID of a Specimen) or that SENAITE keeps up to date afterwards (e.g.
    the Specimen status), so they must never be served from the snapshot
    stored by `link_fhir_resource`. Which elements are owned by SENAITE for
    each resource type is defined in `SERVER_OWNED_ELEMENTS`.

    :param obj: the content object the resource is linked to
    :param resource_type: FHIR resource type, e.g. `"Specimen"`
    :returns: dict of element name to value, empty if none
    """
    keys = dict(SERVER_OWNED_ELEMENTS).get(resource_type)
    if not keys:
        return {}

    live = to_fhir_resource(obj, default=None, resource_type=resource_type)
    if not live:
        return {}

    return dict([(key, live[key]) for key in keys if live.get(key)])


def get_fhir_resource(obj, resource_type=None, default=_marker):
    """Returns the FHIR resource of the given type linked to the given object.

    Secondary resources -- those without a counterpart content type in SENAITE,
    e.g. the ``Specimen`` of an AnalysisRequest -- are served from the snapshot
    that ``link_fhir_resource`` keeps in the object's annotation storage, as
    there is no live content to rebuild them from. The elements owned by
    SENAITE (see `get_server_owned_elements`) are the exception: they are
    always taken from the live content, overriding the snapshot.

    Any other resource type is synthesized from live content through its
    ``IContentToFHIR`` adapter (see ``to_fhir_resource``), so it always
    reflects the current state of the object rather than the payload that
    happened to create it.

    :param obj: content object, catalog brain, SENAITE UID or FHIR UID/id
    :param resource_type: FHIR resource type to return; defaults to the
        resource type associated to the object (see ``get_resource_type``)
    :param default: value to return instead of raising on failure
    :returns: the FHIR resource, or ``default``
    """
    # resolve the object, also when a bare FHIR id/UID was passed in
    obj = get_object(obj, default=None)
    if not obj:
        if default is _marker:
            fail(msg="Not Found", status=404)
        return default

    # default to the resource type associated to the object
    if not resource_type:
        resource_type = get_resource_type(obj)

    # look for a stored secondary resource first, reading the annotation
    # directly so the storage is not created on read
    storage = IAnnotations(obj).get(FHIR_STORAGE_KEY) or {}
    stored = (storage.get("resources") or {}).get(resource_type)
    if stored:
        # complete the snapshot with the elements owned by SENAITE, e.g. the
        # internal Sample ID of a Specimen, that a consumer cannot supply
        data = dict(stored)
        data.update(get_server_owned_elements(obj, resource_type))
        return to_fhir_resource(data, default=default)

    # rely on the IContentToFHIR adapter for the requested resource type
    return to_fhir_resource(obj, default=default, resource_type=resource_type)


def generate_UUID():
    """Generates a new UUID object
    """
    generator = getUtility(IUUIDGenerator)
    return get_uuid(generator())
