FHIR Bundle POST (logical ids are assigned by SENAITE)
------------------------------------------------------

The logical id (`Resource.id`) of a resource is assigned by SENAITE and never
supplied by the consumer. A POSTed entry is only identified by the placeholder
of its `fullUrl` (e.g. `urn:uuid:<id>`), which the other entries of the same
bundle refer to. An entry carrying `resource.id` rejects the whole bundle with
422 Unprocessable Entity, before anything is processed.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_13


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api
    >>> from senaite.patient.catalog import PATIENT_CATALOG

Variables:

    >>> portal = self.portal
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

    >>> def load_bundle():
    ...     raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    ...     return json.loads(raw)

    >>> def get_entry(bundle, resource_type):
    ...     matches = [e for e in bundle["entry"]
    ...                if e["resource"]["resourceType"] == resource_type]
    ...     return matches[0]

    >>> def post_bundle(bundle):
    ...     browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...                  content_type="application/json")
    ...     return browser.headers["Status"], json.loads(browser.contents)

    >>> def patient_count():
    ...     portal._p_jar.sync()
    ...     return len(api.search({"portal_type": "Patient"}, PATIENT_CATALOG))


The fixture identifies its entries by fullUrl only
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

None of the entries of the fixture carries a `resource.id`:

    >>> bundle = load_bundle()
    >>> [e["resource"].get("id") for e in bundle["entry"]]
    [None, None, None, None, None]
    >>> all([e["fullUrl"].startswith("urn:uuid:") for e in bundle["entry"]])
    True


Rejection: an entry with a logical id
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Patient entry that carries the placeholder of its fullUrl as its id too:

    >>> before = patient_count()
    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["id"] = entry["fullUrl"].split(":")[-1]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '422 Unprocessable Entity'
    >>> issue = outcome["issue"][0]
    >>> issue["severity"], issue["code"]
    (u'error', u'invalid')
    >>> issue["details"]["coding"] == [{
    ...     "system": "http://terminology.hl7.org/CodeSystem/"
    ...               "operation-outcome",
    ...     "code": "MSG_LOCAL_FAIL",
    ... }]
    True
    >>> issue["details"]["text"] == (
    ...     "Resource.id must not be supplied in a POST transaction entry. "
    ...     "SENAITE generates all logical IDs; see "
    ...     "identifiers.html#general-pattern.")
    True

The expression points to the entry by its position in the bundle (the
Patient is the first entry):

    >>> issue["expression"]
    [u'Bundle.entry[0].resource.id']

Nothing was created:

    >>> patient_count() == before
    True

The same applies to the resources with no counterpart content in SENAITE,
such as the Specimen:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Specimen")
    >>> entry["resource"]["id"] = "any-id"
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '422 Unprocessable Entity'
    >>> outcome["issue"][0]["expression"]
    [u'Bundle.entry[3].resource.id']
    >>> patient_count() == before
    True
