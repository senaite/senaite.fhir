FHIR Bundle POST (orderDetail / code validation scenarios)
----------------------------------------------------------

Explicit tests for all six ``orderDetail``/``code`` scenarios:

- **Defer to panel** — named panel code, no ``orderDetail``: SENAITE creates
  the sample using the profile's analyses
- **Full elaboration** — named panel code, ``orderDetail`` lists every panel
  test: sample created for exactly those tests
- **Partial subset (rejected)** — named panel code, ``orderDetail`` omits one
  or more panel tests: ``400 Bad Request`` / ``OperationOutcome``
- **Defer to orderDetail** — default catch-all code (``30954-2``),
  ``orderDetail`` present: sample created for exactly those tests
- **Default panel, no tests (rejected)** — code ``30954-2``, no
  ``orderDetail``: ``400 Bad Request`` / ``OperationOutcome``

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_06


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import copy
    >>> import json
    >>> import transaction
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api
    >>> from senaite.fhir import api as fapi

Variables:

    >>> portal = self.portal
    >>> request = self.request
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Load the base bundle (Electrolyte Panel, three tests in ``orderDetail``):

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.03.json")
    >>> base_bundle = json.loads(raw)
    >>> base_bundle["type"]
    u'transaction'


Preconditions
~~~~~~~~~~~~~

Shared analysis services matched by ProtocolID:

    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Boss")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Chemistry", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="Electrolytes", Department=department)
    >>> chloride = api.create(
    ...     portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...     title="Chloride", Keyword="Cl",
    ...     Category=category.UID(), ProtocolID="2075-0")
    >>> potassium = api.create(
    ...     portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...     title="Potassium", Keyword="K",
    ...     Category=category.UID(), ProtocolID="2823-3")
    >>> sodium = api.create(
    ...     portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...     title="Sodium", Keyword="Na",
    ...     Category=category.UID(), ProtocolID="2951-2")
    >>> magnesium = api.create(
    ...     portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...     title="Magnesium", Keyword="Mg",
    ...     Category=category.UID(), ProtocolID="19123-9")

The *Electrolyte Panel* profile (Cl, K, Na), keyed by its LOINC code:

    >>> profile = api.create(setup.analysisprofiles, "AnalysisProfile",
    ...                      title="Electrolyte Panel", ProfileKey="55231-5")
    >>> profile.setServices([chloride.UID(), potassium.UID(), sodium.UID()])

Client and SampleType:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Cayman Islands Health Services Authority",
    ...                     ClientID="ORG-HLTH-CYM-001")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum", Prefix="SER")
    >>> transaction.commit()


Helpers
~~~~~~~

Find and return the ServiceRequest entry dict from the bundle:

    >>> def get_sr_entry(bundle):
    ...     for entry in bundle["entry"]:
    ...         if entry["resource"]["resourceType"] == "ServiceRequest":
    ...             return entry
    ...     raise KeyError("No ServiceRequest entry in bundle")

Replace the ServiceRequest's entry fullUrl so each scenario creates a distinct
object rather than updating a previous one:

    >>> def set_sr_id(bundle, new_id):
    ...     entry = get_sr_entry(bundle)
    ...     entry["fullUrl"] = "urn:uuid:{}".format(new_id)

Shorthand for the LOINC orderDetail parameter structure:

    >>> def loinc_param(code, display):
    ...     return {
    ...         "parameter": [{
    ...             "code": {"coding": [{
    ...                 "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
    ...                 "code": "LOINC", "display": "Test Code"
    ...             }]},
    ...             "valueCodeableConcept": {"coding": [{
    ...                 "system": "http://loinc.org",
    ...                 "code": code, "display": display
    ...             }]}
    ...         }]
    ...     }

    >>> def loinc_code(code, display):
    ...     return {"concept": {"coding": [{"system": "http://loinc.org",
    ...                                     "code": code, "display": display}]}}


Scenario 1: Defer to panel (empty orderDetail)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a named panel code is present and ``orderDetail`` is omitted, SENAITE
assigns the profile and derives all analyses from it — nothing needs to be
enumerated by the caller.

    >>> bundle = copy.deepcopy(base_bundle)
    >>> sr = get_sr_entry(bundle)["resource"]
    >>> set_sr_id(bundle, "a1111111-1111-1111-1111-111111111101")
    >>> sr["code"] = loinc_code("55231-5", "Electrolyte Panel")
    >>> _ = sr.pop("orderDetail", None)

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

    >>> status = dict((e["fullUrl"].split("/")[0], e["response"]["status"])
    ...               for e in response["entry"])
    >>> status["ServiceRequest"]
    u'201 Created'

