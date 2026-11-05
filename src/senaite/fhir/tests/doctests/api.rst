SENAITE FHIR API
----------------

This doctest exercises the helpers exposed in ``senaite.fhir.api``. The
package-level convention is to alias it as ``fapi`` so it can co-exist
with the core SENAITE API which is imported as ``api``::

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

``fapi.slugify`` lowercases the input, strips non-word characters and
collapses runs of whitespace, underscores and hyphens into a single
separator (``-`` by default), trimming leading/trailing separators::

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

``fapi.fail`` raises a ``FHIRAPIError`` carrying the requested HTTP
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

A default message is used when ``None`` is passed::

    >>> fapi.fail(None)
    Traceback (most recent call last):
    ...
    FHIRAPIError: Reason not given.


is_uuid / get_uuid
~~~~~~~~~~~~~~~~~~

``fapi.is_uuid`` accepts either the canonical dashed form or the
32-char hex form. Anything that can't be parsed into a ``uuid.UUID`` is
rejected::

    >>> fapi.is_uuid("52f941c6-81a0-51be-b1a6-f92ac079be34")
    True

    >>> fapi.is_uuid("52f941c681a051beb1a6f92ac079be34")
    True

    >>> fapi.is_uuid("not-a-uuid")
    False

    >>> fapi.is_uuid(None)
    False

``fapi.get_uuid`` parses either form into a ``uuid.UUID``::

    >>> fapi.get_uuid("52f941c6-81a0-51be-b1a6-f92ac079be34")
    UUID('52f941c6-81a0-51be-b1a6-f92ac079be34')

    >>> fapi.get_uuid("52f941c681a051beb1a6f92ac079be34")
    UUID('52f941c6-81a0-51be-b1a6-f92ac079be34')

A ``UUID`` instance is returned unchanged::

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

``fapi.get_uid`` returns a 32-char hex UID, and ``fapi.get_uuid``
returns the corresponding ``uuid.UUID``::

    >>> patient_uid = fapi.get_uid(patient)
    >>> len(patient_uid)
    32
    >>> fapi.is_uuid(patient_uid)
    True
    >>> fapi.get_uuid(patient).hex == patient_uid
    True


get_resource_type
~~~~~~~~~~~~~~~~~

``fapi.get_resource_type`` returns the FHIR resource type for a given
thing. For a content object, it is resolved from the object's portal type::

    >>> fapi.get_resource_type(patient)
    'Patient'

It also accepts a catalog brain or a UID resolving to a content object::

    >>> fapi.get_resource_type(patient_uid)
    'Patient'

The lookup is a true reverse of ``FHIR_RESOURCE_TO_PORTAL_TYPE`` (an immutable
tuple of ``(resource_type, portal_type)`` pairs), so a portal type resolves
back to its FHIR resource type even when the two names differ. A SENAITE
``Client`` maps to a FHIR ``Organization``::

    >>> client = api.create(portal.clients, "Client", title="Acme")
    >>> fapi.get_resource_type(client)
    'Organization'

For a FHIR resource, its own ``resourceType`` is returned::

    >>> a_resource = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "52f941c6-81a0-51be-b1a6-f92ac079be34",
    ... })
    >>> fapi.get_resource_type(a_resource)
    'Patient'

Portal types without a mapping in ``FHIR_RESOURCE_TO_PORTAL_TYPE`` are
returned unchanged::

    >>> fapi.get_resource_type(portal.clients) == api.get_portal_type(
    ...     portal.clients)
    True


get_portal_type
~~~~~~~~~~~~~~~

``fapi.get_portal_type`` is the inverse of ``get_resource_type``. For a
content object it returns the object's portal type, and it likewise accepts a
catalog brain or a UID resolving to one::

    >>> fapi.get_portal_type(patient)
    'Patient'

    >>> fapi.get_portal_type(patient_uid)
    'Patient'

For a FHIR resource, the portal type is looked up from its ``resourceType``
through ``FHIR_RESOURCE_TO_PORTAL_TYPE``, so a FHIR ``Organization`` resolves
to a SENAITE ``Client``::

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

``fapi.get_fhir_uid`` returns the FHIR UID (hex) of the counterpart resource
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
object returns ``None``::

    >>> fapi.get_fhir_uid(patient, resource_type="Patient") == fapi.get_uid(patient)
    True

    >>> fapi.get_fhir_uid(patient, resource_type="Observation") is None
    True


