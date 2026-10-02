FHIR Bundle POST (ifNoneExist conditional create -- Organization, Practitioner)
--------------------------------------------------------------------------------

Continues ``bundle_post_10`` (which covers the ``ifNoneExist`` mechanics end
to end for ``Patient``) with spot-checks for ``Organization`` and
``Practitioner``, plus two cross-cutting edge cases: more than one match
(412, whole bundle rejected) and a stray ``ifNoneExist`` on a resource type
that doesn't support it (``ServiceRequest``/``Specimen`` are ``0..0`` per the
IG -- silently ignored rather than rejected).

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_11


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

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

    >>> def get_entry(bundle, resource_type):
    ...     matches = [e for e in bundle["entry"]
    ...                if e["resource"]["resourceType"] == resource_type]
    ...     return matches[0]

    >>> def load_bundle():
    ...     raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    ...     return json.loads(raw)

    >>> def post_bundle(bundle):
    ...     browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...                  content_type="application/json")
    ...     return browser.headers["Status"], json.loads(browser.contents)

    >>> def entry_status(response, resource_type):
    ...     matches = [e["response"]["status"] for e in response["entry"]
    ...                if e["fullUrl"].startswith(resource_type + "/")]
    ...     return matches[0]

    >>> def client_count():
    ...     portal._p_jar.sync()
    ...     return len([obj for obj in portal.clients.objectValues()
    ...                 if api.get_portal_type(obj) == "Client"])

The Organization's placeholder id is also referenced by the ServiceRequest's
``SenaiteClient`` extension, so repointing it (same reason as
``bundle_post_10``'s ``set_patient_id``, avoiding a later scenario's link
stealing an earlier one's FHIR id) means updating both:

    >>> def set_org_id(bundle, new_id):
    ...     entry = get_entry(bundle, "Organization")
    ...     entry["resource"]["id"] = new_id
    ...     entry["fullUrl"] = "urn:uuid:{}".format(new_id)
    ...     sr_entry = get_entry(bundle, "ServiceRequest")
    ...     ext = sr_entry["resource"]["extension"][0]
    ...     ext["valueReference"]["reference"] = "urn:uuid:{}".format(new_id)

Every scenario that expects a *new* Sample also needs its own ServiceRequest
placeholder id -- otherwise it silently matches (and updates in place) the
AnalysisRequest an earlier scenario already linked to the fixture's default
id, rather than creating a new one (the exact gotcha ``bundle_post_06``
documents):

    >>> def set_sr_id(bundle, new_id):
    ...     entry = get_entry(bundle, "ServiceRequest")
    ...     entry["resource"]["id"] = new_id
    ...     entry["fullUrl"] = "urn:uuid:{}".format(new_id)

Same for the Practitioner, referenced from ServiceRequest.requester:

    >>> def set_practitioner_id(bundle, new_id):
    ...     entry = get_entry(bundle, "Practitioner")
    ...     entry["resource"]["id"] = new_id
    ...     entry["fullUrl"] = "urn:uuid:{}".format(new_id)
    ...     sr_entry = get_entry(bundle, "ServiceRequest")
    ...     sr_entry["resource"]["requester"]["reference"] = (
    ...         "Practitioner/{}".format(new_id))


Setup objects
~~~~~~~~~~~~~

Same fixture as ``bundle_post_09``/``bundle_post_10`` -- the default Client
the bundle's own Organization entry already carries an external id for
(``ORG-RMH-MEL``), plus the AnalysisServices/SampleType the ServiceRequest
and Specimen need to succeed:

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


Edge case: a stray ifNoneExist on ServiceRequest is silently ignored
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ServiceRequest`` (and ``Specimen``) never carry ``ifNoneExist`` per the IG
-- both are created fresh on every order. SENAITE doesn't enforce that as a
hard profile violation; it simply never looks at ``ifNoneExist`` for these
two types, so the bundle processes normally:

    >>> bundle = load_bundle()
    >>> set_sr_id(bundle, "e1e1e1e1-e1e1-5e1e-9e1e-e1e1e1e1e1e1")
    >>> entry = get_entry(bundle, "ServiceRequest")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/sample-id"
    ...     "|SHOULD-BE-IGNORED")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "ServiceRequest")
    u'201 Created'

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    1


Success: Organization matched by external id (ClientID) discards the body
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A second, unrelated Client already exists:

    >>> existing_org = api.create(portal.clients, "Client",
    ...                           ClientID="ORG-PRE-EXISTING")
    >>> existing_org.setName(u"Existing Hospital")
    >>> existing_org.reindexObject()
    >>> transaction.commit()
    >>> before = client_count()

