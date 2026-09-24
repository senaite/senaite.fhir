FHIR Bundle POST (identifier validation)
----------------------------------------

Tests the identifier validation layer in
`ResourceToAnalysisRequest.validate_identifiers()`:

1. **Rejection of usual identifier in ServiceRequest**: when a `ServiceRequest`
   carries an identifier with `use="usual"`, the conversion raises with
   `"Cannot specify usual identifier externally in incoming ServiceRequest"`.

2. **Rejection of usual identifier in Specimen**: when a `Specimen`
   carries an identifier with `use="usual"`, the conversion raises with
   `"Cannot specify usual identifier externally in incoming Specimen"`.

3. **Rejection of external identifier in ServiceRequest**: when a
   `ServiceRequest` carries an identifier with `use="secondary"` and
   `system="client-sample-id"`, the conversion raises with
   `"Cannot specify external identifier in ServiceRequest"`.

4. **Allow external identifier in Specimen**: when a `Specimen` carries an
   identifier with `use="secondary"` and `system="client-sample-id"`, the
   conversion succeeds and the identifier is used as the `ClientSampleID`.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_08


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

Load Bundle.01.json as the base bundle:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)


Setup objects
~~~~~~~~~~~~~

Create the basic SENAITE objects needed for bundle processing:

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
    >>> serum = api.create(setup.sampletypes, "SampleType",
    ...                    title="Serum specimen", Prefix="SER")
    >>> transaction.commit()


Rejection: ServiceRequest with a usual identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a `ServiceRequest` carries an identifier with `use="usual"`, the
conversion must reject it as internal IDs cannot be specified externally:

    >>> sr_entry = [e for e in bundle["entry"]
    ...             if e["resource"]["resourceType"] == "ServiceRequest"][0]
    >>> sr_entry["resource"]["identifier"] = [
    ...     {
    ...         "use": "usual",
    ...         "system": "https://fhir.senaite.org/NamingSystem/sample-id",
    ...         "value": "INTERNAL-SAMPLE-ID"
    ...     }
    ... ]
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome = json.loads(browser.contents)
    >>> outcome["resourceType"]
    u'OperationOutcome'
    >>> issue = outcome["issue"][0]
    >>> text = issue["details"]["text"]
    >>> "Cannot specify usual identifier externally" in text
    True

No AnalysisRequest is created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    0


Rejection: Specimen with a usual identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a `Specimen` carries an identifier with `use="usual"`, the
conversion must reject it:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> specimen_entry = [e for e in bundle["entry"]
    ...                   if e["resource"]["resourceType"] == "Specimen"][0]
    >>> specimen_entry["resource"]["identifier"] = [
    ...     {
    ...         "use": "usual",
    ...         "system": "https://fhir.senaite.org/NamingSystem/sample-id",
    ...         "value": "INTERNAL-SAMPLE-ID"
    ...     }
    ... ]
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome = json.loads(browser.contents)
    >>> issue = outcome["issue"][0]
    >>> text = issue["details"]["text"]
    >>> "Cannot specify usual identifier externally" in text
    True

No AnalysisRequest is created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    0


Rejection: ServiceRequest with an external identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a `ServiceRequest` carries an identifier with `use="secondary"` and
`system="client-sample-id"`, the conversion must reject it as ServiceRequest
should not carry external identifiers (only Specimen should):

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> sr_entry = [e for e in bundle["entry"]
    ...             if e["resource"]["resourceType"] == "ServiceRequest"][0]
    >>> sr_entry["resource"]["identifier"] = [
    ...     {
    ...         "use": "secondary",
    ...         "system": ("https://fhir.senaite.org"
    ...                    "/NamingSystem/client-sample-id"),
    ...         "value": "EXT-CARDIAC-003"
    ...     }
    ... ]
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome = json.loads(browser.contents)
    >>> issue = outcome["issue"][0]
    >>> text = issue["details"]["text"]
    >>> "Cannot specify external identifier in ServiceRequest" in text
    True

