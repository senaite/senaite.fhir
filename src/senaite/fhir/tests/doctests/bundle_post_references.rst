FHIR Bundle POST (references to new and existing resources)
-----------------------------------------------------------

The entries of a POSTed bundle carry no `resource.id`, so the references
between them point to the `fullUrl` of the entry, in the `urn:uuid:<id>`
form. The `{Resource}/{id}` form points to a resource that already exists in
SENAITE instead, by the FHIR id SENAITE returned in the `fullUrl` of the
bundle response.

Neither form falls back to the other: a `urn:uuid:<id>` reference that does
not match the `fullUrl` of an entry of the same bundle, or a
`{Resource}/{id}` reference to a resource that does not exist in SENAITE,
rejects the whole bundle with 422 Unprocessable Entity.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_references


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
    >>> from senaite.core.catalog import SAMPLE_CATALOG
    >>> from senaite.fhir import api as fapi
    >>> from senaite.patient.catalog import PATIENT_CATALOG

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")

    >>> def get_entry(bundle, resource_type):
    ...     matches = [e for e in bundle["entry"]
    ...                if e["resource"]["resourceType"] == resource_type]
    ...     return matches[0]

    >>> def get_service_request(bundle):
    ...     return get_entry(bundle, "ServiceRequest")["resource"]

    >>> def get_client_reference(bundle):
    ...     return get_service_request(bundle)["extension"][0]["valueReference"]

    >>> def remove_entries(bundle, *resource_types):
    ...     bundle["entry"] = [e for e in bundle["entry"]
    ...                        if e["resource"]["resourceType"]
    ...                        not in resource_types]

    >>> def post_bundle(bundle):
    ...     browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...                  content_type="application/json")
    ...     return browser.headers["Status"], json.loads(browser.contents)

    >>> def get_response_url(response, resource_type):
    ...     matches = [e["fullUrl"] for e in response["entry"]
    ...                if e["fullUrl"].startswith(resource_type + "/")]
    ...     return matches[0]

    >>> def counts():
    ...     portal._p_jar.sync()
    ...     patients = api.search({"portal_type": "Patient"}, PATIENT_CATALOG)
    ...     samples = api.search({"portal_type": "AnalysisRequest"},
    ...                          SAMPLE_CATALOG)
    ...     return len(patients), len(samples)


Setup objects
~~~~~~~~~~~~~

Same setup as `bundle_post`: the Client the bundle's Organization resolves to,
the SampleType of the Specimen and the services of the ServiceRequest:

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


References to the entries of the same bundle
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ServiceRequest of the fixture refers to the other entries by their
`fullUrl`:

    >>> bundle = json.loads(raw)
    >>> sr = get_service_request(bundle)
    >>> urls = [e["fullUrl"] for e in bundle["entry"]]
    >>> sr["subject"]["reference"] in urls
    True
    >>> sr["requester"]["reference"] in urls
    True
    >>> sr["specimen"][0]["reference"] in urls
    True
    >>> get_client_reference(bundle)["reference"] in urls
    True

    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'

The response gives the FHIR id SENAITE assigned to each resource:

    >>> patient_url = get_response_url(response, "Patient")
    >>> organization_url = get_response_url(response, "Organization")
    >>> practitioner_url = get_response_url(response, "Practitioner")
    >>> specimen_url = get_response_url(response, "Specimen")

    >>> sample = api.get_object_by_uid(
    ...     fapi.get_uuid(get_response_url(
    ...         response, "ServiceRequest").split("/")[-1]).hex)
    >>> sample.getClient() == client
    True
    >>> contact = sample.getContact()


References to existing resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A bundle with no Patient, Organization nor Practitioner entries refers to the
ones created above by the `fullUrl` of the response. The ServiceRequest and
the Specimen get new placeholders, so a new sample is created:

    >>> before = counts()
    >>> bundle = json.loads(raw)
    >>> remove_entries(bundle, "Patient", "Organization", "Practitioner")
    >>> sr_entry = get_entry(bundle, "ServiceRequest")
    >>> sr_entry["fullUrl"] = "urn:uuid:11111111-2222-4333-8444-555555555555"
    >>> specimen_entry = get_entry(bundle, "Specimen")
    >>> specimen_entry["fullUrl"] = (
    ...     "urn:uuid:66666666-7777-4888-8999-aaaaaaaaaaaa")
    >>> sr = sr_entry["resource"]
    >>> sr["specimen"][0]["reference"] = specimen_entry["fullUrl"]
    >>> sr["subject"]["reference"] = patient_url
    >>> sr["requester"]["reference"] = practitioner_url
    >>> get_client_reference(bundle)["reference"] = organization_url

    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> [e["fullUrl"].split("/")[0] for e in response["entry"]]
    [u'Specimen', u'ServiceRequest']

