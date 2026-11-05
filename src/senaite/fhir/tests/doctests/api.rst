SENAITE FHIR API
----------------

This doctest exercises the helpers exposed in `senaite.fhir.api`. The
package-level convention is to alias it as `fapi` so it can co-exist
with the core SENAITE API which is imported as `api`::

    >>> from bika.lims import api
    >>> from senaite.fhir import api as fapi

Running this test from the buildout directory::

    bin/test test_doctests -t api


Test Setup
~~~~~~~~~~

Needed imports::

    >>> import transaction
    >>> from uuid import UUID
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID

    >>> from senaite.fhir.exceptions import FHIRAPIError
    >>> from senaite.fhir.interfaces import IFHIRContent
    >>> from senaite.fhir.interfaces import IFHIRResource
    >>> from senaite.fhir.resource.patient import PatientResource

Variables::

    >>> portal = self.portal
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])
    >>> transaction.commit()


slugify
~~~~~~~

`fapi.slugify` lowercases the input, strips non-word characters and
collapses runs of whitespace, underscores and hyphens into a single
separator (`-` by default), trimming leading/trailing separators::

    >>> fapi.slugify("Hello World")
    'hello-world'

    >>> fapi.slugify("Patient ID #42")
    'patient-id-42'

    >>> fapi.slugify("  --leading and trailing--  ")
    'leading-and-trailing'

    >>> fapi.slugify("Mixed   case_and__underscores")
    'mixed-case-and-underscores'

The separator can be customised or removed::

    >>> fapi.slugify("Hello World", repl="_")
    'hello_world'

    >>> fapi.slugify("Hello World", repl="")
    'helloworld'

fail
~~~~

`fapi.fail` raises a `FHIRAPIError` carrying the requested HTTP
status code::

    >>> fapi.fail("Not Found", status=404)
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not Found

The HTTP status is attached to the exception and applied to the
current request response::

    >>> try:
    ...     fapi.fail("Not Found", status=404)
    ... except FHIRAPIError as e:
    ...     e.status
    404

A default message is used when `None` is passed::

    >>> fapi.fail(None)
    Traceback (most recent call last):
    ...
    FHIRAPIError: Reason not given.


is_uuid / get_uuid
~~~~~~~~~~~~~~~~~~

`fapi.is_uuid` accepts either the canonical dashed form or the
32-char hex form. Anything that can't be parsed into a `uuid.UUID` is
rejected::

    >>> fapi.is_uuid("52f941c6-81a0-51be-b1a6-f92ac079be34")
    True

    >>> fapi.is_uuid("52f941c681a051beb1a6f92ac079be34")
    True

    >>> fapi.is_uuid("not-a-uuid")
    False

    >>> fapi.is_uuid(None)
    False

`fapi.get_uuid` parses either form into a `uuid.UUID`::

    >>> fapi.get_uuid("52f941c6-81a0-51be-b1a6-f92ac079be34")
    UUID('52f941c6-81a0-51be-b1a6-f92ac079be34')

    >>> fapi.get_uuid("52f941c681a051beb1a6f92ac079be34")
    UUID('52f941c6-81a0-51be-b1a6-f92ac079be34')

A `UUID` instance is returned unchanged::

    >>> u = UUID("52f941c6-81a0-51be-b1a6-f92ac079be34")
    >>> fapi.get_uuid(u) is u
    True


Create a plain Patient
~~~~~~~~~~~~~~~~~~~~~~

Most of the remaining helpers operate on content objects, so we first
create a Patient through the core SENAITE API::

    >>> patient = api.create(
    ...     portal.patients, "Patient",
    ...     mrn=u"PAT-001",
    ...     firstname=u"Jane",
    ...     lastname=u"Doe",
    ...     sex=u"f",
    ...     gender=u"f",
    ...     birthdate="1980-01-01",
    ... )
    >>> patient
    <Patient at /plone/patients/...>


get_uid / get_uuid on content
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`fapi.get_uid` returns a 32-char hex UID, and `fapi.get_uuid`
returns the corresponding `uuid.UUID`::

    >>> patient_uid = fapi.get_uid(patient)
    >>> len(patient_uid)
    32
    >>> fapi.is_uuid(patient_uid)
    True
    >>> fapi.get_uuid(patient).hex == patient_uid
    True


get_resource_type
~~~~~~~~~~~~~~~~~

`fapi.get_resource_type` returns the FHIR resource type for a given
thing. For a content object, it is resolved from the object's portal type::

    >>> fapi.get_resource_type(patient)
    'Patient'

It also accepts a catalog brain or a UID resolving to a content object::

    >>> fapi.get_resource_type(patient_uid)
    'Patient'

The lookup is a true reverse of `FHIR_RESOURCE_TO_PORTAL_TYPE` (an immutable
tuple of `(resource_type, portal_type)` pairs), so a portal type resolves
back to its FHIR resource type even when the two names differ. A SENAITE
`Client` maps to a FHIR `Organization`::

    >>> client = api.create(portal.clients, "Client", title="Acme")
    >>> fapi.get_resource_type(client)
    'Organization'

For a FHIR resource, its own `resourceType` is returned::

    >>> a_resource = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "52f941c6-81a0-51be-b1a6-f92ac079be34",
    ... })
    >>> fapi.get_resource_type(a_resource)
    'Patient'

Portal types without a mapping in `FHIR_RESOURCE_TO_PORTAL_TYPE` are
returned unchanged::

    >>> fapi.get_resource_type(portal.clients) == api.get_portal_type(
    ...     portal.clients)
    True

A portal type name is accepted too::

    >>> fapi.get_resource_type("AnalysisRequest")
    'ServiceRequest'


get_portal_type
~~~~~~~~~~~~~~~

