# -*- coding: utf-8 -*-

from bika.lims import api
from senaite.core.api import dtime
from senaite.core.schema.addressfield import OTHER_ADDRESS
from senaite.core.schema.addressfield import PHYSICAL_ADDRESS
from senaite.core.schema.addressfield import POSTAL_ADDRESS
from senaite.fhir import api as fapi
from senaite.fhir.converter import group_by
from senaite.fhir.converter import reject_internal_identifier
from senaite.fhir.converter import to_content_address
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_identifier as to_fhir_id
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.converter import to_naming_system_url
from senaite.fhir.converter import validate_external_identifier
from senaite.fhir.interfaces import IContentToFHIR
from senaite.fhir.interfaces import IFHIRToContent
from senaite.fhir.interfaces import IPatientResource
from senaite.fhir.resource.patient import PatientResource
from senaite.patient.config import GENDERS
from senaite.patient.config import SEXES
from senaite.patient.interfaces import IPatient
from zope.component import adapter
from zope.interface import implementer


# senaite.patient gender key -> FHIR R5 administrative-gender code
# https://hl7.org/fhir/R5/valueset-administrative-gender.html
#
# TODO Lossy mapping: FHIR administrative-gender has no distinction between
# transgender and diverse, so both "t" and "d" collapse to "other". A
# round-trip Patient("t") -> FHIR("other") -> Patient("d") loses the original
# value (see ResourceToPatient.get_gender below, which maps "other" back to
# "d"). Carrying the SENAITE-specific identity in a dedicated extension
# (e.g. patient-genderIdentity) would preserve it across conversions.
GENDER_TO_FHIR = {
    "m": "male",
    "f": "female",
    "t": "other",
    "d": "other",
    "": "unknown",
}

# SENAITE address type -> FHIR Address use/type
# FHIR use:  home | work | temp | old | billing
# FHIR type: postal | physical | both
ADDRESS_USE_TO_FHIR = {
    PHYSICAL_ADDRESS: "home",
    POSTAL_ADDRESS: "home",
    OTHER_ADDRESS: "temp",
}
ADDRESS_TYPE_TO_FHIR = {
    PHYSICAL_ADDRESS: "physical",
    POSTAL_ADDRESS: "postal",
    OTHER_ADDRESS: "both",
}

# FHIR ContactPoint use value set: home | work | temp | old | mobile
VALID_CONTACT_USES = frozenset(["home", "work", "temp", "old", "mobile"])


