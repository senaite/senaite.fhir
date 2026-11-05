FHIR Bundle POST (unexpected failure)
-------------------------------------

A `transaction` Bundle is all-or-none: if one of the resources it carries
cannot be processed, nothing at all is persisted.

When the failure is one the endpoint knows about -- a violation of a SENAITE
profile -- it is reported as a `400 OperationOutcome` naming the offending
element (see `bundle_post_specimen`). This test covers the other case: an
*unexpected* failure while a resource is being processed. Such a failure has to

- roll the whole bundle back, including the resources that were processed
  successfully before the one that failed;
- answer with HTTP `500` and an `OperationOutcome`, rather than reporting a
  rolled-back transaction as an HTTP `200` `transaction-response`;
- keep the internal exception text server-side, where it is logged, and never
  hand it to the client.

An unexpected failure cannot be provoked through the API by construction --
that is what makes it unexpected -- so `fapi.create` is patched to raise
while the `ServiceRequest` of an otherwise valid bundle is processed.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_failure


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

Load the example bundle. It carries a `Patient`, an `Organization`, a
`Practitioner`, a `Specimen` and a `ServiceRequest`:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> bundle["type"]
    u'transaction'

Create the setup objects the bundle resolves against, exactly as in
`bundle_post`: only the `Client`, the `SampleType` and the analysis
services have to pre-exist:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Royal Melbourne Hospital",
    ...                     ClientID="ORG-RMH-MEL")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum specimen", Prefix="SER")
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
    >>> transaction.commit()

The bundle creates a Patient, a Contact (from the Practitioner) and a Sample
(from the ServiceRequest). Count them to tell apart "rolled back" from
"never created":

    >>> def created():
    ...     portal._p_jar.sync()
    ...     patients = [obj for obj in portal.patients.objectValues()
    ...                 if api.get_portal_type(obj) == "Patient"]
    ...     contacts = [obj for obj in client.objectValues()
    ...                 if api.get_portal_type(obj) == "Contact"]
    ...     samples = client.objectValues("AnalysisRequest")
    ...     return len(patients), len(contacts), len(samples)

Nothing has been created yet:

    >>> created()
    (0, 0, 0)


An unexpected failure rolls the whole bundle back
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Patch `fapi.create` so it keeps working for every resource except the
`ServiceRequest`. The Patient and the Practitioner come before it in the
bundle, so they are created successfully and have to be rolled back together
with the failure:

    >>> create = fapi.create
    >>> def failing_create(resource):
    ...     if resource.resourceType == "ServiceRequest":
    ...         raise RuntimeError("Cursor is closed: LEAKED-INTERNAL-DETAIL")
    ...     return create(resource)
    >>> fapi.create = failing_create

Post the bundle:

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")

The endpoint answers `500` with an `OperationOutcome`, naming the resource
it choked on:

    >>> browser.headers["Status"]
    '500 Internal Server Error'

    >>> outcome = json.loads(browser.contents)
    >>> outcome["resourceType"]
    u'OperationOutcome'
    >>> issue = outcome["issue"][0]
    >>> issue["severity"]
    u'error'
    >>> issue["code"]
    u'exception'
    >>> issue["expression"]
    [u'ServiceRequest.id']

The message is generic. The exception text is logged server-side and is not
part of the response, so nothing about the internals leaks to the client:

    >>> issue["details"]["text"]
    u'Internal error while processing the ServiceRequest resource'
    >>> "LEAKED-INTERNAL-DETAIL" in browser.contents
    False
    >>> "RuntimeError" in browser.contents
    False
    >>> "Traceback" in browser.contents
    False

It is an `OperationOutcome`, not a `transaction-response` Bundle reporting
the failure in one of its entries:

    >>> "entry" in outcome
    False
    >>> "type" in outcome
    False

And nothing was persisted -- not even the Patient and the Contact that had
already been created when the ServiceRequest failed:

    >>> created()
    (0, 0, 0)


The bundle itself is valid
~~~~~~~~~~~~~~~~~~~~~~~~~~

Restore `fapi.create` and post the very same bundle again. It goes through,
which confirms the `500` above came from the patched failure and not from an
unrelated problem with the bundle or the setup:

    >>> fapi.create = create

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '200 OK'

    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'
    >>> created()
    (1, 1, 1)

    >>> browser.raiseHttpErrors = True
