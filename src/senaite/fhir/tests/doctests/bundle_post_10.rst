FHIR Bundle POST (ifNoneExist conditional create -- Patient)
--------------------------------------------------------------

Implements the conditional-create business rules from issue #60: a
``Patient``, ``Practitioner`` or ``Organization`` bundle entry may carry
``request.ifNoneExist`` of the form ``identifier=<system>|<value>``, keyed on
either that type's internal (``...-id``) or external
(``...-mrn``/``...-external-id``) default ``NamingSystem``
(``senaite.fhir.conditions.MATCH_TABLE``). Zero matches creates as normal.
Exactly one match is treated as already-satisfied: the submitted body is
discarded entirely and the existing object is left untouched. More than one
match -- or a missing/unrecognized identifier system -- cannot be safely
evaluated and rejects the whole transaction with ``412 Precondition
Failed``, the same all-or-none rollback used by every other bundle
validation failure.

This file covers the mechanics end-to-end for ``Patient``.
``bundle_post_11`` spot-checks ``Organization``/``Practitioner`` and a couple
of cross-cutting edge cases.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_10


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api
    >>> from senaite.fhir import api as fapi
    >>> from senaite.patient import api as papi

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

    >>> def load_bundle():
    ...     raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    ...     return json.loads(raw)

    >>> def get_entry(bundle, resource_type):
    ...     return [e for e in bundle["entry"]
    ...             if e["resource"]["resourceType"] == resource_type][0]

    >>> def post_bundle(bundle):
    ...     browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...                  content_type="application/json")
    ...     return browser.headers["Status"], json.loads(browser.contents)

    >>> def entry_status(response, resource_type):
    ...     matches = [e["response"]["status"] for e in response["entry"]
    ...                if e["fullUrl"].startswith(resource_type + "/")]
    ...     return matches[0]

    >>> def patient_count():
    ...     portal._p_jar.sync()
    ...     return len([obj for obj in portal.patients.objectValues()
    ...                 if api.get_portal_type(obj) == "Patient"])

Each scenario below that creates or links a Patient uses its own Patient
placeholder id, so a later scenario's link doesn't silently steal the FHIR
id a previous scenario already linked to a different Patient (the same
gotcha documented in ``bundle_post_06`` for ServiceRequest ids). The
ServiceRequest's ``subject`` reference is a literal ``Patient/{id}`` pointing
at the fixture's original placeholder, so it must be repointed too:

    >>> def set_patient_id(bundle, new_id):
    ...     entry = get_entry(bundle, "Patient")
    ...     entry["resource"]["id"] = new_id
    ...     entry["fullUrl"] = "urn:uuid:{}".format(new_id)
    ...     sr_entry = get_entry(bundle, "ServiceRequest")
    ...     sr_entry["resource"]["subject"]["reference"] = (
    ...         "Patient/{}".format(new_id))


Setup objects
~~~~~~~~~~~~~

Create the basic SENAITE objects needed for the ServiceRequest/Specimen part
of the bundle to succeed regardless of how the Patient entry resolves:

    >>> client = api.create(portal.clients, "Client",
    ...                     ClientID="ORG-RMH-MEL")
    >>> client.setName(u"Royal Melbourne Hospital")
    >>> client.reindexObject()
    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Boss")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Chemistry", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="Liver", Department=department)
    >>> loinc_codes = ["1742-6", "1920-8", "6768-6", "1975-2",
    ...                "1968-7", "2885-2", "1751-7", "5902-2"]
    >>> for num, code in enumerate(loinc_codes):
    ...     service = api.create(
    ...         portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...         title="LFT %s" % code, Keyword="LFT%s" % num,
    ...         Category=category.UID(), ProtocolID=code)
    >>> serum = api.create(setup.sampletypes, "SampleType",
    ...                    title="Serum specimen", Prefix="SER")
    >>> transaction.commit()

    >>> patient_count()
    0


