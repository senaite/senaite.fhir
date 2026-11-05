# -*- coding: utf-8 -*-

from bika.lims import api
from bika.lims.interfaces import IInstrument
from senaite.fhir import api as fapi
from senaite.fhir.config import DEVICE_ID_SYSTEM
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_identifier
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.resource.device import DeviceResource
from zope.component import adapter
from zope.interface import implementer


@adapter(IInstrument)
@implementer(IContentToFHIR)
class InstrumentToDevice(object):
    """Convert a SENAITE Instrument into a FHIR Device resource.
    """

    def __init__(self, instrument):
        self.instrument = instrument

    def to_fhir_resource(self):
        profile_url = to_fhir_profile_url("SenaiteDevice")
        data = {
            "resourceType": "Device",
            "id": fapi.get_fhir_id(self.instrument),
            "meta": {
                "profile": [profile_url],
                "lastUpdated": self.get_last_updated(),
            },
            "text": self.get_narrative(),
        }

        display_name = self.get_display_name()
        if display_name:
            data["displayName"] = display_name

        identifier = self.get_identifier()
        if identifier:
            data["identifier"] = identifier

        manufacturer = self.get_manufacturer()
        if manufacturer:
            data["manufacturer"] = manufacturer

        model = self.get_model()
        if model:
            data["modelNumber"] = model

        serial_no = self.get_serial_no()
        if serial_no:
            data["serialNumber"] = serial_no

        notes = self.get_notes()
        if notes:
            data["note"] = notes

        return DeviceResource(data)

    def get_last_updated(self):
        modified = api.get_modification_date(self.instrument)
        return to_fhir_datetime(modified)

    def get_display_name(self):
        return api.safe_unicode(api.get_title(self.instrument)) or None

    def get_identifier(self):
        """Returns the Device.identifier slices defined by the SenaiteDevice
        profile: the SENAITE-assigned id (use=usual, device-id NamingSystem)
        and, when set, the asset register number as an external id
        (use=secondary).
        """
        identifiers = []

        # senaiteId slice: SENAITE server-generated id
        senaite_id = to_fhir_identifier(
            DEVICE_ID_SYSTEM, api.get_id(self.instrument), use="usual")
        if senaite_id:
            identifiers.append(senaite_id)

        # externalId slice: asset register number
        asset_number = self.instrument.getAssetNumber()
        if asset_number:
            identifiers.append({
                "use": "secondary",
                "value": api.safe_unicode(asset_number),
            })

        return identifiers

    def get_manufacturer(self):
        manufacturer = self.instrument.getManufacturer()
        if not manufacturer:
            return None
        return api.safe_unicode(api.get_title(manufacturer))

    def get_model(self):
        model = self.instrument.getModel()
        return api.safe_unicode(model) if model else None

    def get_serial_no(self):
        serial = self.instrument.getSerialNo()
        return api.safe_unicode(serial) if serial else None

    def get_narrative(self):
        """Returns Device.text — a generated human-readable narrative
        """
        title = api.safe_unicode(api.get_title(self.instrument))
        parts = []

        asset_number = self.instrument.getAssetNumber()
        if asset_number:
            parts.append(u"Asset: {}".format(api.safe_unicode(asset_number)))

        serial_no = self.instrument.getSerialNo()
        if serial_no:
            parts.append(
                u"Serial number: {}".format(api.safe_unicode(serial_no))
            )

        if parts:
            summary = u"Device of {} ({})".format(title, u", ".join(parts))
        else:
            summary = u"Device of {}".format(title)

        return {
            "status": "generated",
            "div": u'<div xmlns="http://www.w3.org/1999/xhtml">{}</div>'.format(summary)  # noqa: E501
        }

    def get_notes(self):
        """Returns Device.note entries.

        Each entry is only included when the field has a value.
        They are prefixed with their label so clients can identify them
        regardless of their position in the list.
        """
        notes = []

        description = api.safe_unicode(self.instrument.Description() or "")
        if description:
            notes.append({"text": u"Description: {}".format(description)})

        location = self.instrument.getInstrumentLocation()
        if location:
            location_title = api.safe_unicode(api.get_title(location))
            notes.append({"text": u"Location: {}".format(location_title)})

        instrument_type = self.instrument.getInstrumentType()
        if instrument_type:
            type_title = api.safe_unicode(api.get_title(instrument_type))
            notes.append({"text": u"Instrument Type: {}".format(type_title)})

        return notes
