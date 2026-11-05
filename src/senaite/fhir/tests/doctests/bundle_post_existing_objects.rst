FHIR Bundle POST (objects that already exist)
---------------------------------------------

The counterpart objects of the resources of a bundle are matched by their
external identifiers (the Patient's MRN, the Client ID of the Organization,
the external ID of the Practitioner). SENAITE stores the value of these
identifiers, not their system, so the objects that already exist (e.g. created
by bundles sent before the identifier systems were required, or by hand) are
matched as well, and not duplicated, by bundles carrying the systems.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_existing_objects


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api
    >>> from senaite.patient import api as papi

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Setup objects needed for the bundle's ServiceRequest/Specimen to resolve:

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

A helper to load a fresh copy of the base bundle and find an entry by its
resource type:

    >>> def load_bundle():
    ...     raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    ...     return json.loads(raw)

    >>> def get_entry(bundle, resource_type):
    ...     return [e for e in bundle["entry"]
    ...             if e["resource"]["resourceType"] == resource_type][0]

    >>> def post_bundle(bundle):
    ...     browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...                  content_type="application/json")
    ...     return browser.headers["Status"], json.loads(browser.contents)

    >>> def error_text(outcome):
    ...     return outcome["issue"][0]["details"]["text"]

    >>> def no_clients_created():
    ...     portal._p_jar.sync()
    ...     return len(portal.clients.objectValues("Client")) == 0



Objects that already exist
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create the Client, its Contact and the Patient directly, with the values of
the external identifiers of the bundle, but not linked to any FHIR resource:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Royal Melbourne Hospital",
    ...                     ClientID="ORG-RMH-MEL")
    >>> contact = api.create(client, "Contact",
    ...                      Firstname="Catherine", Lastname="Sullivan")
    >>> contact.setFHIRExternalID("PRACT-DR-SULLIVAN")
    >>> contact.reindexObject()
    >>> patient = api.create(portal.patients, "Patient",
    ...                      mrn="MRN-20394857",
    ...                      firstname="James", lastname="Nguyen")
    >>> transaction.commit()

    >>> client_uid = api.get_uid(client)
    >>> contact_uid = api.get_uid(contact)
    >>> patient_uid = api.get_uid(patient)


Matched, not duplicated
~~~~~~~~~~~~~~~~~~~~~~~

Send the bundle, whose resources carry the external identifiers under their
NamingSystems:

    >>> bundle = load_bundle()
    >>> [i["system"] for i in get_entry(bundle, "Patient")["resource"]
    ...  ["identifier"]]
    [u'https://fhir.senaite.org/NamingSystem/patient-mrn']
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'

The objects that already existed are used, no other is created:

    >>> portal._p_jar.sync()
    >>> clients = portal.clients.objectValues("Client")
    >>> [api.get_uid(c) for c in clients] == [client_uid]
    True
    >>> contacts = client.getContacts()
    >>> [api.get_uid(c) for c in contacts] == [contact_uid]
    True
    >>> patients = portal.patients.objectValues()
    >>> [api.get_uid(p) for p in patients] == [patient_uid]
    True

And the sample is registered for them:

    >>> samples = client.objectValues("AnalysisRequest")
    >>> len(samples)
    1
    >>> api.get_uid(samples[0].getContact()) == contact_uid
    True
    >>> sample = samples[0]
    >>> sample.getField("MedicalRecordNumber").get(sample).get("value")
    'MRN-20394857'
