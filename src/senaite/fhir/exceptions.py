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
    """

    def __init__(self, message, expression=None, code="business-rule"):
        super(ResourceValidationError, self).__init__(message)
        self.expression = expression or []
        self.code = code


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


class ServiceRequestValidationError(ResourceValidationError):
    """Raised when a ServiceRequest violates validation rules
    """


class ObservationValidationError(ResourceValidationError):
    """Raised when an Observation violates validation rules
    """