The sample is assigned the Electrolyte Panel profile; SENAITE expands it to
the three panel analyses:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> sample.getProfiles()[0] == profile
    True
    >>> sorted([an.getKeyword for an in sample.getAnalyses()])
    ['Cl', 'K', 'Na']


Scenario 2: Full elaboration (all panel tests enumerated)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a named panel code is present and ``orderDetail`` enumerates every test
in the panel, the sample is created for exactly those tests and the profile is
also assigned.

    >>> bundle = copy.deepcopy(base_bundle)
    >>> sr = get_sr_entry(bundle)["resource"]
    >>> set_sr_id(bundle, "a1111111-1111-1111-1111-111111111102")
    >>> sr["code"] = loinc_code("55231-5", "Electrolyte Panel")
    >>> sr["orderDetail"] = [
    ...     loinc_param("2075-0", "Chloride"),
    ...     loinc_param("2823-3", "Potassium"),
    ...     loinc_param("2951-2", "Sodium"),
    ... ]

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

    >>> status = dict((e["fullUrl"].split("/")[0], e["response"]["status"])
    ...               for e in response["entry"])
    >>> status["ServiceRequest"]
    u'201 Created'

A new sample is created with the profile and exactly the three tests:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    2
    >>> newest = sorted(samples, key=lambda s: s.created())[-1]
    >>> newest.getProfiles()[0] == profile
    True
    >>> sorted([an.getKeyword for an in newest.getAnalyses()])
    ['Cl', 'K', 'Na']


Scenario 3: Partial subset rejected (400)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a named panel code is present and ``orderDetail`` omits one or more of
the panel's tests, the request is rejected with ``400 Bad Request`` and an
``OperationOutcome``. No sample is created.

Only Chloride is listed; Potassium and Sodium are missing:

    >>> bundle = copy.deepcopy(base_bundle)
    >>> sr = get_sr_entry(bundle)["resource"]
    >>> set_sr_id(bundle, "a1111111-1111-1111-1111-111111111103")
    >>> sr["code"] = loinc_code("55231-5", "Electrolyte Panel")
    >>> sr["orderDetail"] = [loinc_param("2075-0", "Chloride")]

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["status"]
    '400 Bad Request'
    >>> response = json.loads(browser.contents)
    >>> response["resourceType"]
    u'OperationOutcome'
    >>> response["issue"][0]["code"]
    u'business-rule'
    >>> response["issue"][0]["expression"]
    [u'ServiceRequest.orderDetail']

No new sample was created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    2


Scenario 4: Defer to orderDetail (default code 30954-2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``code`` carries the default catch-all LOINC ``30954-2``, the server
skips panel-membership validation and creates a sample with exactly the tests
listed in ``orderDetail``.

    >>> bundle = copy.deepcopy(base_bundle)
    >>> sr = get_sr_entry(bundle)["resource"]
    >>> set_sr_id(bundle, "a1111111-1111-1111-1111-111111111104")
    >>> sr["code"] = loinc_code("30954-2",
    ...                         "Relevant diagnostic tests/laboratory data note")
    >>> sr["orderDetail"] = [loinc_param("19123-9", "Magnesium")]

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

    >>> status = dict((e["fullUrl"].split("/")[0], e["response"]["status"])
    ...               for e in response["entry"])
    >>> status["ServiceRequest"]
    u'201 Created'

A new sample is created with only Magnesium and no profile:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    3
    >>> newest = sorted(samples, key=lambda s: s.created())[-1]
    >>> newest.getProfiles()
    []
    >>> [an.getKeyword for an in newest.getAnalyses()]
    ['Mg']


Scenario 5: Default code with no tests rejected (400)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``code`` is ``30954-2`` and ``orderDetail`` is absent, there is neither a
panel to expand nor explicit tests. The request must be rejected.

    >>> bundle = copy.deepcopy(base_bundle)
    >>> sr = get_sr_entry(bundle)["resource"]
    >>> set_sr_id(bundle, "a1111111-1111-1111-1111-111111111105")
    >>> sr["code"] = loinc_code("30954-2",
    ...                         "Relevant diagnostic tests/laboratory data note")
    >>> _ = sr.pop("orderDetail", None)

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["status"]
    '400 Bad Request'
    >>> response = json.loads(browser.contents)
    >>> response["resourceType"]
    u'OperationOutcome'
    >>> response["issue"][0]["code"]
    u'business-rule'
    >>> response["issue"][0]["expression"]
    [u'ServiceRequest.orderDetail']

No additional sample was created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    3
