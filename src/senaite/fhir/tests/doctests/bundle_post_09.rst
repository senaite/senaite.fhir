FHIR Bundle POST (Patient/Organization/Practitioner identifier validation)
---------------------------------------------------------------------------

Tests the same internal-id/external-id validation pattern used by
`ResourceToAnalysisRequest.validate_identifiers()` (see `bundle_post_08.rst`),
now applied to `ResourceToPatient`, `ResourceToOrganisation` and
`ResourceToContact`:

1. **Rejection of usual identifier**: a `Patient`, `Organization` or
   `Practitioner` carrying an identifier with `use="usual"` is rejected, since
   internal ids are assigned by SENAITE only after creation.

2. **Rejection of external identifier with no/unsupported system**: a
   `use="secondary"` identifier with no `system`, or one other than the
   type's fixed default `NamingSystem`, is rejected. Every external
   identifier is checked, whatever its position.

3. **Rejection of identifiers that are not `use="secondary"`**: any
   identifier other than an internal (`usual`) one must have
   `use="secondary"`; one with no `use`, or another one, is rejected.

4. **Success**: a `use="secondary"` identifier under the correct default
   system is accepted and mapped to the counterpart SENAITE field (Patient's
   MRN, Client's `ClientID`, Contact's `fhir_external_id`).

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_09


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


Rejection: Patient with a usual identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "usual",
    ...     "system": "https://fhir.senaite.org/NamingSystem/patient-id",
    ...     "value": "P000999"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Cannot specify usual identifier externally in incoming Patient" in (
    ...     error_text(outcome))
    True
    >>> no_clients_created()
    True


Rejection: Patient with an external identifier carrying no system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "secondary",
    ...     "value": "MRN-NO-SYSTEM"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier system in Patient" in error_text(outcome)
    True
    >>> no_clients_created()
    True


Rejection: Patient with an additional external identifier of another system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A `Patient` can only carry external identifiers of its own `NamingSystem`.
Another one is rejected, even when it comes after a valid MRN:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "secondary",
    ...     "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...     "value": "MRN-VALID",
    ... }, {
    ...     "use": "secondary",
    ...     "system": "urn:oid:2.16.840.1.113883.4.1",
    ...     "value": "NATIONAL-ID",
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier system in Patient" in error_text(outcome)
    True
    >>> no_clients_created()
    True

The external identifier of a resource is the one with the `NamingSystem` its
type supports, whatever its position:

    >>> from senaite.fhir import api as fapi
    >>> resource = fapi.to_fhir_resource({
    ...     "resourceType": "Patient",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "urn:oid:2.16.840.1.113883.4.1",
    ...         "value": "NATIONAL-ID",
    ...     }, {
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "MRN-VALID",
    ...     }],
    ... })
    >>> resource.external_id_system
    'patient-mrn'
    >>> resource.get_external_id().value
    'MRN-VALID'

A resource whose type supports no external identifier has none:

    >>> service_request = fapi.to_fhir_resource({
    ...     "resourceType": "ServiceRequest",
    ...     "identifier": [{
    ...         "use": "secondary",
    ...         "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...         "value": "MRN-VALID",
    ...     }],
    ... })
    >>> service_request.external_id_system is None
    True
    >>> service_request.get_external_id() is None
    True


Rejection: Organization with a usual identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Organization")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "usual",
    ...     "system": "https://fhir.senaite.org/NamingSystem/organization-id",
    ...     "value": "client-999"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Cannot specify usual identifier externally in incoming Organization"\
    ...     in error_text(outcome)
    True
    >>> no_clients_created()
    True


Rejection: Organization with an unsupported external identifier system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Organization")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "secondary",
    ...     "system": "https://example.org/NamingSystem/their-own-id",
    ...     "value": "ORG-OTHER"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier system in Organization" in error_text(outcome)
    True
    >>> no_clients_created()
    True