`fapi.get_portal_type` is the inverse of `get_resource_type`. For a
content object it returns the object's portal type, and it likewise accepts a
catalog brain or a UID resolving to one::

    >>> fapi.get_portal_type(patient)
    'Patient'

    >>> fapi.get_portal_type(patient_uid)
    'Patient'

For a FHIR resource, the portal type is looked up from its `resourceType`
through `FHIR_RESOURCE_TO_PORTAL_TYPE`, so a FHIR `Organization` resolves
to a SENAITE `Client`::

    >>> org = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "44444444-4444-5444-9444-444444444444",
    ... })
    >>> org["resourceType"] = "Organization"
    >>> fapi.get_portal_type(org)
    'Client'

Resource types without a mapping fall back to the resource type itself::

    >>> org["resourceType"] = "Encounter"
    >>> fapi.get_portal_type(org)
    'Encounter'


is_fhir_content / is_fhir_resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A freshly-created Patient is not yet linked to any external FHIR resource::

    >>> fapi.is_fhir_content(patient)
    False

    >>> fapi.is_fhir_resource(patient)
    False


get_fhir_uid
~~~~~~~~~~~~

`fapi.get_fhir_uid` returns the FHIR UID (hex) of the counterpart resource
of the given object for a resource type, defaulting to the object's own
resource type when none is passed.

For a FHIR resource, its own UID is returned::

    >>> fapi.get_fhir_uid(a_resource) == fapi.get_uid(a_resource)
    True

An object not linked to a separate FHIR resource falls back to its own
SENAITE UID, so a derived resource keeps a stable identity::

    >>> fapi.get_fhir_uid(patient) == fapi.get_uid(patient)
    True

The resource type can be given explicitly; one with no UID associated to the
object returns `None`::

    >>> fapi.get_fhir_uid(patient, resource_type="Patient") == fapi.get_uid(patient)
    True

    >>> fapi.get_fhir_uid(patient, resource_type="Observation") is None
    True


get_fhir_id
~~~~~~~~~~~

`fapi.get_fhir_id` is the canonical dashed UUID form of `get_fhir_uid`
(which returns the UID in hex). For a FHIR resource it returns its own id::

    >>> fapi.get_fhir_id(a_resource)
    '52f941c6-81a0-51be-b1a6-f92ac079be34'

It is the dashed-form counterpart of the hex UID from `get_fhir_uid`::

    >>> fapi.get_uuid(fapi.get_fhir_id(patient)).hex == fapi.get_fhir_uid(patient)
    True

A resource type with no UID associated to the object returns `None`::

    >>> fapi.get_fhir_id(patient, resource_type="Observation") is None
    True


get_fhir_uids
~~~~~~~~~~~~~

`fapi.get_fhir_uids` returns all FHIR UIDs (hex) assigned to a thing,
grouped by resource type. For a FHIR resource it is a single-entry mapping::

    >>> fapi.get_fhir_uids(a_resource) == {"Patient": fapi.get_uid(a_resource)}
    True

For a content object, the object's own UID is injected for both its FHIR
resource type and its portal type. For a Patient the two coincide::

    >>> fapi.get_fhir_uids(patient) == {"Patient": fapi.get_uid(patient)}
    True

When the resource type and the portal type differ, both keys are present: a
`Client` is exposed as a FHIR `Organization`::

    >>> uids = fapi.get_fhir_uids(client)
    >>> sorted(uids.keys())
    ['Client', 'Organization']

    >>> uids["Organization"] == uids["Client"] == fapi.get_uid(client)
    True


to_fhir_resource
~~~~~~~~~~~~~~~~

