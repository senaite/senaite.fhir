FHIR Bundle POST (lab request)
------------------------------

Exercise the POST endpoint of the FHIR API route ``/senaite/@@FHIR/r5``
with a ``SenaiteRequestBundle`` (a transaction ``Bundle``). Posting the
bundle registers a new lab request: the underlying SENAITE objects are
derived from the FHIR resources it carries.

The example bundle is the one published in the implementation guide:
https://fhir.senaite.org/Bundle-cafa2ba8-7aad-5d5e-b2c4-752f61f6ec8f.json

It carries a ``Patient``, an ``Organization`` (the submitting Client), a
``Practitioner`` (the requester), a ``Specimen`` and a ``ServiceRequest``.
The ``Client`` must already exist in SENAITE; everything else (Patient,
Practitioner -> Contact and the ServiceRequest -> AnalysisRequest) is
created automatically.

See https://fhir.senaite.org/StructureDefinition-SenaiteRequestBundle.html
and https://fhir.senaite.org/lab-request-and-results.html

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post


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
    >>> portal_url = portal.absolute_url()
    >>> fhir_url = "{}/@@FHIR/r5".format(portal_url)
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Load the example bundle from the test data:

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> bundle["resourceType"]
    u'Bundle'
    >>> bundle["type"]
    u'transaction'


Setup objects
~~~~~~~~~~~~~

Only the ``Client`` must pre-exist. The bundle's ``Organization`` is resolved
to it by the ``ClientFinder`` (an ``IContentFinder`` adapter): it matches on
the Organization's external identifier (the Client's ``ClientID``) and falls
back to the title, so the Organization is *updated* rather than created anew:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Royal Melbourne Hospital",
    ...                     ClientID="ORG-RMH-MEL")

The ``SampleType`` is matched by the specimen's SNOMED display
(``Serum specimen``), so it must exist too:

    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Serum specimen", Prefix="SER")

The analysis services are matched by the LOINC codes carried in the
ServiceRequest ``orderDetail`` (here through their ``ProtocolID``):

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


Post the bundle
~~~~~~~~~~~~~~~

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)

The response is a ``transaction-response`` Bundle:

    >>> response["resourceType"]
    u'Bundle'
    >>> response["type"]
    u'transaction-response'

It carries one entry per processed resource, including the ``Specimen``
(stored as annotation on the AnalysisRequest):

    >>> entries = response["entry"]
    >>> sorted([e["fullUrl"].split("/")[0] for e in entries])
    [u'Organization', u'Patient', u'Practitioner', u'ServiceRequest', u'Specimen']

The pre-existing Client (Organization) is updated, the rest are created:

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

Pick up the objects committed by the request:

    >>> portal._p_jar.sync()

A Patient was created (Patient is dexterity content, so we filter the
folder contents by portal type rather than meta type):

    >>> patients = [obj for obj in portal.patients.objectValues()
    ...             if api.get_portal_type(obj) == "Patient"]
    >>> len(patients)
    1

A Contact (from the Practitioner) was created under the existing Client,
and no new Client was added:

    >>> len(portal.clients.objectValues("Client"))
    1
    >>> contacts = [obj for obj in client.objectValues()
    ...             if api.get_portal_type(obj) == "Contact"]
    >>> len(contacts)
    1
    >>> contact = contacts[0]
    >>> contact.getFullname()
    'Catherine Sullivan'

A Sample (AnalysisRequest) was created under the Client from the
ServiceRequest:

    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> sample = samples[0]
    >>> api.get_workflow_status_of(sample)
    'sample_due'

It is wired to the resolved Client, Contact and SampleType:

    >>> sample.getClient() == client
    True
    >>> sample.getContact() == contact
    True
    >>> sample.getSampleType() == sampletype
    True

The eight ordered services were resolved into analyses:

    >>> len(sample.getAnalyses())
    8

The Patient created from the bundle carries its medical record number:

    >>> patients[0].getMRN()
    'MRN-20394857'
    >>> patients[0].getMaritalStatus()
    u'M'

The Patient telecom is mapped onto the patient record:

    >>> patients[0].getPhone()
    '+61 3 9000 1234'

The patient demographics from the bundle are also copied onto the Sample.
The public accessors (``getMedicalRecordNumberValue`` etc.) are guarded by
senaite.patient's ``@check_installed``, which requires the senaite.patient
browser layer on the *current* request -- not present in this test thread
after the POST -- so we read the stored field values directly:

    >>> sample.getField("MedicalRecordNumber").get(sample).get("value")
    'MRN-20394857'

    >>> sample.getField("PatientFullName").get_fullname(sample)
    'James Nguyen'

    >>> sample.getField("Sex").get(sample)
    'm'


External ID of the Contact
~~~~~~~~~~~~~~~~~~~~~~~~~~

