FHIR Bundle POST (single analysis without panel, asap priority)
---------------------------------------------------------------

A `SenaiteRequestBundle` example: a request for a single analysis
(Magnesium) with an `asap` priority. The `ServiceRequest` carries a
SNOMED `code` (*Laboratory procedure*) but no analysis panel, so no
profile is resolved and the Sample ends up with just the ordered analysis.

This also pins the priority mapping: a FHIR `asap` priority maps to the
SENAITE priority `2`.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_without_panel


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

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.04.json")
    >>> bundle = json.loads(raw)
    >>> bundle["type"]
    u'transaction'


Setup objects
~~~~~~~~~~~~~

The pre-existing Client (matched by the Organization's `ClientID`), the
Serum SampleType, and the single ordered analysis (Magnesium, matched by
`ProtocolID`):

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Harbour Island Health Authority",
    ...                     ClientID="ORG-HLTH-HBI-001")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum", Prefix="SER")
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

A new Sample is created under the Client, including only Magnesium and with
no analysis profile (the SNOMED `code` does not resolve to a panel)::

    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> api.get_workflow_status_of(sample)
    'sample_due'
    >>> sample.getSampleType() == sampletype
    True
    >>> sample.getProfiles()
    []
    >>> [an.getKeyword for an in sample.getAnalyses()]
    ['Mg']

The `asap` priority is mapped to the SENAITE priority `2`::

    >>> sample.getPriority()
    '2'