No Patient was created, but a new sample, for the existing Client and Contact:

    >>> after = counts()
    >>> after[0] == before[0]
    True
    >>> after[1] == before[1] + 1
    True

    >>> new_sample = api.get_object_by_uid(
    ...     fapi.get_uuid(get_response_url(
    ...         response, "ServiceRequest").split("/")[-1]).hex)
    >>> new_sample == sample
    False
    >>> new_sample.getClient() == client
    True
    >>> new_sample.getContact() == contact
    True


Rejection: a urn:uuid reference with no matching entry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> def assert_rejected(bundle, expression):
    ...     before = counts()
    ...     status, outcome = post_bundle(bundle)
    ...     issue = outcome["issue"][0]
    ...     assert status == "422 Unprocessable Entity", status
    ...     assert issue["code"] == "invalid", issue
    ...     assert issue["expression"] == [expression], issue
    ...     assert counts() == before, "Something was created"
    ...     return issue["details"]["text"]

A `urn:uuid:` reference that does not match the `fullUrl` of any entry:

    >>> unknown = "urn:uuid:0f0f0f0f-1111-4222-8333-444455556666"
    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["subject"]["reference"] = unknown
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no entry with fullUrl 'urn:uuid:0f0f0f0f-...' in the Bundle

The same applies to the other references:

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["requester"]["reference"] = unknown
    >>> print(assert_rejected(bundle, "ServiceRequest.requester"))
    ServiceRequest.requester: no entry with fullUrl ... in the Bundle

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["specimen"][0]["reference"] = unknown
    >>> print(assert_rejected(bundle, "ServiceRequest.specimen"))
    ServiceRequest.specimen: no entry with fullUrl ... in the Bundle

    >>> bundle = json.loads(raw)
    >>> get_client_reference(bundle)["reference"] = unknown
    >>> expression = ("ServiceRequest.extension('https://fhir.senaite.org/"
    ...               "StructureDefinition/SenaiteClient').value")
    >>> print(assert_rejected(bundle, expression))
    ServiceRequest.extension(...).value: no entry with fullUrl ... in the Bundle

A `urn:uuid:` reference is never resolved to an existing resource, even when
it carries the FHIR id of one:

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["subject"]["reference"] = (
    ...     "urn:uuid:" + patient_url.split("/")[-1])
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no entry with fullUrl ... in the Bundle

Nor is an entry matched by its id only, regardless of the form of its
`fullUrl`:

    >>> bundle = json.loads(raw)
    >>> patient_entry = get_entry(bundle, "Patient")
    >>> placeholder = patient_entry["fullUrl"].split(":")[-1]
    >>> patient_entry["fullUrl"] = "Patient/" + placeholder
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no entry with fullUrl ... in the Bundle


Rejection: a urn:uuid reference to an entry of another type
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = json.loads(raw)
    >>> sr = get_service_request(bundle)
    >>> sr["subject"]["reference"] = sr["requester"]["reference"]
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: the entry with fullUrl '...' is a 'Practitioner', not a Patient

The same applies to an entry with no valid type, which is not processed:

    >>> bundle = json.loads(raw)
    >>> get_entry(bundle, "Practitioner")["resource"]["resourceType"] = ""
    >>> print(assert_rejected(bundle, "ServiceRequest.requester"))
    ServiceRequest.requester: the entry with fullUrl '...' is a '', not a Practitioner


Rejection: a reference to a resource that does not exist
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A `{Resource}/{id}` reference is never resolved to an entry of the bundle, so
the placeholder of an entry is not valid in this form:

    >>> bundle = json.loads(raw)
    >>> sr = get_service_request(bundle)
    >>> placeholder = sr["subject"]["reference"].split(":")[-1]
    >>> sr["subject"]["reference"] = "Patient/" + placeholder
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no Patient found for 'Patient/...'

Nor is a resource of another type:

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["subject"]["reference"] = practitioner_url
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no Patient found for 'Practitioner/...'

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["subject"]["reference"] = (
    ...     "Patient/" + practitioner_url.split("/")[-1])
    >>> print(assert_rejected(bundle, "ServiceRequest.subject"))
    ServiceRequest.subject: no Patient found for 'Patient/...'


Rejection: a reference to an existing Specimen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Specimen is stored along with the sample created for it, so the
ServiceRequest can only refer to a new one, from the same bundle:

    >>> bundle = json.loads(raw)
    >>> get_service_request(bundle)["specimen"][0]["reference"] = specimen_url
    >>> print(assert_rejected(bundle, "ServiceRequest.specimen"))
    ServiceRequest.specimen: no Specimen found for 'Specimen/...'
