FHIR Practitioner read and search
---------------------------------

A SENAITE `Contact` is served as a FHIR `Practitioner`, following the
`SenaitePractitioner` profile. The IG requires both the read, so the logical
id returned in a transaction response can be dereferenced and reused in later
bundles, and the search by identifier, that backs the conditional create
(`request.ifNoneExist`) of Practitioner entries.

See https://fhir.senaite.org/StructureDefinition-SenaitePractitioner.html

Running this test from the buildout directory:

    bin/test test_doctests -t practitioner_read


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> import uuid
    >>> from bika.lims import api
    >>> from bika.lims.workflow import doActionFor as do_action_for
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from senaite.fhir import api as fapi
    >>> from six.moves.urllib_parse import urlencode

Variables:

    >>> portal = self.portal
    >>> portal_url = portal.absolute_url()
    >>> fhir_url = "{}/@@FHIR/r5".format(portal_url)
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

    >>> internal_system = (
    ...     "https://fhir.senaite.org/NamingSystem/practitioner-id")
    >>> external_system = (
    ...     "https://fhir.senaite.org/NamingSystem/practitioner-external-id")

Some helpers:

    >>> def read(fhir_id):
    ...     browser.open("{}/Practitioner/{}".format(fhir_url, fhir_id))
    ...     return json.loads(browser.contents)

    >>> def search(**params):
    ...     query = urlencode(params, doseq=True)
    ...     browser.open("{}/Practitioner?{}".format(fhir_url, query))
    ...     return json.loads(browser.contents)

    >>> def get_identifiers(resource):
    ...     return [(i["use"], i["system"], i["value"])
    ...             for i in resource["identifier"]]


Setup objects
~~~~~~~~~~~~~

Create a Client and a Contact with a name, the ways to contact them, an
address and the external ID assigned by the system of the API consumer:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Alfred Hospital", ClientID="ALFRED")
    >>> contact = api.create(client, "Contact",
    ...                      Salutation="Dr.", Firstname="John",
    ...                      Middlename="Paul", Surname="Smith",
    ...                      EmailAddress="john.smith@hospital.com",
    ...                      BusinessPhone="+61 3 9076 1234",
    ...                      MobilePhone="+61 400 000 000")
    >>> contact.setPhysicalAddress([{
    ...     "type": "physical",
    ...     "address": "55 Commercial Rd",
    ...     "city": "Melbourne",
    ...     "zip": "3004",
    ...     "subdivision1": "Victoria",
    ...     "country": "Australia",
    ... }])
    >>> contact.setFHIRExternalID("PRAC-001")
    >>> contact.reindexObject()
    >>> transaction.commit()


Read
~~~~

The Practitioner of a Contact not created through the FHIR API has the UID
of the Contact as its logical id:

    >>> contact_id = str(uuid.UUID(api.get_uid(contact)))
    >>> practitioner = read(contact_id)
    >>> browser.headers["Status"]
    '200 OK'
    >>> practitioner["resourceType"]
    u'Practitioner'
    >>> practitioner["id"] == contact_id
    True
    >>> practitioner["meta"]["profile"]
    [u'https://fhir.senaite.org/StructureDefinition/SenaitePractitioner']

It is also reachable by the 32-char hex form of the UID:

    >>> read(api.get_uid(contact))["id"] == contact_id
    True

It carries the internal identifier assigned by SENAITE (`usual`) and the one
assigned by the system of the API consumer (`secondary`):

    >>> get_identifiers(practitioner) == [
    ...     ("usual", internal_system, contact.getId()),
    ...     ("secondary", external_system, "PRAC-001"),
    ... ]
    True

The official name, with the salutation as prefix:

    >>> practitioner["name"] == [{
    ...     "use": "official",
    ...     "prefix": ["Dr."],
    ...     "given": ["John", "Paul"],
    ...     "family": "Smith",
    ... }]
    True

The ways to contact the practitioner:

    >>> for point in practitioner["telecom"]:
    ...     print("{system} {use} {value}".format(**point))
    email work john.smith@hospital.com
    phone work +61 3 9076 1234
    phone mobile +61 400 000 000

And its address, with the ISO 3166 code of the country:

    >>> address = practitioner["address"][0]
    >>> address["use"], address["type"]
    (u'work', u'physical')
    >>> address["line"], address["city"], address["postalCode"]
    ([u'55 Commercial Rd'], u'Melbourne', u'3004')
    >>> address["state"], address["country"]
    (u'Victoria', u'AU')