get_fhir_id
~~~~~~~~~~~

``fapi.get_fhir_id`` is the canonical dashed UUID form of ``get_fhir_uid``
(which returns the UID in hex). For a FHIR resource it returns its own id::

    >>> fapi.get_fhir_id(a_resource)
    '52f941c6-81a0-51be-b1a6-f92ac079be34'

It is the dashed-form counterpart of the hex UID from ``get_fhir_uid``::

    >>> fapi.get_uuid(fapi.get_fhir_id(patient)).hex == fapi.get_fhir_uid(patient)
    True

A resource type with no UID associated to the object returns ``None``::

    >>> fapi.get_fhir_id(patient, resource_type="Observation") is None
    True


get_fhir_uids
~~~~~~~~~~~~~

``fapi.get_fhir_uids`` returns all FHIR UIDs (hex) assigned to a thing,
grouped by resource type. For a FHIR resource it is a single-entry mapping::

    >>> fapi.get_fhir_uids(a_resource) == {"Patient": fapi.get_uid(a_resource)}
    True

For a content object, the object's own UID is injected for both its FHIR
resource type and its portal type. For a Patient the two coincide::

    >>> fapi.get_fhir_uids(patient) == {"Patient": fapi.get_uid(patient)}
    True

When the resource type and the portal type differ, both keys are present: a
``Client`` is exposed as a FHIR ``Organization``::

    >>> uids = fapi.get_fhir_uids(client)
    >>> sorted(uids.keys())
    ['Client', 'Organization']

    >>> uids["Organization"] == uids["Client"] == fapi.get_uid(client)
    True


to_fhir_resource
~~~~~~~~~~~~~~~~

``fapi.to_fhir_resource`` accepts a dict and dispatches to the named
``IFHIRResource`` adapter for its ``resourceType``::

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
``IContentToFHIR`` adapter::

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

Empty / falsy input returns ``None``::

    >>> fapi.to_fhir_resource(None) is None
    True

    >>> fapi.to_fhir_resource({}) is None
    True

Unsupported or malformed dicts fail unless ``default`` is provided::

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

Unknown UIDs fail unless ``default`` is provided::

    >>> fapi.to_fhir_resource("00000000000000000000000000000000")
    Traceback (most recent call last):
    ...
    FHIRAPIError: Not Found

    >>> fapi.to_fhir_resource("00000000000000000000000000000000",
    ...                       default=None) is None
    True


to_content_dict
~~~~~~~~~~~~~~~

``fapi.to_content_dict`` converts a FHIR resource into a kwargs dict
suitable for ``api.create`` / ``api.edit`` via the registered
``IFHIRToContent`` adapter::

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

When no ``IFHIRToContent`` adapter is registered the call raises
``ValueError`` (or returns the supplied default)::

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

``fapi.can_create_or_update`` tells whether a FHIR resource has a
supported counterpart in this SENAITE deployment. It checks both that
the ``resourceType`` is in the allow-list and that an ``IFHIRToContent``
adapter is registered for it::

    >>> fapi.can_create_or_update(resource)
    True

Resource types outside the allow-list return ``False`` (no exception)::

    >>> unsupported = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "33333333-3333-5333-9333-333333333333",
    ... })
    >>> unsupported["resourceType"] = "Encounter"
    >>> fapi.can_create_or_update(unsupported)
    False

Non-resources are rejected with ``ValueError``::

    >>> fapi.can_create_or_update({"foo": "bar"})
    Traceback (most recent call last):
    ...
    ValueError: Type not supported: <type 'dict'>


link_fhir_resource / get_fhir_storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``fapi.link_fhir_resource`` marks an object as ``IFHIRContent`` and records
the resource's UID in the object's ``uids`` mapping (keyed by resource type),
plus the serialized payload under ``data``, in the FHIR annotation storage.
It is what ``create`` / ``update`` use internally::

    >>> fapi.link_fhir_resource(patient, resource)
    >>> fapi.is_fhir_content(patient)
    True
    >>> IFHIRContent.providedBy(patient)
    True
    >>> fapi.get_fhir_uid(patient) == fapi.get_uid(resource)
    True

``fapi.get_fhir_storage`` returns the (lazily-created)
``PersistentDict`` holding the linked resource's payload::

    >>> storage = fapi.get_fhir_storage(patient)
    >>> sorted(storage.keys())
    ['data', 'uids']

