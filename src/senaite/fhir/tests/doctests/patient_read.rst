FHIR Patient Read
-----------------

Verify that a Patient created via ``bika.lims.api.create`` is exposed by
the FHIR API route ``/senaite/@@FHIR/r5/Patient/<uid>`` and that its
JSON representation matches the canonical example published at
https://fhir.senaite.org/Patient-52f941c6-81a0-51be-b1a6-f92ac079be34.json

Running this test from the buildout directory:

    bin/test test_doctests -t patient_read


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api

Variables:

    >>> portal = self.portal
    >>> portal_url = portal.absolute_url()
    >>> fhir_url = "{}/@@FHIR/r5".format(portal_url)
    >>> browser = self.getBrowser()
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])
    >>> transaction.commit()


Reference Resource
~~~~~~~~~~~~~~~~~~

The canonical Patient resource that the FHIR API response is expected
to match (excerpt of the relevant fields):

    >>> reference = {
    ...     "resourceType": "Patient",
    ...     "identifier": [
    ...         {"use": "usual",
    ...          "system": "https://fhir.senaite.org/NamingSystem/patient-id",
    ...          "value": "PAT-001"},
    ...         {"use": "secondary",
    ...          "value": "123456"},
    ...     ],
    ...     "name": [{
    ...         "use": "official",
    ...         "family": "Doe",
    ...         "given": ["Jane"],
    ...     }],
    ...     "gender": "female",
    ...     "birthDate": "1980-01-01",
    ... }


Create the Patient
~~~~~~~~~~~~~~~~~~

Create a Patient under the portal's ``patients`` folder, matching the
data of the reference resource:

    >>> patient = api.create(
    ...     portal.patients, "Patient",
    ...     mrn=u"PAT-001",
    ...     firstname=u"Jane",
    ...     lastname=u"Doe",
    ...     sex=u"f",
    ...     gender=u"f",
    ...     birthdate="1980-01-01",
    ...     identifiers=[{"key": "other", "value": "123456"}],
    ... )
    >>> patient
    <Patient at /plone/patients/...>
    >>> uid = api.get_uid(patient)
    >>> transaction.commit()


Fetch via the FHIR Route
~~~~~~~~~~~~~~~~~~~~~~~~

Calling ``/senaite/@@FHIR/r5/Patient/<uid>`` returns the FHIR
representation of the Patient:

    >>> browser.open("{}/Patient/{}".format(fhir_url, uid))
    >>> resource = json.loads(browser.contents)

The resource type matches the reference:

    >>> resource["resourceType"] == reference["resourceType"]
    True

The administrative gender and the date of birth match the reference.

.. note::

   The Patient -> FHIR gender mapping is lossy: ``administrative-gender``
   only defines ``male | female | other | unknown``, so both SENAITE
   ``t`` (transgender) and ``d`` (diverse) collapse to ``other`` and a
   round-trip ``t -> other -> d`` loses the original key. Preserving it
   requires a dedicated extension (e.g. ``patient-genderIdentity``) and
   is out of scope for this test.

    >>> resource["gender"] == reference["gender"]
    True

    >>> resource["birthDate"] == reference["birthDate"]
    True

The Patient's family and given name match the reference:

    >>> def as_official_name(name):
    ...     if isinstance(name, list):
    ...         for item in name:
    ...             if item.get("use") == "official":
    ...                 return item
    ...         return name[0] if name else {}
    ...     return name or {}

    >>> ref_name = as_official_name(reference["name"])
    >>> res_name = as_official_name(resource["name"])
    >>> res_name["family"] == ref_name["family"]
    True
    >>> list(res_name["given"]) == list(ref_name["given"])
    True

The MRN (``PAT-001``) and the secondary identifier (``123456``) from the
reference are present in the FHIR response:

    >>> def identifier_values(identifiers):
    ...     return sorted([i.get("value") for i in identifiers if i.get("value")])

    >>> values = identifier_values(resource["identifier"])
    >>> "PAT-001" in values
    True
    >>> "123456" in values
    True

The SENAITE ID and MRN use their fixed identifier systems. The MRN is an
external, ``secondary`` identifier:

    >>> internal_identifier = next(
    ...     i for i in resource["identifier"] if i.get("use") == "usual")
    >>> internal_identifier["system"]
    u'https://fhir.senaite.org/NamingSystem/patient-id'
    >>> mrn_identifier = next(
    ...     i for i in resource["identifier"]
    ...     if i.get("system") == (
    ...         "https://fhir.senaite.org/NamingSystem/patient-mrn"))
    >>> mrn_identifier["use"]
    u'secondary'
    >>> mrn_identifier["value"]
    u'PAT-001'


The FHIR resource ``id`` is a separate UUID generated on first fetch;
it is not the same as the SENAITE object UID::

    >>> fhir_id = resource["id"]
    >>> fhir_id != uid
    True

Fetch by FHIR ID
~~~~~~~~~~~~~~~~

Because the FHIR ID and the SENAITE UID are separate, the resource is
also reachable by its FHIR-assigned ``id``::

    >>> browser.open("{}/Patient/{}".format(fhir_url, fhir_id))
    >>> resource2 = json.loads(browser.contents)
    >>> resource2["resourceType"]
    u'Patient'
    >>> resource2["id"] == fhir_id
    True

The FHIR ID is stable — re-fetching via the SENAITE UID returns the same ``id``::

    >>> browser.open("{}/Patient/{}".format(fhir_url, uid))
    >>> json.loads(browser.contents)["id"] == fhir_id
    True

Fetch by UID Alone
~~~~~~~~~~~~~~~~~~

The same Patient is also reachable by its plain SENAITE UID (without the
resource type segment):

    >>> browser.open("{}/{}".format(fhir_url, uid))
    >>> json.loads(browser.contents)["resourceType"]
    u'Patient'


Patient created from a FHIR resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Patient above was created natively in SENAITE, so its FHIR ``id`` is
derived from its own SENAITE UID. When a Patient is instead created *from* an
incoming FHIR resource (e.g. POSTed in a Bundle), the resource's own ``id`` is
preserved against the object as a distinct FHIR id:

    >>> from senaite.fhir import api as fapi
    >>> incoming = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "id": "a1b2c3d4-1111-5111-9111-aaaaaaaaaaaa",
    ...     "name": [{"use": "official", "family": "Stone", "given": ["Mark"]}],
    ...     "gender": "male",
    ...     "birthDate": "1970-02-03",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "PAT-FHIR"}],
    ... })
    >>> created = fapi.create(incoming)
    >>> transaction.commit()

The object gets its own generated SENAITE UID, which differs from the incoming
FHIR id (here shown in hex form):

    >>> created_uid = api.get_uid(created)
    >>> created_uid != "a1b2c3d4111151119111aaaaaaaaaaaa"
    True

Fetching the Patient by its SENAITE UID returns a resource whose ``id`` is the
original FHIR id (in dashed UUID form), not the underlying object's UID:

    >>> browser.open("{}/Patient/{}".format(fhir_url, created_uid))
    >>> created_resource = json.loads(browser.contents)
    >>> created_resource["id"]
    u'a1b2c3d4-1111-5111-9111-aaaaaaaaaaaa'

    >>> created_resource["id"] != created_uid
    True

Fetching the Patient by its original FHIR resource id (which is not a SENAITE
UID, so it is resolved through the FHIR catalog) returns the very same
resource:

    >>> browser.open("{}/Patient/{}".format(
    ...     fhir_url, "a1b2c3d4-1111-5111-9111-aaaaaaaaaaaa"))
    >>> by_fhir_id = json.loads(browser.contents)
    >>> by_fhir_id == created_resource
    True