`fapi.to_fhir_resource` accepts a dict and dispatches to the named
`IFHIRResource` adapter for its `resourceType`::

    >>> data = {
    ...     "resourceType": "Patient",
    ...     "id": "52f941c6-81a0-51be-b1a6-f92ac079be34",
    ...     "name": [{"use": "official", "family": "Roe", "given": ["John"]}],
    ...     "gender": "male",
    ...     "birthDate": "1975-05-20",
    ...     "maritalStatus": {
    ...         "coding": [
    ...             {"code": "M", "display": "Married"},
    ...         ],
    ...     },
    ...     "identifier": [
    ...         {"use": "secondary",
    ...          "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...          "value": "PAT-999"},
    ...     ],
    ... }
    >>> resource = fapi.to_fhir_resource(data)
    >>> isinstance(resource, PatientResource)
    True
    >>> fapi.is_fhir_resource(resource)
    True
    >>> IFHIRResource.providedBy(resource)
    True

The call is idempotent on resources::

    >>> fapi.to_fhir_resource(resource) is resource
    True

A FHIR resource also exposes its UID via the same helpers::

    >>> fapi.get_uid(resource)
    '52f941c681a051beb1a6f92ac079be34'

    >>> fapi.get_uuid(resource)
    UUID('52f941c6-81a0-51be-b1a6-f92ac079be34')

It also accepts a content object and dispatches to the registered
`IContentToFHIR` adapter::

    >>> resource_from_patient = fapi.to_fhir_resource(patient)
    >>> isinstance(resource_from_patient, PatientResource)
    True

    >>> resource_from_patient["resourceType"]
    'Patient'

    >>> resource_from_patient["gender"]
    'female'

And accepts a UID, resolving the matching content first::

    >>> resource_from_uid = fapi.to_fhir_resource(patient_uid)
    >>> isinstance(resource_from_uid, PatientResource)
    True

Empty / falsy input returns `None`::

    >>> fapi.to_fhir_resource(None) is None
    True

    >>> fapi.to_fhir_resource({}) is None
    True

Unsupported or malformed dicts fail unless `default` is provided::

    >>> fapi.to_fhir_resource({"resourceType": "Unsupported"})
    Traceback (most recent call last):
    ...
    FHIRAPIError: Resource type is not supported: Unsupported

    >>> fapi.to_fhir_resource({"resourceType": "Unsupported"},
    ...                       default=None) is None
    True

    >>> fapi.to_fhir_resource({"id": "x"})
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not well formed resource. Resource type is missing

Unknown UIDs fail unless `default` is provided::

    >>> fapi.to_fhir_resource("00000000000000000000000000000000")
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not Found

    >>> fapi.to_fhir_resource("00000000000000000000000000000000",
    ...                       default=None) is None
    True

So do a dict without resource type and an unsupported resource type::

    >>> fapi.to_fhir_resource({"id": "x"}, default=None) is None
    True
    >>> fapi.to_fhir_resource({"resourceType": "Unknown"})
    Traceback (most recent call last):
    ...
    FHIRAPIError: Resource type is not supported: Unknown
    >>> unknown = {"resourceType": "Unknown"}
    >>> fapi.to_fhir_resource(unknown, default=None) is None
    True


to_content_dict
~~~~~~~~~~~~~~~

`fapi.to_content_dict` converts a FHIR resource into a kwargs dict
suitable for `api.create` / `api.edit` via the registered
`IFHIRToContent` adapter::

    >>> content = fapi.to_content_dict(resource)
    >>> content["portal_type"]
    'Patient'
    >>> content["parent_path"]
    '/plone/patients'
    >>> content["mrn"]
    u'PAT-999'
    >>> content["firstname"]
    u'John'
    >>> content["lastname"]
    u'Roe'
    >>> content["sex"]
    u'm'
    >>> content["gender"]
    u'm'
    >>> content["marital_status"]
    u'M'

When no `IFHIRToContent` adapter is registered the call raises
`ValueError` (or returns the supplied default)::

    >>> class _Dummy(object):
    ...     pass
    >>> fapi.to_content_dict(_Dummy())
    Traceback (most recent call last):
    ...
    ValueError: Missing IFHIRToContent adapter for ...

    >>> fapi.to_content_dict(_Dummy(), default=None) is None
    True


can_create_or_update
~~~~~~~~~~~~~~~~~~~~

`fapi.can_create_or_update` tells whether a FHIR resource has a
supported counterpart in this SENAITE deployment. It checks both that
the `resourceType` is in the allow-list and that an `IFHIRToContent`
adapter is registered for it::

    >>> fapi.can_create_or_update(resource)
    True

Resource types outside the allow-list return `False` (no exception)::

    >>> unsupported = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "33333333-3333-5333-9333-333333333333",
    ... })
    >>> unsupported["resourceType"] = "Encounter"
    >>> fapi.can_create_or_update(unsupported)
    False

Non-resources are rejected with `ValueError`::

    >>> fapi.can_create_or_update({"foo": "bar"})
    Traceback (most recent call last):
    ...
    ValueError: Type not supported: <type 'dict'>


link_fhir_resource / get_fhir_storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`fapi.link_fhir_resource` marks an object as `IFHIRContent` and records
the resource's UID in the object's `uids` mapping (keyed by resource type),
plus the serialized payload under `data`, in the FHIR annotation storage.
It is what `create` / `update` use internally::

    >>> fapi.link_fhir_resource(patient, resource)
    >>> fapi.is_fhir_content(patient)
    True
    >>> IFHIRContent.providedBy(patient)
    True
    >>> fapi.get_fhir_uid(patient) == fapi.get_uid(resource)
    True

`fapi.get_fhir_storage` returns the (lazily-created)
`PersistentDict` holding the linked resource's payload::

    >>> storage = fapi.get_fhir_storage(patient)
    >>> sorted(storage.keys())
    ['data', 'uids']

The resource's UID is also tracked in the `uids` mapping, keyed by
resource type, so a single object can hold several FHIR ids per type::

    >>> storage["uids"]["Patient"] == fapi.get_uid(resource)
    True

    >>> storage["data"]["resourceType"]
    'Patient'

The storage is created on first access and re-used afterwards::

    >>> fapi.get_fhir_storage(patient) is storage
    True

`link_fhir_resource` rejects non-resources::

    >>> fapi.link_fhir_resource(patient, {"foo": "bar"})
    Traceback (most recent call last):
    ...
    ValueError: Type not supported: <type 'dict'>


create
~~~~~~

`fapi.create` creates a counterpart content object for the given FHIR
resource and links the two via `link_fhir_resource`. The object gets its
own generated SENAITE UID; the resource's FHIR id is preserved separately in
the object's `uids` mapping, so the two identities stay distinct::

    >>> fresh = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "11111111-1111-5111-9111-111111111111",
    ...     "name": [{"use": "official", "family": "Newman", "given": ["Anne"]}],
    ...     "telecom": [
    ...         {"system": "phone", "value": "+61 3 9000 1234", "use": "home"},
    ...         {"system": "phone", "value": "+61 412 345 678", "use": "mobile"},
    ...     ],
    ...     "gender": "female",
    ...     "birthDate": "1990-06-15",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "PAT-NEW"}],
    ... })
    >>> created = fapi.create(fresh)
    >>> created
    <Patient at /plone/patients/...>

The SENAITE UID is not overwritten; it keeps its own generated value::

    >>> fapi.get_uid(created) == fapi.get_uid(fresh)
    False

The incoming FHIR id is preserved in the annotation storage::

    >>> fapi.get_fhir_uid(created, "Patient") == fapi.get_uid(fresh)
    True

    >>> fapi.get_fhir_uid(created) == fapi.get_uid(fresh)
    True

    >>> fapi.is_fhir_content(created)
    True

    >>> created.getFirstname()
    'Anne'

    >>> created.getLastname()
    'Newman'

    >>> created.getPhone() == "+61 3 9000 1234"
    True

    >>> numbers = created.getAdditionalPhoneNumbers()
    >>> len(numbers)
    1
    >>> numbers[0]["name"] == "mobile"
    True
    >>> numbers[0]["phone"] == "+61 412 345 678"
    True

    >>> transaction.commit()