Rejection: Practitioner with a usual identifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Practitioner")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "usual",
    ...     "system": (
    ...         "https://fhir.senaite.org/NamingSystem/practitioner-id"),
    ...     "value": "practitioner-999"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Cannot specify usual identifier externally in incoming Practitioner"\
    ...     in error_text(outcome)
    True
    >>> no_clients_created()
    True


Rejection: Practitioner with an external identifier carrying no system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Practitioner")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "secondary",
    ...     "value": "PRACT-NO-SYSTEM"
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier system in Practitioner" in error_text(outcome)
    True
    >>> no_clients_created()
    True


Rejection: identifiers that are not `use="secondary"`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The consumer can only send external identifiers, so any identifier other than
an internal (`usual`) one must have `use="secondary"`. One with the supported
system but no `use` is rejected, instead of being silently ignored:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["identifier"] = [{
    ...     "system": "https://fhir.senaite.org/NamingSystem/patient-mrn",
    ...     "value": "MRN-NO-USE",
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Missing identifier use in Patient" in error_text(outcome)
    True
    >>> no_clients_created()
    True

So is one with any other `use`:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Practitioner")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "official",
    ...     "system": (
    ...         "https://fhir.senaite.org/NamingSystem/"
    ...         "practitioner-external-id"),
    ...     "value": "PRACT-OFFICIAL",
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier use in Practitioner: official" in (
    ...     error_text(outcome))
    True
    >>> no_clients_created()
    True

This also covers an internal identifier sent under another `use`:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Organization")
    >>> entry["resource"]["identifier"] = [{
    ...     "use": "official",
    ...     "system": "https://fhir.senaite.org/NamingSystem/organization-id",
    ...     "value": "client-999",
    ... }]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Unsupported identifier use in Organization: official" in (
    ...     error_text(outcome))
    True
    >>> no_clients_created()
    True


Success: external identifiers under the correct default systems
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With `Patient`, `Organization` and `Practitioner` each carrying a
`use="secondary"` identifier under their correct default `NamingSystem`, the
bundle is accepted and each identifier is mapped onto the matching SENAITE
object:

    >>> bundle = load_bundle()
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> response["type"]
    u'transaction-response'

The Patient's MRN matches the Patient resource's external identifier
(``MRN-20394857``, from ``Bundle.01.json``):

    >>> portal._p_jar.sync()
    >>> patient = papi.get_patient_by_mrn("MRN-20394857")
    >>> patient.getMRN()
    'MRN-20394857'

The Client's ID matches the Organization resource's external identifier
(``ORG-RMH-MEL``):

    >>> clients = portal.clients.objectValues("Client")
    >>> len(clients)
    1
    >>> client = clients[0]
    >>> client.getClientID()
    'ORG-RMH-MEL'

The Contact's `fhir_external_id` matches the Practitioner resource's external
identifier (``PRACT-DR-SULLIVAN``):

    >>> contacts = client.getContacts()
    >>> len(contacts)
    1
    >>> contacts[0].getFHIRExternalID()
    'PRACT-DR-SULLIVAN'


Rejection: invalid identifiers on resources that already exist
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The resources are validated before their counterpart objects are searched, so
the rules apply to the objects that already exist as well. Send the same
bundle again, now with the existing Patient also carrying a usual identifier:

    >>> bundle = load_bundle()
    >>> entry = get_entry(bundle, "Patient")
    >>> entry["resource"]["identifier"].append({
    ...     "use": "usual",
    ...     "system": "https://fhir.senaite.org/NamingSystem/patient-id",
    ...     "value": "P-999",
    ... })
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> "Cannot specify usual identifier externally in incoming Patient" in (
    ...     error_text(outcome))
    True

The rules are those of the converter of the resource, available through the
API as well:

    >>> from senaite.fhir import api as fapi
    >>> from senaite.fhir.exceptions import IdentifierValidationError
    >>> patient_resource = fapi.to_fhir_resource(entry["resource"])
    >>> try:
    ...     fapi.validate(patient_resource)
    ... except IdentifierValidationError as e:
    ...     print(e.expression)
    ['Patient.identifier']