Rejection: ifNoneExist with no identifier system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A malformed ``ifNoneExist`` (no ``system|value`` pair at all) cannot be
evaluated safely and is rejected with 412, not silently ignored:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = "identifier=MRN-SOMETHING"
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '412 Precondition Failed'
    >>> outcome["issue"][0]["code"]
    u'multiple-matches'
    >>> "Missing identifier system" in outcome["issue"][0]["details"]["text"]
    True

Nothing was created -- the whole transaction is rejected:

    >>> patient_count()
    0


Rejection: ifNoneExist with an unrecognized identifier system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://example.org/NamingSystem/their-own-id"
    ...     "|MRN-20394857")
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '412 Precondition Failed'
    >>> outcome["issue"][0]["code"]
    u'multiple-matches'
    >>> "Unsupported identifier system" in outcome["issue"][0]["details"]["text"]
    True

    >>> patient_count()
    0


Success: zero matches creates the Patient as normal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ifNoneExist`` keyed on the bundle's own MRN, which no Patient carries yet:

    >>> bundle = load_bundle()
    >>> set_patient_id(bundle, "a1a1a1a1-a1a1-5a1a-9a1a-a1a1a1a1a1a1")
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-mrn"
    ...     "|MRN-20394857")
    >>> before = patient_count()
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Patient")
    u'201 Created'

The body was applied since this was a real create, not a match:

    >>> patient_count() == before + 1
    True
    >>> created = papi.get_patient_by_mrn("MRN-20394857")
    >>> created.getFirstname()
    'James'


Success: one match on the external system discards the body
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Patient already exists, independently of anything the bundle carries:

    >>> existing = api.create(portal.patients, "Patient",
    ...                       mrn=u"MRN-PRE-EXISTING",
    ...                       firstname=u"Existing", lastname=u"Patient")
    >>> transaction.commit()
    >>> before = patient_count()

``ifNoneExist`` matches it by MRN. The bundle's own Patient body (still
James Nguyen / MRN-20394857 from the fixture) is never even looked at:

    >>> bundle = load_bundle()
    >>> set_patient_id(bundle, "b2b2b2b2-b2b2-5b2b-9b2b-b2b2b2b2b2b2")
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-mrn"
    ...     "|MRN-PRE-EXISTING")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Patient")
    u'200 OK'

No duplicate was created, and the existing Patient's own fields (name, MRN)
are untouched -- the submitted body was discarded, not applied:

    >>> patient_count() == before
    True
    >>> existing.getFirstname()
    'Existing'
    >>> existing.getMRN()
    'MRN-PRE-EXISTING'

The bundle's placeholder FHIR id is now linked to the pre-existing Patient,
same as a real create/update would do:

    >>> patient_entry = get_entry(bundle, "Patient")
    >>> match = fapi.get_object_by_fhir_uid(
    ...     patient_entry["resource"]["id"], "Patient")
    >>> fapi.get_uid(match) == fapi.get_uid(existing)
    True

That link is also what lets the rest of the same bundle resolve the
ServiceRequest's ``subject`` reference to the matched Patient rather than
failing to find one -- the Sample is created successfully:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1


Success: one match on the internal system discards the body
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Same idea, but matching by SENAITE's own internal object id rather than the
consumer's MRN:

    >>> existing2 = api.create(portal.patients, "Patient",
    ...                        mrn=u"MRN-PRE-EXISTING-2",
    ...                        firstname=u"Existing2", lastname=u"Patient")
    >>> transaction.commit()
    >>> before = patient_count()

    >>> bundle = load_bundle()
    >>> set_patient_id(bundle, "c3c3c3c3-c3c3-5c3c-9c3c-c3c3c3c3c3c3")
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-id"
    ...     "|{}".format(api.get_id(existing2)))
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Patient")
    u'200 OK'

    >>> patient_count() == before
    True
    >>> existing2.getFirstname()
    'Existing2'