get_object
~~~~~~~~~~

`fapi.get_object` resolves a FHIR resource into its counterpart SENAITE
content, looking it up through the FHIR catalog by the resource's FHIR UID::

    >>> fapi.get_uid(fapi.get_object(fresh)) == fapi.get_uid(created)
    True

Anything that is not a FHIR resource (a content object, catalog brain or
SENAITE UID) is delegated to the core API::

    >>> resolved = fapi.get_object(fapi.get_uid(created))
    >>> fapi.get_uid(resolved) == fapi.get_uid(created)
    True

A bare FHIR id string that is not a SENAITE UID is resolved too, by searching
the FHIR catalog across all portal types::

    >>> fhir_id = fapi.get_uid(fresh)
    >>> resolved = fapi.get_object(fhir_id)
    >>> fapi.get_uid(resolved) == fapi.get_uid(created)
    True

An unknown FHIR resource raises unless a default is provided::

    >>> orphan = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "99999999-9999-5999-9999-999999999999",
    ... })
    >>> fapi.get_object(orphan)
    Traceback (most recent call last):
    ...
    FHIRAPIError: No object found for FHIR UID 99999999999959999999999999999999

    >>> fapi.get_object(orphan, default=None) is None
    True

So does anything that is neither a SENAITE UID nor a FHIR id::

    >>> fapi.get_object("not-a-uid")
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not Found
    >>> fapi.get_object("not-a-uid", default=None) is None
    True


find_object_for
~~~~~~~~~~~~~~~

`fapi.find_object_for` resolves the SENAITE counterpart of a FHIR resource:
first by an exact FHIR-UID match (via `get_object`), then via the
resource's `IContentFinder` adapter -- matching by business keys -- when
the UID match misses::

    >>> fapi.get_uid(fapi.find_object_for(fresh)) == fapi.get_uid(created)
    True

Non-resources are rejected::

    >>> fapi.find_object_for({"foo": "bar"})
    Traceback (most recent call last):
    ...
    FHIRAPIError: Type is not supported: {'foo': 'bar'}
    >>> fapi.find_object_for({"foo": "bar"}, default=None) is None
    True

A resource with an unknown FHIR id is resolved by its `IContentFinder`, e.g.
a Patient by its MRN::

    >>> by_mrn = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "55555555-5555-5555-9555-555555555555",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "PAT-001"}],
    ... })
    >>> fapi.find_object_for(by_mrn) == patient
    True

Nothing is found for a resource type without finder::

    >>> fapi.find_object_for(fapi.to_fhir_resource({
    ...     "resourceType": "Device",
    ...     "id": "66666666-6666-5666-9666-666666666666",
    ... })) is None
    True


search_by_fhir_uid
~~~~~~~~~~~~~~~~~~

`fapi.search_by_fhir_uid` looks up the FHIR catalog by its `fhir_uids`
index and returns the matching brains::

    >>> brains = fapi.search_by_fhir_uid(fapi.get_uid(fresh))
    >>> fapi.get_uid(brains[0]) == fapi.get_uid(created)
    True

A dashed FHIR id is harmonized to a hex UID, so either form works. With
`as_brains=False` the matching objects are woken up and returned::

    >>> objs = fapi.search_by_fhir_uid(
    ...     fapi.get_fhir_id(created), "Patient", as_brains=False)
    >>> fapi.get_uid(objs[0]) == fapi.get_uid(created)
    True

An unknown UID yields an empty result::

    >>> len(fapi.search_by_fhir_uid("99999999-9999-5999-9999-999999999999"))
    0


get_object_by_fhir_uid
~~~~~~~~~~~~~~~~~~~~~~~

`fapi.get_object_by_fhir_uid` resolves the object holding a FHIR UID through
the FHIR catalog. Either a hex UID or a dashed FHIR id works::

    >>> obj = fapi.get_object_by_fhir_uid(fapi.get_uid(fresh), "Patient")
    >>> fapi.get_uid(obj) == fapi.get_uid(created)
    True

    >>> obj = fapi.get_object_by_fhir_uid(fapi.get_fhir_id(created), "Patient")
    >>> fapi.get_uid(obj) == fapi.get_uid(created)
    True

The `portal_type` is optional; when omitted, all portal types are searched::

    >>> obj = fapi.get_object_by_fhir_uid(fapi.get_uid(fresh))
    >>> fapi.get_uid(obj) == fapi.get_uid(created)
    True

When no object holds the UID it raises, unless a default is given::

    >>> fapi.get_object_by_fhir_uid(
    ...     "99999999-9999-5999-9999-999999999999")
    Traceback (most recent call last):
    ...
    FHIRAPIError: No object found for FHIR UID 99999999999959999999999999999999

    >>> fapi.get_object_by_fhir_uid(
    ...     "99999999-9999-5999-9999-999999999999", default=None) is None
    True


set_fhir_uids
~~~~~~~~~~~~~

`fapi.set_fhir_uids` persists FHIR UIDs against an object, keyed by resource
type, and indexes it in the FHIR catalog so it can be found again with
`search_by_fhir_uid`::

    >>> linked = api.create(portal.patients, "Patient", mrn=u"PAT-UIDS")
    >>> specimen_uid = fapi.generate_UUID().hex
    >>> fapi.set_fhir_uids(linked, Specimen=specimen_uid)

The UID is now part of the object's FHIR UIDs, keyed by resource type::

    >>> fapi.get_fhir_uid(linked, "Specimen") == specimen_uid
    True

And the object is resolvable through the FHIR catalog::

    >>> brains = fapi.search_by_fhir_uid(specimen_uid, "Patient")
    >>> fapi.get_uid(brains[0]) == fapi.get_uid(linked)
    True