``ifNoneExist`` matches it by ``ClientID``, not the default ``client``
fixture (which the bundle's own Organization body still names):

    >>> bundle = load_bundle()
    >>> set_org_id(bundle, "d4d4d4d4-d4d4-5d4d-9d4d-d4d4d4d4d4d4")
    >>> set_sr_id(bundle, "e2e2e2e2-e2e2-5e2e-9e2e-e2e2e2e2e2e2")
    >>> entry = get_entry(bundle, "Organization")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/"
    ...     "organization-external-id|ORG-PRE-EXISTING")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Organization")
    u'200 OK'

No duplicate Client, and the matched one's own Name is untouched -- the
submitted body (``Royal Melbourne Hospital``) was discarded:

    >>> client_count() == before
    True
    >>> existing_org.getName()
    'Existing Hospital'

The Sample was created under the matched Client, not the unrelated default
fixture:

    >>> portal._p_jar.sync()
    >>> len(existing_org.objectValues("AnalysisRequest"))
    1
    >>> len(client.objectValues("AnalysisRequest"))
    1

(``1`` from the previous scenario, unchanged by this one.)


Success: Practitioner matched by external id via ifNoneExist
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Contact already exists under the default Client:

    >>> practitioner = api.create(client, "Contact",
    ...                           Firstname="Existing", Surname="Doctor")
    >>> practitioner.setFHIRExternalID(u"PRACT-PRE-EXISTING")
    >>> practitioner.reindexObject()
    >>> transaction.commit()
    >>> before = len(client.getContacts())

This is the same match ``bundle_post_09`` already exercises via the always-on
``ContactFinder`` fallback -- here it's driven explicitly by ``ifNoneExist``
instead, a different code path with the same outcome:

    >>> bundle = load_bundle()
    >>> set_sr_id(bundle, "e3e3e3e3-e3e3-5e3e-9e3e-e3e3e3e3e3e3")
    >>> set_practitioner_id(bundle, "f3f3f3f3-f3f3-5f3f-9f3f-f3f3f3f3f3f3")
    >>> entry = get_entry(bundle, "Practitioner")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/"
    ...     "practitioner-external-id|PRACT-PRE-EXISTING")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> entry_status(response, "Practitioner")
    u'200 OK'

    >>> portal._p_jar.sync()
    >>> len(client.getContacts()) == before
    True
    >>> practitioner.getFullname()
    'Existing Doctor'

The new Sample's Contact is the matched, pre-existing Practitioner:

    >>> samples = [s for s in client.objectValues("AnalysisRequest")
    ...            if s.getContact().getFullname() == "Existing Doctor"]
    >>> len(samples)
    1


Rejection: more than one match cannot be evaluated safely (412)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two Contacts legally share the same external id (unlike Patient MRNs,
``fhir_external_id`` has no uniqueness constraint):

    >>> dup1 = api.create(client, "Contact", Firstname="Dup", Surname="One")
    >>> dup1.setFHIRExternalID(u"PRACT-DUP")
    >>> dup1.reindexObject()
    >>> dup2 = api.create(client, "Contact", Firstname="Dup", Surname="Two")
    >>> dup2.setFHIRExternalID(u"PRACT-DUP")
    >>> dup2.reindexObject()
    >>> transaction.commit()
    >>> before_contacts = len(client.getContacts())
    >>> before_samples = len(client.objectValues("AnalysisRequest"))

    >>> bundle = load_bundle()
    >>> set_sr_id(bundle, "e4e4e4e4-e4e4-5e4e-9e4e-e4e4e4e4e4e4")
    >>> set_practitioner_id(bundle, "f4f4f4f4-f4f4-5f4f-9f4f-f4f4f4f4f4f4")
    >>> entry = get_entry(bundle, "Practitioner")
    >>> entry["request"]["ifNoneExist"] = (
    ...     "identifier=https://fhir.senaite.org/NamingSystem/"
    ...     "practitioner-external-id|PRACT-DUP")
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '412 Precondition Failed'
    >>> outcome["issue"][0]["code"]
    u'multiple-matches'

The whole transaction is rejected -- no third Contact and no new Sample:

    >>> portal._p_jar.sync()
    >>> len(client.getContacts()) == before_contacts
    True
    >>> len(client.objectValues("AnalysisRequest")) == before_samples
    True
