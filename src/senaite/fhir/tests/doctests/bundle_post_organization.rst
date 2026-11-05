FHIR Bundle POST (Organization)
-------------------------------

The Organization of a bundle is the Client the Sample is registered for. It
is matched to an existing Client by its external identifier, the `ClientID`,
and only by it: two Clients can share a name, and a renamed one would no
longer match. When no Client has the ClientID, the Client is created from the
Organization.

- The `contact` of an Organization is optional: it carries the address, phone
  and email of the Client, which are left empty when the Organization has
  none.
- The ClientID is required, as it is the only key: without it, every bundle
  would create another Client.
- The name is required, as it is the name of the Client.
- A ClientID shared by more than one Client cannot be resolved without
  guessing, so the bundle is rejected with `412 Precondition Failed`, naming
  the Clients.

Running this test from the buildout directory:

    bin/test test_doctests -t bundle_post_organization


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import transaction
    >>> from pkg_resources import resource_string
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api

Variables:

    >>> portal = self.portal
    >>> setup = portal.setup
    >>> fhir_url = "{}/@@FHIR/r5".format(portal.absolute_url())
    >>> browser = self.getBrowser()
    >>> browser.raiseHttpErrors = False
    >>> setRoles(portal, TEST_USER_ID, ["LabManager", "Manager"])

Helpers:

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

Each scenario sends its own Organization and ServiceRequest, with their own
placeholder ids, so they are not resolved to the ones of a previous scenario:

    >>> def new_bundle(org_id, sr_id, client_id):
    ...     bundle = load_bundle()
    ...     org_entry = get_entry(bundle, "Organization")
    ...     org_entry["fullUrl"] = "urn:uuid:{}".format(org_id)
    ...     org_entry["resource"]["identifier"][0]["value"] = client_id
    ...     sr_entry = get_entry(bundle, "ServiceRequest")
    ...     sr_entry["fullUrl"] = "urn:uuid:{}".format(sr_id)
    ...     ext = sr_entry["resource"]["extension"][0]
    ...     ext["valueReference"]["reference"] = "urn:uuid:{}".format(org_id)
    ...     return bundle

    >>> def clients(client_id=None):
    ...     portal._p_jar.sync()
    ...     found = portal.clients.objectValues("Client")
    ...     if client_id:
    ...         found = [c for c in found if c.getClientID() == client_id]
    ...     return found


Setup objects
~~~~~~~~~~~~~

The SampleType and analysis services the bundle requests. There is no Client
yet: it is created from the Organization:

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
    >>> portal.clients.objectValues("Client")
    []


Post a bundle whose Organization carries no contact
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    >>> raw = resource_string("senaite.fhir.tests", "data/Bundle.01.json")
    >>> bundle = json.loads(raw)
    >>> organization = [e["resource"] for e in bundle["entry"]
    ...                 if e["resource"]["resourceType"] == "Organization"][0]
    >>> contact = organization.pop("contact")
    >>> browser.post("{}/Bundle".format(fhir_url), json.dumps(bundle),
    ...              content_type="application/json")
    >>> browser.headers["Status"]
    '200 OK'

The Client is created from the Organization, with its name, and without
address, phone nor email:

    >>> portal._p_jar.sync()
    >>> client = portal.clients.objectValues("Client")[0]
    >>> client.getName(), client.getClientID()
    ('Royal Melbourne Hospital', 'ORG-RMH-MEL')
    >>> client.getPhysicalAddress().get("address", "")
    ''
    >>> client.getPhone(), client.getEmailAddress()
    ('', '')

And the Sample is registered for it:

    >>> len(client.objectValues("AnalysisRequest"))
    1


Matched by ClientID, not by name
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An Organization with the same name, but another ClientID, is not the same
Client: a new one is created:

    >>> before = len(clients())
    >>> bundle = new_bundle("a1a1a1a1-a1a1-5a1a-9a1a-a1a1a1a1a1a1",
    ...                     "b1b1b1b1-b1b1-5b1b-9b1b-b1b1b1b1b1b1",
    ...                     "ORG-RMH-NEW")
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> len(clients()) == before + 1
    True
    >>> new_client = clients("ORG-RMH-NEW")[0]
    >>> new_client.getName()
    'Royal Melbourne Hospital'
    >>> len(new_client.objectValues("AnalysisRequest"))
    1