The identifier assigned to the `Practitioner` by the API consumer's own
system (`use=secondary`) is kept in the `fhir_external_id` field of the
Contact, added by the `IExtendedContactBehavior` behavior:

    >>> from senaite.fhir.behaviors.contact import IExtendedContactBehavior
    >>> practitioner = [e["resource"] for e in bundle["entry"]
    ...                 if e["resource"]["resourceType"] == "Practitioner"][0]
    >>> external_id = practitioner["identifier"][0]
    >>> external_id["use"]
    u'secondary'
    >>> external_id["value"]
    u'PRACT-DR-SULLIVAN'

    >>> contact.getFHIRExternalID()
    'PRACT-DR-SULLIVAN'
    >>> IExtendedContactBehavior(contact).fhir_external_id
    'PRACT-DR-SULLIVAN'

It is indexed in the contacts catalog, so the Contact can be searched by it:

    >>> from senaite.core.catalog import CONTACT_CATALOG
    >>> query = {"fhir_external_id": "PRACT-DR-SULLIVAN"}
    >>> brains = api.search(query, CONTACT_CATALOG)
    >>> [api.get_object(brain) for brain in brains] == [contact]
    True


Requester lookup
~~~~~~~~~~~~~~~~

The Contact of the Sample is the `requester` of the `ServiceRequest`. When
that reference cannot be resolved by the FHIR id of the `Practitioner`, the
Contact is searched within the Client, first by the external ID of the
`Practitioner` and then by its full name.

To exercise it, build a copy of the bundle where the `Practitioner` has a
FHIR id not known by SENAITE, along with the given external ID and, optionally,
a different family name:

    >>> import copy
    >>> from senaite.fhir.converter.analysisrequest import (
    ...     ResourceToAnalysisRequest)
    >>> unknown_id = "0f0f0f0f-1111-4222-8333-444455556666"

    >>> def get_requester(external_id, family=None):
    ...     data = copy.deepcopy(bundle)
    ...     for entry in data["entry"]:
    ...         resource = entry["resource"]
    ...         if resource["resourceType"] == "Practitioner":
    ...             resource["id"] = unknown_id
    ...             resource["identifier"] = [{
    ...                 "use": "secondary",
    ...                 "value": external_id,
    ...             }]
    ...             if family:
    ...                 for name in resource.get("name") or []:
    ...                     name["family"] = family
    ...         if resource["resourceType"] == "ServiceRequest":
    ...             reference = "Practitioner/{}".format(unknown_id)
    ...             resource["requester"]["reference"] = reference
    ...             sr_id = resource["id"]
    ...     data = fapi.to_fhir_resource(data)
    ...     service_request = data.first_entry("id", sr_id)
    ...     converter = ResourceToAnalysisRequest(service_request)
    ...     return converter.get_requester()

The FHIR id is not known by SENAITE:

    >>> fapi.get_object(unknown_id, default=None) is None
    True

The Contact is found by its external ID, even if the name differs:

    >>> get_requester("PRACT-DR-SULLIVAN", family="Nobody") == contact
    True

When no Contact has that external ID, the Contact is found by its full name:

    >>> get_requester("PRACT-UNKNOWN") == contact
    True

When neither the external ID nor the full name match, no Contact is found:

    >>> get_requester("PRACT-UNKNOWN", family="Nobody")
    Traceback (most recent call last):
    ...
    ValueError: ... No Contact for ...

The external ID of the Contacts from other Clients is not considered. Move
the external ID to a Contact of another Client:

    >>> other_client = api.create(portal.clients, "Client",
    ...                           Name="Other Lab", ClientID="OTHER")
    >>> other_contact = api.create(other_client, "Contact",
    ...                            Firstname="Other", Surname="Contact")
    >>> IExtendedContactBehavior(contact).fhir_external_id = None
    >>> contact.reindexObject()
    >>> IExtendedContactBehavior(other_contact).fhir_external_id = (
    ...     u"PRACT-OTHER")
    >>> other_contact.reindexObject()

    >>> get_requester("PRACT-OTHER", family="Nobody")
    Traceback (most recent call last):
    ...
    ValueError: ... No Contact for ...

Restore the external ID of the Contact:

    >>> IExtendedContactBehavior(contact).fhir_external_id = (
    ...     u"PRACT-DR-SULLIVAN")
    >>> contact.reindexObject()
    >>> transaction.commit()


Re-post the same Bundle (idempotent update)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Posting the same Bundle again resolves every resource to its existing
counterpart and updates it in place, instead of creating duplicates. We
tweak the ServiceRequest priority (``routine`` -> ``stat``) to observe that
the change is propagated to the Sample. The Sample is currently routine::

    >>> sample.getPriority()
    '5'

Bump the priority on the same ServiceRequest and re-post the Bundle::

    >>> service_request = [e["resource"] for e in bundle["entry"]
    ...                    if e["resource"]["resourceType"] == "ServiceRequest"][0]
    >>> service_request["priority"] = "stat"
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)

The same five resources are reported, now consistently as updated::

    >>> entries = response["entry"]
    >>> sorted([e["fullUrl"].split("/")[0] for e in entries])
    [u'Organization', u'Patient', u'Practitioner', u'ServiceRequest', u'Specimen']

    >>> sorted(set(e["response"]["status"] for e in entries))
    [u'200 OK']

No duplicates are created -- it is still the same Sample, now ``stat``::

    >>> portal._p_jar.sync()
    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> fapi.get_uid(samples[0]) == fapi.get_uid(sample)
    True
    >>> samples[0].getPriority()
    '1'