No AnalysisRequest is created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    0


Rejection: Specimen with an unsupported identifier system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `Specimen` may carry an external identifier, but only under the
`client-sample-id` naming system -- the profile slices `identifier` with
`closed` rules, so any other system is rejected:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> specimen_entry = [e for e in bundle["entry"]
    ...                   if e["resource"]["resourceType"] == "Specimen"][0]
    >>> specimen_entry["resource"]["identifier"] = [
    ...     {
    ...         "use": "secondary",
    ...         "system": "https://example.org/NamingSystem/their-own-id",
    ...         "value": "EXT-CARDIAC-004"
    ...     }
    ... ]
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome = json.loads(browser.contents)
    >>> issue = outcome["issue"][0]
    >>> issue["expression"]
    [u'Specimen.identifier']
    >>> text = issue["details"]["text"]
    >>> "Unsupported identifier system in Specimen" in text
    True

No AnalysisRequest is created:

    >>> portal._p_jar.sync()
    >>> len(client.objectValues("AnalysisRequest"))
    0


Success: Specimen with an external identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a `Specimen` carries an identifier with `use="secondary"` and
`system="client-sample-id"`, the conversion succeeds and the identifier
value becomes the `ClientSampleID` of the created `AnalysisRequest`:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> specimen_entry = [e for e in bundle["entry"]
    ...                   if e["resource"]["resourceType"] == "Specimen"][0]
    >>> specimen_entry["resource"]["identifier"] = [
    ...     {
    ...         "use": "secondary",
    ...         "system": ("https://fhir.senaite.org"
    ...                    "/NamingSystem/client-sample-id"),
    ...         "value": "EXT-CARDIAC-003"
    ...     }
    ... ]
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '200 OK'
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

The AnalysisRequest is created with the correct ClientSampleID:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> sample.getClientSampleID()
    'EXT-CARDIAC-003'

The transaction-response records the newly created Specimen by its FHIR id.
When read, it carries SENAITE's newly assigned sample ID as the ``usual``
identifier, ahead of the external client-sample ID. The consumer cannot supply
the former, so it is resolved from the live sample rather than from the stored
snapshot (see ``get_server_owned_elements``):

    >>> response_specimen = [entry for entry in response["entry"]
    ...                      if entry["fullUrl"].startswith("Specimen/")][0]
    >>> specimen_id = response_specimen["fullUrl"].rsplit("/", 1)[1]
    >>> browser.open("{}/Specimen/{}".format(fhir_url, specimen_id))
    >>> stored_specimen = json.loads(browser.contents)
    >>> stored_specimen["identifier"][0]["value"] == sample.getId()
    True
    >>> stored_specimen["identifier"][0]["use"]
    u'usual'
    >>> stored_specimen["identifier"][0]["system"] == (
    ...     "https://fhir.senaite.org/NamingSystem/sample-id")
    True
    >>> stored_specimen["identifier"][1]["value"]
    u'EXT-CARDIAC-003'
    >>> stored_specimen["identifier"][1]["use"]
    u'secondary'


Success: no identifiers
~~~~~~~~~~~~~~~~~~~~~~~

When a `Bundle` carries no identifiers on either `ServiceRequest` or
`Specimen`, the conversion succeeds normally:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> sr_entry = [e for e in bundle["entry"]
    ...             if e["resource"]["resourceType"] == "ServiceRequest"][0]
    >>> sr_entry["resource"].pop("identifier", None)
    >>> specimen_entry = [e for e in bundle["entry"]
    ...                   if e["resource"]["resourceType"] == "Specimen"][0]
    >>> identifier = specimen_entry["resource"].pop("identifier", None)
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '200 OK'
    >>> response = json.loads(browser.contents)
    >>> response["type"]
    u'transaction-response'

The AnalysisRequest is created without a ClientSampleID:

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> new_sample = [s for s in samples if not s.getClientSampleID()][0]
    >>> new_sample.getClientSampleID()