An Organization with the ClientID of an existing Client is that Client, even
with another name. The Client is updated, with the name stripped of
surrounding spaces, and no other is created:

    >>> before = len(clients())
    >>> bundle = new_bundle("a2a2a2a2-a2a2-5a2a-9a2a-a2a2a2a2a2a2",
    ...                     "b2b2b2b2-b2b2-5b2b-9b2b-b2b2b2b2b2b2",
    ...                     "ORG-RMH-NEW")
    >>> get_entry(bundle, "Organization")["resource"]["name"] = u"  Renamed "
    >>> status, response = post_bundle(bundle)
    >>> status
    '200 OK'
    >>> len(clients()) == before
    True
    >>> new_client.getName()
    'Renamed'
    >>> len(new_client.objectValues("AnalysisRequest"))
    2


Rejection: a ClientID shared by more than one Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two Clients have the same ClientID:

    >>> dup1 = api.create(portal.clients, "Client", Name="Duplicate One",
    ...                   ClientID="ORG-DUP")
    >>> dup2 = api.create(portal.clients, "Client", Name="Duplicate Two",
    ...                   ClientID="ORG-DUP")
    >>> transaction.commit()
    >>> before = len(clients())

The bundle is rejected, rather than creating a third one or picking one of
them. The outcome names the Clients:

    >>> bundle = new_bundle("a3a3a3a3-a3a3-5a3a-9a3a-a3a3a3a3a3a3",
    ...                     "b3b3b3b3-b3b3-5b3b-9b3b-b3b3b3b3b3b3",
    ...                     "ORG-DUP")
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '412 Precondition Failed'
    >>> issue = outcome["issue"][0]
    >>> issue["code"], issue["expression"]
    (u'multiple-matches', [u'Organization.identifier'])
    >>> duplicates = ", ".join(sorted([api.get_id(dup1), api.get_id(dup2)]))
    >>> issue["details"]["text"] == (
    ...     "Multiple Clients with ClientID ORG-DUP: " + duplicates)
    True

Nothing was created:

    >>> len(clients()) == before
    True
    >>> dup1.objectValues("AnalysisRequest") + dup2.objectValues(
    ...     "AnalysisRequest")
    []


Rejection: an Organization without name
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The name of the Client is required, so an Organization without name, or with
a blank one, is rejected, whether it would create a Client or update one:

    >>> for client_id, name in (("ORG-NO-NAME", None), ("ORG-RMH-NEW", u"  ")):
    ...     bundle = new_bundle("a4a4a4a4-a4a4-5a4a-9a4a-a4a4a4a4a4a4",
    ...                         "b4b4b4b4-b4b4-5b4b-9b4b-b4b4b4b4b4b4",
    ...                         client_id)
    ...     organization = get_entry(bundle, "Organization")["resource"]
    ...     if name is None:
    ...         del organization["name"]
    ...     else:
    ...         organization["name"] = name
    ...     status, outcome = post_bundle(bundle)
    ...     issue = outcome["issue"][0]
    ...     print(status)
    ...     print(issue["code"], issue["expression"])
    ...     print(issue["details"]["text"])
    400 Bad Request
    (u'invalid', [u'Organization.name'])
    Missing name in Organization
    400 Bad Request
    (u'invalid', [u'Organization.name'])
    Missing name in Organization

Nothing was created nor updated:

    >>> clients("ORG-NO-NAME")
    []
    >>> new_client.getName()
    'Renamed'


Rejection: an Organization without ClientID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ClientID is the only key the Organization is matched by, so an
Organization without external identifier is rejected:

    >>> before = len(clients())
    >>> bundle = new_bundle("a5a5a5a5-a5a5-5a5a-9a5a-a5a5a5a5a5a5",
    ...                     "b5b5b5b5-b5b5-5b5b-9b5b-b5b5b5b5b5b5",
    ...                     "unused")
    >>> del get_entry(bundle, "Organization")["resource"]["identifier"]
    >>> status, outcome = post_bundle(bundle)
    >>> status
    '400 Bad Request'
    >>> issue = outcome["issue"][0]
    >>> issue["code"], issue["expression"]
    (u'invalid', [u'Organization.identifier'])
    >>> print(issue["details"]["text"])
    Missing external identifier in Organization

Nothing was created:

    >>> len(clients()) == before
    True