Stored entries for other resource types are kept; passing a new resource type
adds to the mapping rather than replacing it::

    >>> service_request_uid = fapi.generate_UUID().hex
    >>> fapi.set_fhir_uids(linked, ServiceRequest=service_request_uid)
    >>> sorted(fapi.get_fhir_uids(linked).keys())
    ['Patient', 'ServiceRequest', 'Specimen']


update
~~~~~~

`fapi.update` re-applies the resource fields to an already-resolved
content object (the caller resolves it first, e.g. via `get_object` or
`find_object_for`)::

    >>> fresh["name"] = [
    ...     {"use": "official", "family": "Smith", "given": ["Anne"]},
    ... ]
    >>> fresh["telecom"] = [
    ...     {"system": "phone", "value": "+61-3-9111-2222", "use": "home"},
    ... ]
    >>> obj = fapi.get_object(fresh)
    >>> updated = fapi.update(obj, fresh)
    >>> fapi.get_uid(updated) == fapi.get_uid(created)
    True
    >>> updated.getLastname()
    'Smith'
    >>> updated.getPhone()
    '+61-3-9111-2222'

Archetypes-based objects, such as the Client, are updated through the
mutators of their fields. The keys of the content dict that are not fields
are skipped::

    >>> organization = fapi.to_fhir_resource({
    ...     "resourceType": "Organization",
    ...     "id": "77777777-7777-5777-9777-777777777777",
    ...     "name": "Acme Laboratories",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/"
    ...                   "organization-external-id",
    ...         "value": "ACME"}],
    ...     "contact": [{"address": {"line": ["1 Main Street"]}}],
    ... })
    >>> sorted(fapi.to_content_dict(organization).keys())
    ['ClientID', 'Name', 'PhysicalAddress', 'parent_path', 'portal_type']
    >>> fapi.update(client, organization) == client
    True
    >>> client.getName(), client.getClientID()
    ('Acme Laboratories', 'ACME')

The Client is now linked to the Organization, so it is found by the FHIR id of
the Organization, even if it is stored under the resource type and not the
portal type::

    >>> fapi.get_fhir_uids(client)["Organization"]
    '77777777777757779777777777777777'
    >>> fapi.get_object_by_fhir_uid(organization["id"]) == client
    True


create (brand-new resource)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A brand-new resource produces a new content object::

    >>> brand_new = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "22222222-2222-5222-9222-222222222222",
    ...     "name": [{"use": "official", "family": "Mint", "given": ["Fresh"]}],
    ...     "gender": "male",
    ...     "birthDate": "2000-01-01",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "PAT-MINT"}],
    ... })
    >>> minted = fapi.create(brand_new)
    >>> fapi.is_fhir_content(minted)
    True
    >>> minted.getLastname()
    'Mint'

A Patient carrying only a `mobile` phone stores that number in the
additional phone numbers field::

    >>> mobile_only = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "33333333-3333-5333-9333-333333333333",
    ...     "name": [{"use": "official", "family": "Mobile", "given": ["Only"]}],
    ...     "gender": "female",
    ...     "birthDate": "1999-03-22",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "PAT-MOBILE-ONLY"}],
    ...     "telecom": [{
    ...         "system": "phone",
    ...         "value": "+1-345-555-0193",
    ...         "use": "mobile",
    ...     }],
    ... })
    >>> mobile_patient = fapi.create(mobile_only)
    >>> mobile_patient.getPhone()
    ''
    >>> mobile_numbers = mobile_patient.getAdditionalPhoneNumbers()
    >>> len(mobile_numbers)
    1
    >>> mobile_numbers[0]["name"] == "mobile"
    True
    >>> mobile_numbers[0]["phone"] == "+1-345-555-0193"
    True

The FHIR id is stored separately; the SENAITE UID is distinct::

    >>> fapi.get_fhir_uid(minted, "Patient") == fapi.get_uid(brand_new)
    True
    >>> fapi.get_uid(minted) == fapi.get_uid(brand_new)
    False


Duplicate create
~~~~~~~~~~~~~~~~

Calling `create` a second time for the same resource fails, because
the counterpart already exists::

    >>> fapi.create(brand_new)
    Traceback (most recent call last):
    ...
    ValueError: Counterpart object already exists: <PatientResource ...>


get_system_code
~~~~~~~~~~~~~~~

`fapi.get_system_code` returns the coding system URL configured for a
resource type::

    >>> fapi.get_system_code("Specimen")
    'http://snomed.info/sct'

Unknown types raise unless a default is provided::

    >>> fapi.get_system_code("Unknown")
    Traceback (most recent call last):
    ...
    ValueError: No system code defined for Unknown

    >>> fapi.get_system_code("Unknown", default=None) is None
    True


generate_UUID
~~~~~~~~~~~~~

`fapi.generate_UUID` returns a fresh `uuid.UUID`::

    >>> generated = fapi.generate_UUID()
    >>> isinstance(generated, UUID)
    True
    >>> fapi.generate_UUID() != generated
    True


to_naming_system_url
~~~~~~~~~~~~~~~~~~~~

`fapi.to_naming_system_url` returns the canonical URI of a NamingSystem id,
as carried by `Identifier.system`::

    >>> fapi.to_naming_system_url("patient-mrn")
    'https://fhir.senaite.org/NamingSystem/patient-mrn'


validate_internal_identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Identifiers to build the incoming resources of the tests below::

    >>> from senaite.fhir.exceptions import IdentifierValidationError
    >>> def identifier(use, system_id, value):
    ...     ident = {"value": value}
    ...     if use:
    ...         ident["use"] = use
    ...     if system_id:
    ...         ident["system"] = fapi.to_naming_system_url(system_id)
    ...     return ident
    >>> def incoming(resource_type, *identifiers):
    ...     return fapi.to_fhir_resource({
    ...         "resourceType": resource_type,
    ...         "identifier": list(identifiers),
    ...     })
    >>> mrn = identifier("secondary", "patient-mrn", "MRN-1")
    >>> internal = identifier("usual", "patient-id", "P-1")

