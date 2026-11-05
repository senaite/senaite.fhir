FHIR Bundle POST (response entries in request order)
----------------------------------------------------

For a successful transaction, the server returns a `transaction-response`
Bundle "that contains one entry for each entry in the request, in the same
order, with the outcome of processing the entry":
https://hl7.org/fhir/R5/http.html#transaction-response

SENAITE processes the resources of a `SenaiteRequestBundle` in dependency
order (Organization, Practitioner, Specimen, Patient, ServiceRequest), so the
response must be put back in the order of the request.

The request (`Bundle.07.json`) and its expected response
(`BundleResponse.07.json`) are the target bundles of the specification. The
identifiers of the request carry the default NamingSystems, and its entries
refer to each other by the `urn:uuid` placeholder of their `fullUrl`.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_14


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

    >>> def load(filename):
    ...     raw = resource_string("senaite.fhir.tests", "data/" + filename)
    ...     return json.loads(raw)

    >>> def get_type(entry):
    ...     return entry["fullUrl"].split("/")[0]


Setup objects
~~~~~~~~~~~~~

The `SampleType` is matched by the SNOMED display of the Specimen type
(`Blood`), and the analysis services by the LOINC codes of the
ServiceRequest's `orderDetail` (here through their `ProtocolID`):

    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Blood", Prefix="BLD")
    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Boss")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Haematology", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="Blood", Department=department)
    >>> loinc_codes = ["883-9", "6690-2", "10331-7", "19261-7"]
    >>> for num, code in enumerate(loinc_codes):
    ...     service = api.create(
    ...         portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...         title="Test %s" % code, Keyword="TEST%s" % num,
    ...         Category=category.UID(), ProtocolID=code)
    >>> transaction.commit()

Nothing else exists: the Organization, Patient and Practitioner are all
created from the bundle.


Post the bundle
~~~~~~~~~~~~~~~

    >>> request_bundle = load("Bundle.07.json")
    >>> browser.post("{}/Bundle".format(fhir_url),
    ...              json.dumps(request_bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '200 OK'
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'


Response entries in the order of the request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The response has one entry for each entry of the request:

    >>> request_types = [e["resource"]["resourceType"]
    ...                  for e in request_bundle["entry"]]
    >>> request_types
    [u'Patient', u'Organization', u'Practitioner', u'Specimen',
     u'ServiceRequest']
    >>> len(response["entry"]) == len(request_bundle["entry"])
    True

In the same order as the request, which is not the processing order:

    >>> [get_type(e) for e in response["entry"]] == request_types
    True

The response matches the expected one, entry by entry, in resource type and
outcome:

    >>> expected = load("BundleResponse.07.json")
    >>> outcome = [(get_type(e), e["response"]["status"])
    ...            for e in response["entry"]]
    >>> expected_outcome = [(get_type(e), e["response"]["status"])
    ...                     for e in expected["entry"]]
    >>> outcome == expected_outcome
    True
    >>> outcome
    [(u'Patient', u'201 Created'),
     (u'Organization', u'201 Created'),
     (u'Practitioner', u'201 Created'),
     (u'Specimen', u'201 Created'),
     (u'ServiceRequest', u'201 Created')]


The request was registered
~~~~~~~~~~~~~~~~~~~~~~~~~~

The Client was created from the Organization, with a Sample of the ordered
analyses for the Patient, requested by the Practitioner:

    >>> portal._p_jar.sync()
    >>> client = [c for c in portal.clients.objectValues()
    ...           if c.getClientID() == "ORG-OSP-PIS"][0]
    >>> sample = client.objectValues("AnalysisRequest")[0]
    >>> sample.getSampleType() == sampletype
    True
    >>> sample.getClientSampleID()
    'EXT-CARDIAC-003'
    >>> sample.getContact().getFHIRExternalID()
    'PRACT-DR-RICCI'
    >>> sorted([a.getKeyword() for a in sample.getAnalyses(full_objects=True)])
    ['TEST0', 'TEST1', 'TEST2', 'TEST3']