@adapter(IPatient)
@implementer(IContentToFHIR)
class PatientToResource(object):

    def __init__(self, patient):
        self.patient = patient

    def get_fhir_identifiers(self):
        # basic identifiers
        identifiers = [
            to_fhir_id("patient-id", self.patient.getId(), use="usual"),
            to_fhir_id(
                "patient-mrn", self.patient.getMRN(), use="secondary")
        ]
        # secondary identifiers
        for key, value in self.patient.get_identifier_items():
            sys_id = fapi.slugify(key)
            fhir_id = to_fhir_id(sys_id, value, use="secondary")
            identifiers.append(fhir_id)
        # remove empties
        return list(filter(None, identifiers))

    def get_fhir_addresses(self):
        """Returns a list of FHIR Address dicts built from the SENAITE patient
        address records, skipping any that carry no meaningful content.
        """
        addresses = []
        for record in self.patient.getAddress() or []:
            atype = record.get("type", "")
            street = record.get("address", "").strip()
            city = record.get("city", "").strip()
            zip_code = record.get("zip", "").strip()
            country = record.get("country", "").strip()
            state = record.get("subdivision1", "").strip()
            district = record.get("subdivision2", "").strip()

            if not any([street, city, zip_code, country, state, district]):
                continue

            fhir_addr = {}
            use = ADDRESS_USE_TO_FHIR.get(atype)
            if use:
                fhir_addr["use"] = use
            addr_type = ADDRESS_TYPE_TO_FHIR.get(atype)
            if addr_type:
                fhir_addr["type"] = addr_type
            if street:
                fhir_addr["line"] = [api.safe_unicode(street)]
            if city:
                fhir_addr["city"] = api.safe_unicode(city)
            if zip_code:
                fhir_addr["postalCode"] = api.safe_unicode(zip_code)
            if state:
                fhir_addr["state"] = api.safe_unicode(state)
            if district:
                fhir_addr["district"] = api.safe_unicode(district)
            if country:
                fhir_addr["country"] = api.safe_unicode(country)

            addresses.append(fhir_addr)
        return addresses

    def get_fhir_telecom(self):
        """Returns a list of FHIR ContactPoint dicts built from the SENAITE
        patient email and phone fields.
        """
        contacts = []

        # Primary email
        primary_email = self.patient.getEmail()
        if primary_email:
            contacts.append({
                "system": "email",
                "value": api.safe_unicode(primary_email),
                "use": "home",
            })

        # Additional emails
        for record in self.patient.getAdditionalEmails() or []:
            value = record.get("email", "").strip()
            if not value:
                continue
            name = record.get("name", "").strip().lower()
            use = name if name in VALID_CONTACT_USES else "work"
            contacts.append({
                "system": "email",
                "value": api.safe_unicode(value),
                "use": use,
            })

        # Primary phone
        primary_phone = self.patient.getPhone()
        if primary_phone:
            contacts.append({
                "system": "phone",
                "value": api.safe_unicode(primary_phone),
                "use": "home",
            })

        # Additional phone numbers
        for record in self.patient.getAdditionalPhoneNumbers() or []:
            value = record.get("phone", "").strip()
            if not value:
                continue
            name = record.get("name", "").strip().lower()
            use = name if name in VALID_CONTACT_USES else "work"
            contacts.append({
                "system": "phone",
                "value": api.safe_unicode(value),
                "use": use,
            })

        return contacts

    def to_fhir_resource(self):
        modified = api.get_modification_date(self.patient)
        modified = to_fhir_datetime(modified)

        profile_url = to_fhir_profile_url("Patient")
        data = {
            "resourceType": "Patient",
            "id": fapi.get_fhir_id(self.patient),
            "status": api.get_review_status(self.patient),
            "meta": {
                "profile": [profile_url],
                "lastUpdated": modified,
            },
            "identifier": self.get_fhir_identifiers(),
        }

        # FHIR Patient.name is an array of HumanName
        given = [self.patient.getFirstname(), self.patient.getMiddlename()]
        data["name"] = [{
            "family": self.patient.getLastname(),
            "given": list(filter(None, given)),
            "use": "official",
        }]

        # Date of birth
        dob = self.patient.getBirthdate()
        if dob:
            data["birthDate"] = dtime.date_to_string(dob)

        # Estimated birthdate carried as a FHIR extension
        if self.patient.getEstimatedBirthdate():
            data["extension"] = [{
                "url": to_fhir_profile_url("EstimatedDateBirth"),
                "valueBoolean": True,
            }]

        # Gender
        gender = self.patient.getGender() or ""
        data["gender"] = GENDER_TO_FHIR.get(gender, "unknown")

        # Deceased
        if self.patient.getDeceased():
            data["deceasedBoolean"] = True

        # Address
        addresses = self.get_fhir_addresses()
        if addresses:
            data["address"] = addresses

        # Telecom (phone + email)
        telecom = self.get_fhir_telecom()
        if telecom:
            data["telecom"] = telecom

        return PatientResource(data)


