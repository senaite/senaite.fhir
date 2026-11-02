FHIR Specimen Read
------------------

Verify that ``GET /senaite/@@FHIR/r5/Specimen/<id>`` returns the correct
FHIR ``Specimen`` resource for both a **native** SENAITE AnalysisRequest
(synthesised on-the-fly by the ``AnalysisRequestToSpecimen`` named adapter)
and an **annotation-stored** Specimen (written by ``link_fhir_resource`` as
a bundle POST would do).

Also verifies:

- The SNOMED system code (``http://snomed.info/sct``) appears on the ``type``
  and ``bodySite`` codings.
- ``collection.collectedDateTime`` is populated from the AR's DateSampled.
- Both the 36-char dashed UUID and the 32-char hex UID forms are accepted.
- Requests for unknown UUIDs return a ``404``.
- ARs without a ``SamplePoint`` produce a Specimen with no ``bodySite``.
- The ``status`` is mapped from the status of the AR.

Running this test from the buildout directory:

    bin/test test_doctests -t specimen_read


Test Setup
~~~~~~~~~~

Needed imports:

    >>> import json
    >>> import uuid
    >>> import transaction
    >>> from DateTime import DateTime
    >>> from plone.app.testing import setRoles
    >>> from plone.app.testing import TEST_USER_ID
    >>> from bika.lims import api
    >>> from bika.lims.utils.analysisrequest import create_analysisrequest
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


Setup objects
~~~~~~~~~~~~~

Create the minimum set of objects to register samples:

    >>> client = api.create(portal.clients, "Client",
    ...                     Name="Metro Lab", ClientID="ML")
    >>> contact = api.create(client, "Contact",
    ...                      Firstname="Sam", Lastname="Lee")
    >>> sampletype = api.create(setup.sampletypes, "SampleType",
    ...                         title="Whole Blood", Prefix="WB")
    >>> samplepoint = api.create(setup.samplepoints, "SamplePoint",
    ...                          title="Antecubital Vein")
    >>> labcontact = api.create(portal.bika_setup.bika_labcontacts,
    ...                         "LabContact", Firstname="Lab", Lastname="Chief")
    >>> department = api.create(setup.departments, "Department",
    ...                         title="Haematology", Manager=labcontact)
    >>> category = api.create(setup.analysiscategories, "AnalysisCategory",
    ...                       title="CBC", Department=department)
    >>> Hb = api.create(portal.bika_setup.bika_analysisservices,
    ...                 "AnalysisService", title="Haemoglobin", Keyword="Hb",
    ...                 Category=category.UID())


Create native AnalysisRequest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a native AR with a SampleType, SamplePoint and DateSampled.  The
FHIR layer synthesises a Specimen from it on-the-fly via the
``AnalysisRequestToSpecimen`` named adapter:

    >>> values = {
    ...     "Client": client.UID(),
    ...     "Contact": contact.UID(),
    ...     "DateSampled": DateTime().strftime("%Y-%m-%d"),
    ...     "SampleType": sampletype.UID(),
    ...     "SamplePoint": samplepoint.UID(),
    ...     "ClientSampleID": "EXT-WB-0042",
    ... }
    >>> sample = create_analysisrequest(client, request, values, [Hb.UID()])
    >>> sample
    <AnalysisRequest at /plone/clients/...>
    >>> sample_uid = api.get_uid(sample)
    >>> transaction.commit()

The synthesised Specimen id is the AR's SENAITE UID reformatted as a
dashed UUID:

    >>> specimen_id = str(uuid.UUID(sample_uid))
    >>> specimen_id != sample_uid
    True


GET /Specimen/<id> – 36-char dashed UUID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Fetching the native specimen by its dashed-UUID id returns the synthesised
Specimen resource:

    >>> browser.open("{}/Specimen/{}".format(fhir_url, specimen_id))
    >>> spec = json.loads(browser.contents)
    >>> spec["resourceType"]
    u'Specimen'
    >>> spec["id"] == specimen_id
    True

The ``status`` is mapped from the status of the AR. A sample that is due is
available:

    >>> spec["status"]
    u'available'

The SENAITE specimen barcode is supplied as a base64-encoded SVG attachment
in its own extension. It uses the internal sample ID encoded as Code 128, so
the receiving system can render it at its own printer resolution:

    >>> import base64
    >>> barcode_extensions = [extension for extension in spec["extension"]
    ...                       if extension["url"] == (
    ...                           "https://fhir.senaite.org/StructureDefinition/"
    ...                           "SenaiteSpecimenBarcode")]
    >>> len(barcode_extensions)
    1
    >>> barcode = barcode_extensions[0]["valueAttachment"]
    >>> barcode["contentType"]
    u'image/svg+xml'
    >>> b"<svg" in base64.b64decode(barcode["data"])
    True

The ``type`` coding carries the SNOMED system code and the SampleType title:

    >>> spec["type"]["coding"][0]["system"]
    u'http://snomed.info/sct'
    >>> spec["type"]["coding"][0]["display"]
    u'Whole Blood'

The ``identifier`` list carries SENAITE's sample ID as the ``usual``
identifier and, when present, the client's sample ID as a ``secondary``
identifier:

    >>> sample_identifier = spec["identifier"][0]
    >>> sample_identifier["value"] == sample.getId()
    True
    >>> sample_identifier["use"]
    u'usual'
    >>> sample_identifier["system"] == (
    ...     "https://fhir.senaite.org/NamingSystem/sample-id")
    True
    >>> client_identifier = spec["identifier"][1]
    >>> client_identifier["value"]
    u'EXT-WB-0042'
    >>> client_identifier["use"]
    u'secondary'
    >>> client_identifier["system"] == (
    ...     "https://fhir.senaite.org/NamingSystem/client-sample-id")
    True

The ``collection.collectedDateTime`` is present and non-empty:

    >>> "collectedDateTime" in spec.get("collection", {})
    True
    >>> bool(spec["collection"]["collectedDateTime"])
    True

The ``collection.bodySite`` coding uses the same SNOMED system and carries
the SamplePoint title:

    >>> spec["collection"]["bodySite"]["concept"]["coding"][0]["system"]
    u'http://snomed.info/sct'
    >>> spec["collection"]["bodySite"]["concept"]["coding"][0]["display"]
    u'Antecubital Vein'


GET /Specimen/<id> – 32-char hex UID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The same specimen is also reachable via the AR's raw 32-character hex UID
(the route accepts both length-32 and length-36 forms):

    >>> browser.open("{}/Specimen/{}".format(fhir_url, sample_uid))
    >>> spec2 = json.loads(browser.contents)
    >>> spec2["resourceType"]
    u'Specimen'
    >>> spec2["id"] == specimen_id
    True


GET /Specimen/<id> – 404 for unknown id
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A UUID that does not correspond to any AR or stored Specimen returns 404:

    >>> browser.open("{}/Specimen/{}".format(fhir_url,
    ...              "00000000-0000-0000-0000-000000000001"))
    >>> browser.headers["Status"]
    '404 Not Found'


Native specimen without SamplePoint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An AR created without a ``SamplePoint`` produces a Specimen whose
``collection`` has no ``bodySite``:

    >>> values_no_sp = {
    ...     "Client": client.UID(),
    ...     "Contact": contact.UID(),
    ...     "DateSampled": DateTime().strftime("%Y-%m-%d"),
    ...     "SampleType": sampletype.UID(),
    ... }
    >>> sample_no_sp = create_analysisrequest(
    ...     client, request, values_no_sp, [Hb.UID()])
    >>> sample_no_sp_uid = api.get_uid(sample_no_sp)
    >>> transaction.commit()

    >>> sp_id = str(uuid.UUID(sample_no_sp_uid))
    >>> browser.open("{}/Specimen/{}".format(fhir_url, sp_id))
    >>> sp_no_bodysite = json.loads(browser.contents)
    >>> sp_no_bodysite["resourceType"]
    u'Specimen'
    >>> "bodySite" in sp_no_bodysite.get("collection", {})
    False


Annotation-stored Specimen
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a Specimen is stored against an AR via ``link_fhir_resource`` with
``secondary=True`` (the path taken after a FHIR bundle POST), fetching it by
its own FHIR id returns the stored data rather than the on-the-fly synthesis:

    >>> stored_id = "b1234567-89ab-cdef-0123-456789abcdef"
    >>> stored_specimen = fapi.to_fhir_resource({
    ...     "resourceType": "Specimen",
    ...     "id": stored_id,
    ...     "type": {
    ...         "coding": [{
    ...             "system": "http://snomed.info/sct",
    ...             "display": "Serum specimen",
    ...         }]
    ...     },
    ...     "extension": [{
    ...         "url": "https://example.org/StructureDefinition/keep-me",
    ...         "valueString": "preserved",
    ...     }],
    ... })
    >>> fapi.link_fhir_resource(sample, stored_specimen, secondary=True)
    >>> transaction.commit()

Fetching by the stored Specimen's own FHIR id returns the annotation-backed
resource:

    >>> browser.open("{}/Specimen/{}".format(fhir_url, stored_id))
    >>> ann = json.loads(browser.contents)
    >>> ann["resourceType"]
    u'Specimen'
    >>> ann["id"]
    u'b1234567-89ab-cdef-0123-456789abcdef'
    >>> ann["type"]["coding"][0]["display"]
    u'Serum specimen'
    >>> len(ann["extension"])
    1
    >>> ann["extension"][0]["url"]
    u'https://fhir.senaite.org/StructureDefinition/SenaiteSpecimenBarcode'

Once the annotation is in place, fetching by the original AR-based Specimen
id also returns the stored resource, because the annotation store takes
priority over the on-the-fly adapter:

    >>> browser.open("{}/Specimen/{}".format(fhir_url, specimen_id))
    >>> shadowed = json.loads(browser.contents)
    >>> shadowed["id"]
    u'b1234567-89ab-cdef-0123-456789abcdef'

    >>> browser.raiseHttpErrors = True