Practitioner matched by its external ID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A repeat order may carry the same practitioner under a FHIR id that is not
known by SENAITE. The `Practitioner` is then matched by its external ID to
the existing Contact of the Client, instead of creating a duplicate.

Only the Contacts of the Client are considered. Give a Contact of another
Client the same external ID:

    >>> another_client = api.create(portal.clients, "Client",
    ...                             Name="Another Lab", ClientID="ANOTHER")
    >>> another_contact = api.create(another_client, "Contact",
    ...                              Firstname="Another", Surname="Contact")
    >>> another_contact.setFHIRExternalID("PRACT-DR-SULLIVAN")
    >>> another_contact.reindexObject()
    >>> transaction.commit()

Post the bundle with a `Practitioner` that has a FHIR id not known by SENAITE:

    >>> repeat = json.loads(raw)
    >>> practitioner_id = "0f0f0f0f-1111-4222-8333-444455556666"
    >>> fapi.get_object(practitioner_id, default=None) is None
    True

    >>> for entry in repeat["entry"]:
    ...     resource = entry["resource"]
    ...     if resource["resourceType"] == "Practitioner":
    ...         resource["id"] = practitioner_id
    ...     if resource["resourceType"] == "ServiceRequest":
    ...         reference = "Practitioner/{}".format(practitioner_id)
    ...         resource["requester"]["reference"] = reference

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(repeat),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)

The `Practitioner` is reported as updated rather than created:

    >>> [e["response"]["status"] for e in response["entry"]
    ...  if e["fullUrl"].startswith("Practitioner/")]
    [u'200 OK']

No new Contact was created, and the existing one is now linked to the new
FHIR id of the `Practitioner`:

    >>> portal._p_jar.sync()
    >>> contacts = [obj for obj in client.objectValues()
    ...             if api.get_portal_type(obj) == "Contact"]
    >>> contacts == [contact]
    True
    >>> fapi.get_fhir_id(contact, "Practitioner") == practitioner_id
    True
    >>> sample.getContact() == contact
    True

Nor was the Contact of the other Client modified:

    >>> fapi.get_fhir_id(another_contact, "Practitioner") == practitioner_id
    False

Posting the `Practitioner` without its external ID does not wipe the one the
Contact already has:

    >>> for entry in repeat["entry"]:
    ...     resource = entry["resource"]
    ...     if resource["resourceType"] == "Practitioner":
    ...         _ = resource.pop("identifier", None)

    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(repeat),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)
    >>> [e["response"]["status"] for e in response["entry"]
    ...  if e["fullUrl"].startswith("Practitioner/")]
    [u'200 OK']

    >>> portal._p_jar.sync()
    >>> contact.getFHIRExternalID()
    'PRACT-DR-SULLIVAN'


Update a manually-created counterpart (matched by MRN)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A counterpart need not have been created through the FHIR layer to be
updated: when there is no FHIR-UID match, the ``IContentFinder`` adapter
resolves it by a business key. ``PatientFinder`` matches a Patient by its
medical record number. Create a Patient manually first::

    >>> manual = api.create(portal.patients, "Patient", mrn=u"MRN-MANUAL",
    ...                     firstname=u"Manual", lastname=u"Patient")
    >>> transaction.commit()
    >>> before = len([obj for obj in portal.patients.objectValues()
    ...               if api.get_portal_type(obj) == "Patient"])

Post a Patient resource carrying a *different* logical id but the same MRN,
so it can only be matched by MRN (not by FHIR UID)::

    >>> incoming = {
    ...     "resourceType": "Patient",
    ...     "id": "bbbbbbbb-bbbb-5bbb-9bbb-bbbbbbbbbbbb",
    ...     "name": [{"use": "official", "family": "Patient",
    ...               "given": ["Manual"]}],
    ...     "telecom": [{"system": "phone",
    ...                  "value": "+61 3 9444 5555",
    ...                  "use": "home"}],
    ...     "gender": "male",
    ...     "birthDate": "1970-01-01",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "MRN-MANUAL"}],
    ... }
    >>> browser.post("{}/Patient".format(fhir_url), json.dumps(incoming),
    ...              content_type="application/json")
    >>> response = json.loads(browser.contents)

The existing Patient is matched and updated, not duplicated::

    >>> entries = response["entry"]
    >>> entries[0]["fullUrl"].split("/")[0]
    u'Patient'
    >>> entries[0]["response"]["status"]
    u'200 OK'

    >>> portal._p_jar.sync()
    >>> after = len([obj for obj in portal.patients.objectValues()
    ...              if api.get_portal_type(obj) == "Patient"])
    >>> after == before
    True

It is now linked to the posted resource's FHIR id, so resolving by that id
returns the same manually-created Patient::

    >>> match = fapi.get_object_by_fhir_uid(
    ...     "bbbbbbbb-bbbb-5bbb-9bbb-bbbbbbbbbbbb", "Patient")
    >>> fapi.get_uid(match) == fapi.get_uid(manual)
    True
    >>> match.getPhone()
    '+61 3 9444 5555'