The resource's UID is also tracked in the ``uids`` mapping, keyed by
resource type, so a single object can hold several FHIR ids per type::

    >>> storage["uids"]["Patient"] == fapi.get_uid(resource)
    True

    >>> storage["data"]["resourceType"]
    'Patient'

The storage is created on first access and re-used afterwards::

    >>> fapi.get_fhir_storage(patient) is storage
    True

``link_fhir_resource`` rejects non-resources::

    >>> fapi.link_fhir_resource(patient, {"foo": "bar"})
    Traceback (most recent call last):
    ...
    ValueError: Type not supported: <type 'dict'>


create
~~~~~~

``fapi.create`` creates a counterpart content object for the given FHIR
resource and links the two via ``link_fhir_resource``. The object gets its
own generated SENAITE UID; the resource's FHIR id is preserved separately in
the object's ``uids`` mapping, so the two identities stay distinct::

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

``fapi.get_object`` resolves a FHIR resource into its counterpart SENAITE
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


find_object_for
~~~~~~~~~~~~~~~

``fapi.find_object_for`` resolves the SENAITE counterpart of a FHIR resource:
first by an exact FHIR-UID match (via ``get_object``), then via the
resource's ``IContentFinder`` adapter -- matching by business keys -- when
the UID match misses::

    >>> fapi.get_uid(fapi.find_object_for(fresh)) == fapi.get_uid(created)
    True

Non-resources are rejected::

    >>> fapi.find_object_for({"foo": "bar"})
    Traceback (most recent call last):
    ...
    FHIRAPIError: Type is not supported: {'foo': 'bar'}


search_by_fhir_uid
~~~~~~~~~~~~~~~~~~

``fapi.search_by_fhir_uid`` looks up the FHIR catalog by its ``fhir_uids``
index and returns the matching brains::

    >>> brains = fapi.search_by_fhir_uid(fapi.get_uid(fresh))
    >>> fapi.get_uid(brains[0]) == fapi.get_uid(created)
    True

A dashed FHIR id is harmonized to a hex UID, so either form works. With
``as_brains=False`` the matching objects are woken up and returned::

    >>> objs = fapi.search_by_fhir_uid(
    ...     fapi.get_fhir_id(created), "Patient", as_brains=False)
    >>> fapi.get_uid(objs[0]) == fapi.get_uid(created)
    True

An unknown UID yields an empty result::

    >>> len(fapi.search_by_fhir_uid("99999999-9999-5999-9999-999999999999"))
    0


get_object_by_fhir_uid
~~~~~~~~~~~~~~~~~~~~~~~

``fapi.get_object_by_fhir_uid`` resolves the object holding a FHIR UID through
the FHIR catalog. Either a hex UID or a dashed FHIR id works::

    >>> obj = fapi.get_object_by_fhir_uid(fapi.get_uid(fresh), "Patient")
    >>> fapi.get_uid(obj) == fapi.get_uid(created)
    True

    >>> obj = fapi.get_object_by_fhir_uid(fapi.get_fhir_id(created), "Patient")
    >>> fapi.get_uid(obj) == fapi.get_uid(created)
    True

The ``portal_type`` is optional; when omitted, all portal types are searched::

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

``fapi.set_fhir_uids`` persists FHIR UIDs against an object, keyed by resource
type, and indexes it in the FHIR catalog so it can be found again with
``search_by_fhir_uid``::

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

``fapi.update`` re-applies the resource fields to an already-resolved
content object (the caller resolves it first, e.g. via ``get_object`` or
``find_object_for``)::

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

A Patient carrying only a ``mobile`` phone stores that number in the
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

Calling ``create`` a second time for the same resource fails, because
the counterpart already exists::

    >>> fapi.create(brand_new)
    Traceback (most recent call last):
    ...
    ValueError: Counterpart object already exists: <PatientResource ...>


get_system_code
~~~~~~~~~~~~~~~

``fapi.get_system_code`` returns the coding system URL configured for a
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

``fapi.generate_UUID`` returns a fresh ``uuid.UUID``::

    >>> generated = fapi.generate_UUID()
    >>> isinstance(generated, UUID)
    True
    >>> fapi.generate_UUID() != generated
    True


Invalid bearer tokens are rejected before the search runs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every FHIR search endpoint must reject an invalid bearer token before route
handling. An otherwise successful empty Bundle could cause a polling client to
advance its ``_lastUpdated`` cursor and miss subsequent data. This covers the
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