@adapter(IPatientResource)
@implementer(IFHIRToContent)
class ResourceToPatient(object):

    def __init__(self, resource):
        self.resource = resource

    def to_content_dict(self):
        reject_internal_identifier(self.resource, "Patient")
        validate_external_identifier(
            self.resource, "Patient", to_naming_system_url("patient-mrn"))

        # Medical Record Number
        mrn = self.get_mrn()
        if not mrn:
            # TODO check whether mrn is required in current instance
            raise ValueError("%r: No MRN" % self.resource)

        # Patient name
        firstname = self.get_firstname()
        middlename = self.get_middlename()
        lastname = self.get_lastname()
        if not any([firstname, lastname]):
            raise ValueError("%r: No valid name" % self.resource)

        # Sex and gender
        sex = self.get_sex()
        gender = self.get_gender()

        # Date of birth
        birthdate = self.get_birthdate()
        estimated = self.get_estimated_birthdate()

        # Address
        address = self.get_address()

        # Marital status
        marital = self.get_marital_status()

        # Email(s)
        primary_email = self.get_primary_email()
        additional_emails = self.get_additional_emails()

        # Phone(s)
        primary_phone = self.get_primary_phone()
        additional_phones = self.get_additional_phones()

        # Container path
        portal = api.get_portal()
        parent_path = "%s/patients" % api.get_path(portal)

        return {
            "portal_type": "Patient",
            "parent_path": parent_path,
            "mrn": api.safe_unicode(mrn),
            "sex": api.safe_unicode(sex),
            "gender": api.safe_unicode(gender),
            "birthdate": birthdate,
            "estimated_birthdate": estimated,
            "address": list(filter(None, [address])),
            "firstname": api.safe_unicode(firstname),
            "middlename": api.safe_unicode(middlename),
            "lastname": api.safe_unicode(lastname),
            "marital_status": api.safe_unicode(marital),
            "email": api.safe_unicode(primary_email),
            "additional_emails": additional_emails,
            "phone": api.safe_unicode(primary_phone),
            "additional_phone_numbers": additional_phones,
        }

    def get_mrn(self):
        """Returns the MRN from the resource
        """
        identifier = self.resource.get_identifier(use="secondary")
        return identifier.value if identifier else None

    def get_sex(self):
        """Returns the Sex from the resource, suitable for Patient content type
        """
        # supported genders: male | female | other | unknown
        # https://fhir.senaite.org/StructureDefinition-SenaitePatient-definitions.html#Patient.gender
        gender = self.resource.gender
        if not gender:
            return ""
        sexes = dict(SEXES).keys()
        key = gender[0].lower()
        if key in sexes:
            return key
        return ""

    def get_gender(self):
        # supported genders: male | female | other | unknown
        # https://fhir.senaite.org/StructureDefinition-SenaitePatient-definitions.html#Patient.gender
        gender = self.resource.gender
        if not gender:
            return ""
        # other --> diverse
        gender = "d" if gender == "other" else gender
        genders = dict(GENDERS).keys()
        key = gender[0].lower()
        if key in genders:
            return key
        return ""

    def get_human_name(self):
        """Returns a dict that represents the name of the Patient
        """
        human_name = self.resource.get_name(use="official")
        if human_name:
            return human_name

        # no official name, pick the first one
        human_name = self.resource.name
        return human_name[0] if human_name else None

    def get_firstname(self):
        name = self.get_human_name()
        given = name.given
        return given[0] if given else ""

    def get_middlename(self):
        name = self.get_human_name()
        given = name.given
        return given[1] if len(given) > 1 else ""

    def get_lastname(self):
        name = self.get_human_name()
        return name.family if name else ""

    def get_birthdate(self):
        return self.resource.birthDate

    def get_estimated_birthdate(self):
        """Returns whether the birthdate from the patient resource is
        considered estimated or not
        """
        return self.resource.estimatedDateBirth

    def get_address_element(self):
        """Returns the address of this patient, giving priority to home
        address first
        """
        priority = ["home", "work", "temp", "old"]
        address = None
        for use in priority:
            address = self.resource.get_address(use)
            if address:
                break
        return address

    def get_address(self):
        """Returns a content dict representation of the resource address
        """
        address = self.get_address_element()
        return to_content_address(address)

    def get_marital_status(self, default="UNK"):
        status = self.resource.maritalStatus
        status = status.coding if status else None
        status = status[0] if status else None
        if not status:
            return default

        code = status.code or ""
        display = status.display or ""
        if not any([code, display]):
            return default

        # get the marital statuses registered in the system
        reg_key = "senaite.patient.marital_statuses"
        supported = api.get_registry_record(reg_key)

        # find out if there is a match
        for status in supported:
            key = status.get("key")
            name = status.get("value")
            if code.lower() in [key.lower(), name.lower()]:
                return key
            if display.lower() in [key.lower(), name.lower()]:
                return key

        # return default
        return default

    def get_email_elements(self):
        # get all emails of this patient
        telecom = self.resource.telecom
        grouped = group_by(telecom, key="system")
        return grouped.get("email") or []

    def get_primary_email(self):
        """Returns the primary email address
        """
        emails = self.get_email_elements()
        grouped = group_by(emails, key="use")
        element = grouped.get("home")
        if not element:
            element = grouped.get("work")
        return element[0].value if element else None

    def get_additional_emails(self):
        emails = self.get_email_elements()
        grouped = group_by(emails, key="use")
        # mirror the primary-selection logic from get_primary_email so the
        # primary entry is not duplicated into the additional list
        if grouped.get("home"):
            primary_use = "home"
        elif grouped.get("work"):
            primary_use = "work"
        else:
            primary_use = None
        skipped = False
        result = []
        for email in emails:
            if not skipped and email.use == primary_use:
                skipped = True
                continue
            result.append({
                u"name": api.safe_unicode(email.use),
                u"email": api.safe_unicode(email.value),
            })
        return result

    def get_phone_elements(self):
        # get all phones of this patient
        telecom = self.resource.telecom
        grouped = group_by(telecom, key="system")
        return grouped.get("phone") or []

    def get_primary_phone(self):
        """Returns the primary phone number
        """
        phones = self.get_phone_elements()
        grouped = group_by(phones, key="use")
        element = grouped.get("home")
        if not element:
            element = grouped.get("work")
        return element[0].value if element else None

    def get_additional_phones(self):
        phones = self.get_phone_elements()
        grouped = group_by(phones, key="use")
        # mirror the primary-selection logic from get_primary_phone so the
        # primary entry is not duplicated into the additional list
        if grouped.get("home"):
            primary_use = "home"
        elif grouped.get("work"):
            primary_use = "work"
        else:
            primary_use = None
        skipped = False
        result = []
        for phone in phones:
            if not skipped and phone.use == primary_use:
                skipped = True
                continue
            result.append({
                u"name": api.safe_unicode(phone.use),
                u"phone": api.safe_unicode(phone.value),
            })
        return result
