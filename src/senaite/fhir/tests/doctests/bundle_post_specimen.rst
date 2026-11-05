FHIR Bundle POST (Specimen SampleType validation and re-linking)
----------------------------------------------------------------

Exercises three Specimen-specific behaviours introduced alongside the FHIR
Specimen listing:

1. **Rejection on missing SampleType**: when a `Bundle` contains a
   `Specimen` whose `type.coding.display` does not match any
   `SampleType` in SENAITE, the ServiceRequest conversion raises and the
   whole bundle is rejected with a `400 OperationOutcome`. As the POST is a
   single all-or-nothing transaction, no content is persisted.

2. **Specimen appears in listing**: after a successful bundle POST the stored
   Specimen annotation is returned by `GET /Specimen`.

3. **SampleType re-linking on update**: re-posting the same bundle with a
   different Specimen type updates the underlying AnalysisRequest's
   `SampleType` field even though the field is guarded by the
   `FieldEditSampleType` write permission.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_specimen


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

Load Bundle.01.json as the base bundle (it carries a `Specimen` with
type display `"Serum specimen"`):

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> bundle["type"]
    u'transaction'


Setup objects (without SampleType)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create the Client and analysis services so the bundle can be fully resolved –
except the `SampleType`, which is left out intentionally for the pre-flight
test:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Royal Melbourne Hospital",
    ...                     ClientID="ORG-RMH-MEL")
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


Rejection – missing SampleType
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the `Specimen` in the bundle cannot be matched to an existing
`SampleType` in SENAITE the ServiceRequest conversion raises and the whole
bundle is rejected; the transaction is rolled back so no content is persisted:

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome = json.loads(browser.contents)
    >>> outcome["resourceType"]
    u'OperationOutcome'
    >>> issue = outcome["issue"][0]
    >>> issue["severity"]
    u'error'
    >>> issue["code"]
    u'not-found'
    >>> "Specimen.type" in issue["expression"]
    True

No AnalysisRequest is created by the rejected bundle:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    0


Initial bundle POST – Specimen stored and appears in listing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now create the `SampleType` (matched by the Specimen's SNOMED display) and
a second `SampleType` that will be used in the SampleType re-linking test:

    >>> serum = api.create(setup.sampletypes, "SampleType",
    ...                    title="Serum specimen", Prefix="SER")
    >>> edta = api.create(setup.sampletypes, "SampleType",
    ...                   title="EDTA Blood", Prefix="EDTA")
    >>> transaction.commit()

Post the bundle:

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

The Specimen entry is included in the response (mirrors the ServiceRequest
status):

    >>> entries = response["entry"]
    >>> specimen_entries = [e for e in entries
    ...                     if e["fullUrl"].startswith("Specimen/")]
    >>> len(specimen_entries)
    1
    >>> specimen_entries[0]["response"]["status"]
    u'201 Created'

The response embeds the rendered Specimen resource:

    >>> response_specimen = specimen_entries[0]["resource"]
    >>> response_specimen["resourceType"]
    u'Specimen'
    >>> response_specimen["type"]["coding"][0]["display"]
    u'Serum specimen'

The consumer's content is kept as submitted, e.g. the SNOMED code of the
type and the note:

    >>> response_specimen["type"]["coding"][0]["code"]
    u'119364003'
    >>> response_specimen["note"][0]["text"]
    u'Fasting specimen. No visible haemolysis.'

But the elements owned by SENAITE are populated by the server. The internal
Sample ID, that the consumer cannot supply, is returned alongside the Client
Sample ID it did supply:

    >>> identifiers = response_specimen["identifier"]
    >>> [(i["use"], i["system"].split("/")[-1]) for i in identifiers]
    [(u'usual', u'sample-id'), (u'secondary', u'client-sample-id')]
    >>> portal._p_jar.sync()
    >>> identifiers[0]["value"] == client.objectValues()[0].getId()
    True
    >>> identifiers[1]["value"]
    u'EXT-LIVER-001'

    >>> response_specimen["status"]
    u'available'

The FHIR id of the stored Specimen is derived from the entry's fullUrl:

    >>> bundle_specimen = [e for e in bundle["entry"]
    ...                    if e["resource"]["resourceType"] == "Specimen"][0]
    >>> stored_fhir_id = bundle_specimen["fullUrl"].split(":")[-1]
    >>> specimen_entries[0]["fullUrl"] == "Specimen/{}".format(stored_fhir_id)
    True

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> sample.getSampleType() == serum
    True

The FHIR-backed Specimen is returned by `GET /Specimen`:

    >>> browser.open("{}/Specimen".format(fhir_url))
    >>> listing = json.loads(browser.contents)
    >>> listing["total"]
    1
    >>> listing["entry"][0]["fullUrl"] == "Specimen/{}".format(stored_fhir_id)
    True
    >>> listing["entry"][0]["resource"]["resourceType"]
    u'Specimen'

Fetching the Specimen by its FHIR id also works:

    >>> browser.open("{}/Specimen/{}".format(fhir_url, stored_fhir_id))
    >>> single = json.loads(browser.contents)
    >>> single["resourceType"]
    u'Specimen'
    >>> single["id"] == stored_fhir_id
    True
    >>> single == response_specimen
    True


SampleType re-linking on bundle update
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Change the Specimen's type display to `"EDTA Blood"` in the bundle and
re-post.  The existing AnalysisRequest is found and updated; its SampleType
must be switched even though the field is guarded by the
`FieldEditSampleType` write permission::

    >>> specimen_entry = [e for e in bundle["entry"]
    ...                   if e["resource"]["resourceType"] == "Specimen"][0]
    >>> specimen_entry["resource"]["type"]["coding"][0]["display"] = "EDTA Blood"

Re-post the modified bundle:

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response2 = json.loads(browser.contents)
    >>> response2["type"]
    u'transaction-response'

    >>> entries2 = response2["entry"]
    >>> sr_entry = [e for e in entries2
    ...             if e["fullUrl"].startswith("ServiceRequest/")][0]
    >>> sr_entry["response"]["status"]
    u'200 OK'

The embedded Specimen reflects the update, and still carries the internal
Sample ID:

    >>> specimen_entry2 = [e for e in entries2
    ...                    if e["fullUrl"].startswith("Specimen/")][0]
    >>> specimen2 = specimen_entry2["resource"]
    >>> specimen2["type"]["coding"][0]["display"]
    u'EDTA Blood'
    >>> specimen2["identifier"] == response_specimen["identifier"]
    True

No duplicate AnalysisRequest is created:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1

The AnalysisRequest's SampleType is now `EDTA Blood`:

    >>> samples[0].getSampleType() == edta
    True

The updated Specimen (with the new type) is returned by `GET /Specimen`:

    >>> browser.open("{}/Specimen".format(fhir_url))
    >>> listing2 = json.loads(browser.contents)
    >>> listing2["total"]
    1
    >>> listing2["entry"][0]["resource"]["type"]["coding"][0]["display"]
    u'EDTA Blood'