Only the addresses with content are returned. The Contact has no postal
address:

    >>> len(practitioner["address"])
    1

The Practitioner is active as long as the Contact is:

    >>> practitioner["active"]
    True


Read by the id of the posted resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Contact created from a Practitioner of a bundle is linked to the id of that
Practitioner, so the Practitioner is read by it:

    >>> posted_id = "e04a8f16-2c7d-4b95-9a83-5f61c2e08d47"
    >>> posted = fapi.to_fhir_resource({
    ...     "resourceType": "Practitioner",
    ...     "id": posted_id,
    ...     "name": [{"family": "Sullivan", "given": ["Catherine"]}],
    ... })
    >>> other = api.create(client, "Contact",
    ...                    Firstname="Catherine", Surname="Sullivan")
    >>> fapi.link_fhir_resource(other, posted)
    >>> transaction.commit()

    >>> practitioner = read(posted_id)
    >>> practitioner["id"] == posted_id
    True
    >>> practitioner["name"][0]["family"]
    u'Sullivan'

A Contact without external ID only carries the internal identifier, and no
telecom nor address:

    >>> get_identifiers(practitioner) == [
    ...     ("usual", internal_system, other.getId())]
    True
    >>> "telecom" in practitioner, "address" in practitioner
    (False, False)


Read of an unknown or inactive practitioner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An id that does not match any Contact is not found:

    >>> _ = read("00000000-0000-0000-0000-000000000001")
    >>> browser.headers["Status"]
    '404 Not Found'

A deactivated Contact is still served, but not active:

    >>> success = do_action_for(other, "deactivate")
    >>> transaction.commit()
    >>> read(posted_id)["active"]
    False


Search by identifier
~~~~~~~~~~~~~~~~~~~~

The Practitioner is found by the identifier assigned by the system of the API
consumer, as `<system>|<value>`:

    >>> bundle = search(identifier="{}|PRAC-001".format(external_system))
    >>> browser.headers["Status"]
    '200 OK'
    >>> bundle["resourceType"], bundle["type"], bundle["total"]
    (u'Bundle', u'searchset', 1)
    >>> entry = bundle["entry"][0]
    >>> entry["fullUrl"] == "Practitioner/{}".format(contact_id)
    True
    >>> entry["search"]
    {u'mode': u'match'}
    >>> entry["resource"]["id"] == contact_id
    True

And by the internal identifier assigned by SENAITE:

    >>> identifier = "{}|{}".format(internal_system, contact.getId())
    >>> bundle = search(identifier=identifier)
    >>> bundle["total"]
    1
    >>> bundle["entry"][0]["resource"]["id"] == contact_id
    True

The search matches on both the system and the value. No Practitioner is found
for an unknown value, nor for a known value within an unsupported system:

    >>> search(identifier="{}|PRAC-999".format(external_system))["total"]
    0
    >>> bundle = search(identifier="https://ehr.example.org|PRAC-001")
    >>> browser.headers["Status"], bundle["total"], "entry" in bundle
    ('200 OK', 0, False)

Nor by the external ID within the system of the internal ID, or vice versa:

    >>> search(identifier="{}|PRAC-001".format(internal_system))["total"]
    0
    >>> identifier = "{}|{}".format(external_system, contact.getId())
    >>> search(identifier=identifier)["total"]
    0


Invalid searches
~~~~~~~~~~~~~~~~

The identifier is required:

    >>> outcome = search()
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome["resourceType"]
    u'OperationOutcome'
    >>> issue = outcome["issue"][0]
    >>> issue["code"], issue["expression"]
    (u'required', [u'identifier'])

And so is its system:

    >>> outcome = search(identifier="PRAC-001")
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome["issue"][0]["code"]
    u'invalid'

    >>> outcome = search(identifier="|PRAC-001")
    >>> outcome["issue"][0]["code"]
    u'invalid'

    >>> outcome = search(identifier="{}|".format(external_system))
    >>> outcome["issue"][0]["code"]
    u'invalid'

Only one identifier is supported:

    >>> outcome = search(identifier=[
    ...     "{}|PRAC-001".format(external_system),
    ...     "{}|{}".format(internal_system, contact.getId()),
    ... ])
    >>> browser.headers["Status"]
    '400 Bad Request'
    >>> outcome["issue"][0]["code"]
    u'not-supported'

    >>> browser.raiseHttpErrors = True
