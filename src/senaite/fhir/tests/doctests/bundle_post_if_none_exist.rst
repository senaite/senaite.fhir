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
match cannot be safely evaluated and rejects the whole transaction with
``412 Precondition Failed``. A malformed ``ifNoneExist`` (missing or
unrecognized identifier system, or no value) rejects it with ``400 Bad
Request``. Both use the same all-or-none rollback as every other bundle
validation failure.

This file covers the mechanics end-to-end for ``Patient``.
``bundle_post_if_none_exist_org_practitioner`` spot-checks
``Organization``/``Practitioner`` and a couple of cross-cutting edge cases.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_if_none_exist


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
gotcha documented in ``bundle_post_order_detail`` for ServiceRequest ids). The
ServiceRequest's ``subject`` reference is a literal ``Patient/{id}`` pointing
at the fixture's original placeholder, so it must be repointed too:

    >>> def set_patient_id(bundle, new_id):
    ...     entry = get_entry(bundle, "Patient")
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
evaluated and is rejected with 400, not silently ignored:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = "identifier=MRN-SOMETHING"
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> outcome["issue"][0]["code"]
    u'invalid'
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
    '400 Bad Request'
    >>> outcome["issue"][0]["code"]
    u'invalid'
    >>> "Unsupported identifier system" in (
    ...     outcome["issue"][0]["details"]["text"])
    True

    >>> patient_count()
    0


Rejection: ifNoneExist with no identifier value
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-mrn|")
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> outcome["issue"][0]["code"]
    u'invalid'
    >>> "Missing identifier value" in outcome["issue"][0]["details"]["text"]
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

The body carries another MRN than the matched Patient. This may be on
purpose, e.g. the MRN was corrected at the source and the consumer matches by
the old one, or a mistake in the condition. SENAITE cannot tell, so it accepts
the match and returns a warning in the Bundle's ``issues``:

    >>> issue = response["issues"]["issue"][0]
    >>> issue["severity"], issue["code"]
    (u'warning', u'business-rule')
    >>> issue["expression"]
    [u'Patient.identifier']
    >>> text = issue["details"]["text"]
    >>> "matched an existing Patient with identifier MRN-PRE-EXISTING" in text
    True
    >>> "the Patient in the request carries MRN-20394857" in text
    True
    >>> "The Patient in the request was not applied" in text
    True

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
    ...     patient_entry["fullUrl"].split(":")[-1], "Patient")
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

The warning compares with the matched Patient's MRN whatever system the
condition uses, so a match by internal id warns too:

    >>> issue = response["issues"]["issue"][0]
    >>> "with identifier MRN-PRE-EXISTING-2, but the Patient in the request " \
    ...     "carries MRN-20394857" in issue["details"]["text"]
    True


Success: a match on the Patient's own MRN does not warn
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the body carries the matched Patient's MRN, there is nothing to warn
about and the Bundle has no ``issues``:

    >>> existing5 = api.create(portal.patients, "Patient",
    ...                        mrn=u"MRN-SAME",
    ...                        firstname=u"Existing5", lastname=u"Patient")
    >>> transaction.commit()

    >>> bundle = load_bundle()
    >>> set_patient_id(bundle, "e5e5e5e5-e5e5-5e5e-9e5e-e5e5e5e5e5e5")
    >>> entry = get_entry(bundle, "Patient")
    >>> for identifier in entry["resource"]["identifier"]:
    ...     if identifier.get("use") == "secondary":
    ...         identifier["value"] = u"MRN-SAME"
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-mrn"
    ...     "|MRN-SAME")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Patient")
    u'200 OK'
    >>> "issues" in response
    False


Rejection: a match carrying invalid identifiers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The resources are validated before their counterpart object is searched, so
a conditional create is validated even when its ``ifNoneExist`` matches an
existing object -- a match does not skip the identifier rules. A Patient that
matches by MRN, but also carries an internal (``usual``) identifier, which the
consumer cannot send:

    >>> existing3 = api.create(portal.patients, "Patient",
    ...                        mrn=u"MRN-MATCH-INVALID",
    ...                        firstname=u"Existing3", lastname=u"Patient")
    >>> transaction.commit()
    >>> before = patient_count()
    >>> portal._p_jar.sync()
    >>> samples_before = len(client.objectValues("AnalysisRequest"))

    >>> bundle = load_bundle()
    >>> set_patient_id(bundle, "d4d4d4d4-d4d4-5d4d-9d4d-d4d4d4d4d4d4")
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/patient-mrn"
    ...     "|MRN-MATCH-INVALID")
    >>> entry["resource"]["identifier"].append({
    ...     "use": "usual",
    ...     "system": "https://fhir.senaite.org/NamingSystem/patient-id",
    ...     "value": "P-999",
    ... })
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> issue = outcome["issue"][0]
    >>> issue["expression"]
    [u'Patient.identifier']
    >>> "Cannot specify usual identifier externally in incoming Patient" in (
    ...     issue["details"]["text"])
    True

Nothing was linked or created: the bundle's placeholder FHIR id does not
point to the existing Patient, and no Patient nor Sample was added:

    >>> fapi.get_object_by_fhir_uid(
    ...     "d4d4d4d4-d4d4-5d4d-9d4d-d4d4d4d4d4d4", "Patient",
    ...     default=None) is None
    True
    >>> patient_count() == before
    True
    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest")) == samples_before
    True
