# -*- coding: utf-8 -*-

from senaite.jsonapi.exceptions import APIError


class FHIRAPIError(APIError):
    """Exception Class for FHIR's API Errors
    """

    def __init__(self, status, message):
        """Preserve the FHIR API's ``status, message`` argument order.

        The base ``APIError`` changed its constructor order, while FHIR's
        public ``fail`` helper continues to pass status first.
        """
        self.status = status
        self.message = message
        self.setStatus(status)
        Exception.__init__(self, message)


class ResourceValidationError(Exception):
    """Raised when an incoming FHIR resource violates validation rules

    :param message: human-readable description of the issue
    :param expression: FHIRPath expressions of the elements in error
    :param code: OperationOutcome issue type (e.g. `invalid`, `conflict`)
    :param status: HTTP status code, when it is not the one that matches the
        issue type (see `get_validation_outcome`)
    :param coding: list of Coding dicts for the issue's `details`
    """

    def __init__(self, message, expression=None, code="business-rule",
                 status=None, coding=None):
        super(ResourceValidationError, self).__init__(message)
        self.expression = expression or []
        self.code = code
        self.status = status
        self.coding = coding or []


class IdentifierValidationError(ResourceValidationError):
    """Raised when the identifiers of an incoming resource do not follow the
    identifiers pattern

    :param resource: the resource whose identifiers are invalid
    :param message: human-readable description of the issue
    """

    def __init__(self, resource, message):
        expression = ["{}.identifier".format(resource.resourceType)]
        super(IdentifierValidationError, self).__init__(
            message, expression=expression, code="invalid")


class LogicalIdValidationError(ResourceValidationError):
    """Raised when an entry of a POSTed bundle carries a `resource.id`, which
    is assigned by SENAITE only

    :param index: the position of the entry in the bundle
    """

    def __init__(self, index):
        message = (
            "Resource.id must not be supplied in a POST transaction entry. "
            "SENAITE generates all logical IDs; see "
            "identifiers.html#general-pattern.")
        expression = ["Bundle.entry[{}].resource.id".format(index)]
        coding = [{
            "system": "http://terminology.hl7.org/CodeSystem/"
                      "operation-outcome",
            "code": "MSG_LOCAL_FAIL",
        }]
        super(LogicalIdValidationError, self).__init__(
            message, expression=expression, code="invalid", status=422,
            coding=coding)


class ReferenceValidationError(ResourceValidationError):
    """Raised when a reference of an incoming resource cannot be resolved,
    either to an entry of the same bundle (`urn:uuid:<id>`) or to an existing
    resource in SENAITE (`{Resource}/{id}`)

    :param message: human-readable description of the issue
    :param expression: FHIRPath expression of the reference element
    """

    def __init__(self, message, expression):
        super(ReferenceValidationError, self).__init__(
            message, expression=[expression], code="invalid", status=422)


class ServiceRequestValidationError(ResourceValidationError):
    """Raised when a ServiceRequest violates validation rules
    """


class ObservationValidationError(ResourceValidationError):
    """Raised when an Observation violates validation rules
    """
