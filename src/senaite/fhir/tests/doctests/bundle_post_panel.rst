FHIR Bundle POST (panel resolved to its analysis profile)
---------------------------------------------------------

A `SenaiteRequestBundle` example: a request for an electrolyte panel.
The `ServiceRequest` references an analysis profile (LOINC `55231-5`,
*Electrolyte Panel*) and orders its three tests (Chloride `2075-0`,
Potassium `2823-3`, Sodium `2951-2`).

Preconditions:

- the *Electrolyte Panel* `AnalysisProfile` exists (profile key `55231-5`,
  with the three services);
- the *Cayman Islands Health Services Authority* Client exists;
- the *Serum* SampleType exists;
- the Patient, the Practitioner and the ServiceRequest do **not** exist yet.

Expected: a new electrolyte Sample is created, a new Patient (Adaeze Chisom
Okonkwo) and a new Practitioner/Contact (Dr. Thabo Mbeki, under the Cayman
client).

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_panel


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

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.03.json")
    >>> bundle = json.loads(raw)
    >>> bundle["type"]
    u'transaction'


Preconditions
~~~~~~~~~~~~~

The three electrolyte analysis services (matched by `ProtocolID`):

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

The *Electrolyte Panel* profile, keyed by the panel's LOINC code so the
ServiceRequest's `code` resolves to it::

    >>> profile = api.create(setup.analysisprofiles, "AnalysisProfile",
    ...                      title="Electrolyte Panel", ProfileKey="55231-5")
    >>> profile.setServices([chloride.UID(), potassium.UID(), sodium.UID()])

The Client (matched by the Organization's `ClientID`) and the Serum
SampleType (matched by the Specimen's SNOMED display)::

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Cayman Islands Health Services Authority",
    ...                     ClientID="ORG-HLTH-CYM-001")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum", Prefix="SER")
    >>> transaction.commit()


Post the bundle
~~~~~~~~~~~~~~~

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

The existing Client (Organization) is matched and updated; the Patient, the
Practitioner and the ServiceRequest are created::

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

A new Patient (Adaeze Chisom Okonkwo)::

    >>> patients = [obj for obj in portal.patients.objectValues()
    ...             if api.get_portal_type(obj) == "Patient"]
    >>> len(patients)
    1
    >>> patients[0].getMRN()
    'PAT-2026-00841'
    >>> patients[0].getFullname()
    'Adaeze Chisom Okonkwo'

A new Practitioner/Contact (Dr. Thabo Mbeki) under the Cayman client::

    >>> contacts = [obj for obj in client.objectValues()
    ...             if api.get_portal_type(obj) == "Contact"]
    >>> len(contacts)
    1
    >>> contacts[0].getFullname()
    'Thabo Mbeki'

A new electrolyte Sample, with the resolved profile and its three analyses::

    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> api.get_workflow_status_of(sample)
    'sample_due'
    >>> sample.getSampleType() == sampletype
    True
    >>> sample.getPriority()
    '5'
    >>> len(sample.getProfiles())
    1
    >>> sample.getProfiles()[0] == profile
    True
    >>> sorted([an.getKeyword for an in sample.getAnalyses()])
    ['Cl', 'K', 'Na']