`fapi.validate_internal_identifier` rejects an internal (`usual`)
identifier, which SENAITE assigns only after creation::

    >>> fapi.validate_internal_identifier(incoming("Patient", mrn))
    >>> fapi.validate_internal_identifier(incoming("Patient", mrn, internal))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Cannot specify usual identifier externally in
    incoming Patient:P-1


validate_external_identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`fapi.validate_external_identifier` accepts the external identifiers with
`use="secondary"` and the NamingSystem of the resource type, and skips the
internal one, which is validated by `validate_internal_identifier`::

    >>> fapi.validate_external_identifier(incoming("Patient", mrn))
    >>> fapi.validate_external_identifier(incoming("Patient", internal, mrn))

Any other identifier is rejected, whatever its position::

    >>> fapi.validate_external_identifier(incoming(
    ...     "Patient", mrn, identifier(None, "patient-mrn", "MRN-2")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Missing identifier use in Patient

    >>> fapi.validate_external_identifier(incoming(
    ...     "Patient", identifier("official", "patient-mrn", "MRN-2")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Unsupported identifier use in Patient: official

    >>> fapi.validate_external_identifier(incoming(
    ...     "Patient", identifier("secondary", None, "MRN-2")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Missing identifier system in Patient

    >>> fapi.validate_external_identifier(incoming(
    ...     "Patient",
    ...     identifier("secondary", "practitioner-external-id", "X")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Unsupported identifier system in Patient:
    https://fhir.senaite.org/NamingSystem/practitioner-external-id

The error points to the identifiers of the resource::

    >>> try:
    ...     fapi.validate_external_identifier(incoming(
    ...         "Patient", identifier("secondary", None, "MRN-2")))
    ... except IdentifierValidationError as e:
    ...     e.code, e.expression
    ('invalid', ['Patient.identifier'])


validate_no_identifier
~~~~~~~~~~~~~~~~~~~~~~

`fapi.validate_no_identifier` rejects any identifier at all, whatever its
`use`. It is for the resource types that support none, such as the
ServiceRequest::

    >>> fapi.validate_no_identifier(incoming("ServiceRequest"))
    >>> fapi.validate_no_identifier(incoming(
    ...     "ServiceRequest", identifier("secondary", "sample-id", "S-1")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Cannot specify any identifier in ServiceRequest


validate_identifiers
~~~~~~~~~~~~~~~~~~~~

`fapi.validate_identifiers` applies the identifiers pattern of the resource
type. A type with an external NamingSystem rejects internal identifiers and
foreign external ones::

    >>> fapi.validate_identifiers(incoming("Patient", mrn))
    >>> fapi.validate_identifiers(incoming("Patient", internal))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Cannot specify usual identifier externally in
    incoming Patient:P-1
    >>> fapi.validate_identifiers(incoming(
    ...     "Patient", identifier("secondary", "client-sample-id", "C-1")))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Unsupported identifier system in Patient:
    https://fhir.senaite.org/NamingSystem/client-sample-id

A type without one rejects any identifier::

    >>> fapi.validate_identifiers(incoming("ServiceRequest"))
    >>> fapi.validate_identifiers(incoming("ServiceRequest", mrn))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Cannot specify any identifier in ServiceRequest


validate
~~~~~~~~

`fapi.validate` applies the validation rules of the `IFHIRToContent`
converter of the resource, which include the identifiers pattern::

    >>> fapi.validate(incoming("Patient", mrn))
    >>> fapi.validate(incoming("Patient", internal))
    Traceback (most recent call last):
    ...
    IdentifierValidationError: Cannot specify usual identifier externally in
    incoming Patient:P-1

A resource without converter cannot be validated::

    >>> fapi.validate(fapi.to_fhir_resource(
    ...     {"resourceType": "Bundle", "id": "b-1", "type": "transaction"}))
    Traceback (most recent call last):
    ...
    ValueError: Missing IFHIRToContent adapter for <...>


validate_no_logical_id
~~~~~~~~~~~~~~~~~~~~~~

`fapi.validate_no_logical_id` rejects a bundle entry whose resource carries
a logical id: entries are identified by the placeholder of their `fullUrl`::

    >>> def bundle_with(**resource):
    ...     resource.setdefault("resourceType", "Patient")
    ...     return fapi.to_fhir_resource({
    ...         "resourceType": "Bundle",
    ...         "id": "b-1",
    ...         "type": "transaction",
    ...         "entry": [{
    ...             "fullUrl": "urn:uuid:9c9e7a3e-3b9e-4a5c-9f3d-2f6b1a0c4d11",
    ...             "resource": resource,
    ...         }],
    ...     })
    >>> fapi.validate_no_logical_id(bundle_with().entry[0])

    >>> placeholder = "9c9e7a3e-3b9e-4a5c-9f3d-2f6b1a0c4d11"
    >>> fapi.validate_no_logical_id(bundle_with(id=placeholder).entry[0])
    Traceback (most recent call last):
    ...
    LogicalIdValidationError: Resource.id must not be supplied in a POST
    transaction entry. SENAITE generates all logical IDs; see
    identifiers.html#general-pattern.

Nor is one whose entry is not in its bundle::

    >>> stray = bundle_with().entry[0]
    >>> stray["id"] = "another-id"
    >>> fapi.validate_no_logical_id(stray)

A resource outside a bundle is not checked::

    >>> fapi.validate_no_logical_id(incoming("Patient", mrn))


get_secondary_resources
~~~~~~~~~~~~~~~~~~~~~~~

`fapi.get_secondary_resources` returns the secondary resources a converter
hands over in the content dict, under `SECONDARY_RESOURCES_KEY`, as a list.
A single resource is accepted too, and anything that is not a resource is
skipped::

    >>> from senaite.fhir.config import SECONDARY_RESOURCES_KEY
    >>> specimen = fapi.to_fhir_resource({
    ...     "resourceType": "Specimen",
    ...     "id": "3f2c1b7a-8d4e-4f6a-9b2c-1e5d7a9c0b3f",
    ...     "extension": [{
    ...         "url": "https://example.org/StructureDefinition/keep-me",
    ...         "valueString": "kept",
    ...     }],
    ... })
    >>> fapi.get_secondary_resources({SECONDARY_RESOURCES_KEY: specimen}) == [
    ...     specimen]
    True
    >>> fapi.get_secondary_resources(
    ...     {SECONDARY_RESOURCES_KEY: [specimen, "not a resource"]}) == [
    ...     specimen]
    True
    >>> fapi.get_secondary_resources({})
    []


A Sample
~~~~~~~~

The functions below work with a Sample and its analyses::

    >>> from DateTime import DateTime
    >>> from bika.lims.utils.analysisrequest import create_analysisrequest
    >>> from bika.lims.workflow import doActionFor as do_action_for
    >>> setup = portal.setup
    >>> contact = api.create(client, "Contact",
    ...                      Firstname="Rita", Lastname="Mohale")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Water", Prefix="W")
    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Boss")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Chemistry", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="Metals", Department=department)
    >>> Cu = api.create(portal.bika_setup.bika_analysisservices,
    ...                 "AnalysisService", title="Copper", Keyword="Cu",
    ...                 Category=category.UID())
    >>> values = {
    ...     "Client": client.UID(),
    ...     "Contact": contact.UID(),
    ...     "DateSampled": DateTime().strftime("%Y-%m-%d"),
    ...     "SampleType": sampletype.UID(),
    ...     "ClientSampleID": "EXT-001",
    ... }
    >>> sample = create_analysisrequest(client, self.request, values,
    ...                                 [Cu.UID()])
    >>> analysis = sample.getAnalyses(full_objects=True)[0]
    >>> transaction.commit()


is_reportable
~~~~~~~~~~~~~

`fapi.is_reportable` tells whether an analysis is exposed in the FHIR
results: only once it has a submitted result::

    >>> fapi.is_reportable(analysis)
    False
    >>> success = do_action_for(sample, "receive")
    >>> analysis.setResult("12")
    >>> success = do_action_for(analysis, "submit")
    >>> api.get_review_status(analysis)
    'to_be_verified'
    >>> fapi.is_reportable(analysis)
    True

A hidden analysis is never reported::

    >>> analysis.setHidden(True)
    >>> fapi.is_reportable(analysis)
    False
    >>> analysis.setHidden(False)

Neither is one for internal use::

    >>> from bika.lims.interfaces import IInternalUse
    >>> from zope.interface import alsoProvides
    >>> from zope.interface import noLongerProvides
    >>> alsoProvides(analysis, IInternalUse)
    >>> fapi.is_reportable(analysis)
    False
    >>> noLongerProvides(analysis, IInternalUse)
    >>> fapi.is_reportable(analysis)
    True


get_available_reasons
~~~~~~~~~~~~~~~~~~~~~

`fapi.get_available_reasons` returns the rejection reasons of the setup::

    >>> fapi.get_available_reasons()
    []
    >>> api.get_senaite_setup().setRejectionReasons(["Hemolyzed", "Clotted"])
    >>> fapi.get_available_reasons()
    [u'Hemolyzed', u'Clotted']


to_fhir_action_resource
~~~~~~~~~~~~~~~~~~~~~~~

`fapi.to_fhir_action_resource` converts a transition of an object to the
FHIR resource that represents it, e.g. the revocation of a Sample::

    >>> revoked = fapi.to_fhir_action_resource(sample, "revoke")
    >>> revoked["resourceType"], revoked["status"]
    ('ServiceRequest', 'revoked')
    >>> revoked["id"] == str(fapi.get_uuid(sample))
    True

An action without converter raises, unless a default is provided::

    >>> fapi.to_fhir_action_resource(sample, "unknown")
    Traceback (most recent call last):
    ...
    FHIRAPIError: Action is not supported: unknown for <AnalysisRequest at ...>
    >>> fapi.to_fhir_action_resource(sample, "unknown", default=None) is None
    True


store_fhir_resource / get_stored_fhir_resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`fapi.store_fhir_resource` stores a secondary resource (one with no
counterpart content type, such as the Specimen) against an object, and
`fapi.get_stored_fhir_resource` returns it, or None::

    >>> fapi.get_stored_fhir_resource(sample, "Specimen") is None
    True
    >>> fapi.store_fhir_resource(sample, specimen)
    >>> stored = fapi.get_stored_fhir_resource(sample, "Specimen")
    >>> stored["resourceType"], stored["id"] == specimen["id"]
    ('Specimen', True)
    >>> stored == fapi.get_stored_fhir_resource(
    ...     api.get_uid(sample), "Specimen")
    True

The object is also found by the FHIR id of its secondary resource::

    >>> fapi.get_object_by_fhir_uid(specimen["id"]) == sample
    True


get_server_owned_elements
~~~~~~~~~~~~~~~~~~~~~~~~~

`fapi.get_server_owned_elements` returns the elements of a secondary resource
that SENAITE owns (`SERVER_OWNED_ELEMENTS`), synthesized from the object::

    >>> owned = fapi.get_server_owned_elements(sample, "Specimen")
    >>> sorted(owned.keys())
    ['extension', 'identifier', 'status']
    >>> owned["identifier"][0]["value"] == api.get_id(sample)
    True

Nothing for the types without elements owned by SENAITE, nor for an object
that cannot be represented as the given type::

    >>> fapi.get_server_owned_elements(sample, "ServiceRequest")
    {}
    >>> fapi.get_server_owned_elements(client, "Specimen")
    {}


merge_extensions
~~~~~~~~~~~~~~~~

`fapi.merge_extensions` puts the extensions owned by SENAITE in place of the
ones with the same url, and keeps the rest::

    >>> theirs = [{"url": "a", "valueString": "theirs"},
    ...           {"url": "b", "valueString": "stale"}]
    >>> ours = [{"url": "b", "valueString": "live"}]
    >>> fapi.merge_extensions(theirs, ours)
    [{'url': 'a', 'valueString': 'theirs'},
     {'url': 'b', 'valueString': 'live'}]
    >>> fapi.merge_extensions(None, ours)
    [{'url': 'b', 'valueString': 'live'}]


get_fhir_resource
~~~~~~~~~~~~~~~~~

`fapi.get_fhir_resource` returns a stored secondary resource completed with
the elements SENAITE owns: the consumer's extension is kept, and the
identifiers and status are the live ones::

    >>> served = fapi.get_fhir_resource(sample, "Specimen")
    >>> served["id"] == specimen["id"]
    True
    >>> served["identifier"][0]["value"] == api.get_id(sample)
    True
    >>> served["status"]
    'available'
    >>> [extension["url"] for extension in served["extension"]]
    ['https://example.org/StructureDefinition/keep-me',
     'https://fhir.senaite.org/StructureDefinition/SenaiteSpecimenBarcode']

Any other resource is synthesized from the object through its
`IContentToFHIR` adapter. The resource type defaults to the one of the
object::

    >>> synthesized = fapi.get_fhir_resource(patient)
    >>> synthesized["resourceType"], synthesized["id"] == fapi.get_fhir_id(
    ...     patient)
    ('Patient', True)

An object without adapter for the resource type, or an unknown object,
raises unless a default is provided::

    >>> fapi.get_fhir_resource(client)
    Traceback (most recent call last):
    ...
    FHIRAPIError: Type is not supported: <Client at ...>
    >>> fapi.get_fhir_resource(client, default=None) is None
    True
    >>> fapi.get_fhir_resource("unknown")
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not Found
    >>> fapi.get_fhir_resource("unknown", default=None) is None
    True


create / update (a ServiceRequest)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A ServiceRequest is created as a Sample, and its Specimen, which has no
counterpart content type, is linked to it as a secondary resource. The
resources of a bundle are created or updated in dependency order, as the
POST route does::

    >>> import json
    >>> from pkg_resources import resource_string
    >>> lab = api.create(portal.clients, "Client", Name="Royal Melbourne",
    ...                  ClientID="ORG-RMH-MEL")
    >>> serum = api.create(setup.sampletypes, "SampleType",
    ...                    title="Serum specimen", Prefix="SER")
    >>> for code in ["1742-6", "1920-8", "6768-6", "1975-2",
    ...              "1968-7", "2885-2", "1751-7", "5902-2"]:
    ...     service = api.create(
    ...         portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...         title="LFT %s" % code, Keyword="LFT%s" % code.replace("-", ""),
    ...         Category=category.UID(), ProtocolID=code)
    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = fapi.to_fhir_resource(json.loads(raw))
    >>> for resource in bundle.entry:
    ...     if not fapi.can_create_or_update(resource):
    ...         continue
    ...     obj = fapi.find_object_for(resource)
    ...     if obj:
    ...         obj = fapi.update(obj, resource)
    ...     else:
    ...         obj = fapi.create(resource)
    >>> request_sample = obj
    >>> api.get_portal_type(request_sample)
    'AnalysisRequest'
    >>> api.get_parent(request_sample) == lab
    True

The Specimen of the bundle is linked to the Sample::

    >>> specimen_resource = [r for r in bundle.entry
    ...                      if r.resourceType == "Specimen"][0]
    >>> fapi.get_stored_fhir_resource(request_sample, "Specimen")["id"] == (
    ...     specimen_resource["id"])
    True

Updating the Sample with the same ServiceRequest links it again::

    >>> service_request = [r for r in bundle.entry
    ...                    if r.resourceType == "ServiceRequest"][0]
    >>> fapi.update(request_sample, service_request) == request_sample
    True
    >>> fapi.get_object(service_request) == request_sample
    True
    >>> fapi.get_object_by_fhir_uid(specimen_resource["id"]) == request_sample
    True


Invalid bearer tokens are rejected before the search runs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every FHIR search endpoint must reject an invalid bearer token before route
handling. An otherwise successful empty Bundle could cause a polling client to
advance its `_lastUpdated` cursor and miss subsequent data. This covers the
specialised polling searches and the generic resource search route::

    >>> import json
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> search_paths = [
    ...     "Device?_lastUpdated=gt2026-07-20T03:49:22-05:00",
    ...     "DiagnosticReport?_lastUpdated=gt2026-07-20T03:49:22-05:00",
    ...     "ServiceRequest?_lastUpdated=gt2026-07-20T03:49:22-05:00",
    ...     "Specimen?_lastUpdated=gt2026-07-20T03:49:22-05:00",
    ...     "Patient?_lastUpdated=gt2026-07-20T03:49:22-05:00",
    ... ]
    >>> for path in search_paths:
    ...     anonymous_browser = self.getBrowser(loggedIn=False)
    ...     anonymous_browser.raiseHttpErrors = False
    ...     anonymous_browser.addHeader("Authorization", "Bearer z")
    ...     anonymous_browser.open("{}/{}".format(fhir_url, path))
    ...     assert anonymous_browser.headers["Status"] == "401 Unauthorized"
    ...     error = json.loads(anonymous_browser.contents)
    ...     assert error["resourceType"] == "OperationOutcome"
    ...     issue = error["issue"][0]
    ...     assert issue["severity"] == "error"
    ...     assert issue["code"] == "security"
    ...     details = issue["details"]
    ...     assert details["text"] == "Invalid or expired authentication token"
