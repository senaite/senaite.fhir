FHIR Bundle POST (panel without a matching analysis profile)
------------------------------------------------------------

A `SenaiteRequestBundle` example, exercising the POST endpoint of the FHIR
API route `/senaite/@@FHIR/r5` with a different lab request than
`bundle_post`.

This bundle's `ServiceRequest` references a panel whose `code.concept`
carries a coding but no `text`, and no matching `AnalysisProfile` exists
in the instance. Resolving the (optional) analysis profile must therefore
cope with the missing values and yield no profile, rather than failing with
`500 'NoneType' object has no attribute 'lower'`.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_panel_without_profile


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
    >>> request = self.request
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Load the example bundle from the test data:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.02.json")
    >>> bundle = json.loads(raw)
    >>> bundle["type"]
    u'transaction'


Setup objects
~~~~~~~~~~~~~

The pre-existing `Client` (matched by the Organization's `ClientID`) and
the `SampleType` (matched by the Specimen's SNOMED display, `Serum`):

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Harbour Island Health Authority",
    ...                     ClientID="ORG-HLTH-HBI-001")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum", Prefix="SER")

The single ordered analysis (LOINC `19123-9`, matched by `ProtocolID`).
Note we deliberately do *not* create an `AnalysisProfile` for the panel:

    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Boss")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Chemistry", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="Metals", Department=department)
    >>> magnesium = api.create(
    ...     portal.bika_setup.bika_analysisservices, "AnalysisService",
    ...     title="Magnesium", Keyword="Mg",
    ...     Category=category.UID(), ProtocolID="19123-9")
    >>> transaction.commit()


Post the bundle
~~~~~~~~~~~~~~~

The Bundle is accepted (no `500` from the unresolved panel):

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

    >>> entries = response["entry"]
    >>> sorted([e["fullUrl"].split("/")[0] for e in entries])
    [u'Organization', u'Patient', u'Practitioner', u'ServiceRequest', u'Specimen']

    >>> status = dict((e["fullUrl"].split("/")[0], e["response"]["status"])
    ...               for e in entries)
    >>> status["Organization"]
    u'200 OK'
    >>> status["Patient"]
    u'201 Created'
    >>> status["Practitioner"]
    u'201 Created'
    >>> status["ServiceRequest"]
    u'201 Created'
    >>> status["Specimen"]
    u'201 Created'


Created content
~~~~~~~~~~~~~~~

    >>> portal._p_jar.sync()

A Patient and a Contact (from the Practitioner) were created:

    >>> patients = [obj for obj in portal.patients.objectValues()
    ...             if api.get_portal_type(obj) == "Patient"]
    >>> len(patients)
    1
    >>> patients[0].getMRN()
    'PAT-2026-00841'

    >>> contacts = [obj for obj in client.objectValues()
    ...             if api.get_portal_type(obj) == "Contact"]
    >>> contacts[0].getFullname()
    'Sipho Dlamini'

A Sample was created under the Client, with the single ordered analysis and
the `asap` priority. No analysis profile was assigned -- the unresolved
panel yields no profile instead of raising::

    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> api.get_workflow_status_of(sample)
    'sample_due'
    >>> sample.getSampleType() == sampletype
    True
    >>> len(sample.getAnalyses())
    1
    >>> sample.getPriority()
    '2'
    >>> sample.getProfiles()
    []
