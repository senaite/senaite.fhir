FHIR Bundle POST (Organization without contact)
-----------------------------------------------

The `contact` of an Organization is optional: it carries the address, phone
and email of the Client, which are left empty when the Organization has none.
A bundle whose Organization carries no contact creates the Client all the
same.

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
