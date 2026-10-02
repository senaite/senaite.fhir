# -*- coding: utf-8 -*-

import transaction

from bika.lims import api
from bika.lims.interfaces import IAnalysisRequest
from bika.lims.workflow import doActionFor as do_action_for
from senaite.core.api import dtime
from senaite.core.api import workflow as wapi
from senaite.fhir import api as fapi
from senaite.fhir import conditions
from senaite.fhir import logger
from senaite.fhir.api import find_object_for
from senaite.fhir.config import DEFAULT_BUNDLE_PAGE_COUNT
from senaite.fhir.config import INCLUDE_REFERENCE_FIELDS
from senaite.fhir.config import INSTRUMENT_SERVICE_REQUEST_STATUSES
from senaite.fhir.converter import to_fhir_datetime
from senaite.fhir.converter import to_fhir_profile_url
from senaite.fhir.finder.sampletype import SampleTypeFinder
from senaite.fhir.interfaces import IBundleResource
from senaite.fhir.r5 import add_route
from senaite.fhir.resource.bundleresponse import BundleResponseResource
from senaite.fhir.resource.operationoutcome import OperationOutcome
from senaite.fhir.resource.resultsbundle import ResultsBundleResource
from senaite.fhir.exceptions import ObservationValidationError
from senaite.fhir.exceptions import ServiceRequestValidationError
from senaite.fhir.resource.servicerequestrevoked import ServiceRequestRevocationError  # noqa: E501
from senaite.fhir.resource.servicerequestrevoked import ServiceRequestRevocationResource  # noqa: E501
from senaite.jsonapi import api as japi
from senaite.jsonapi import request as req
from six.moves.urllib_parse import urlencode

ENDPOINT = "senaite.fhir.r5"
ENDPOINT_GET = "%s.get" % ENDPOINT
ENDPOINT_POST = "%s.post" % ENDPOINT
ENDPOINT_REVOKE = "%s.revoke" % ENDPOINT

RESOURCE_TYPE_TO_CONTENT = (
    ("ServiceRequest", IAnalysisRequest),
)


# /<resource_type>
@add_route("/<string:resource_type>",
           ENDPOINT_GET, methods=["GET"])
@add_route("/<string:resource_type>/<string(length=32):uid>",
           ENDPOINT_GET, methods=["GET"])
@add_route("/<string(length=32):uid>",
           ENDPOINT_GET, methods=["GET"])
@add_route("/<string:resource_type>/<string(length=36):uid>",
           ENDPOINT_GET, methods=["GET"])
@add_route("/<string(length=36):uid>",
           ENDPOINT_GET, methods=["GET"])
def get(context, request, resource_type=None, uid=None):
    """GET
    """
    # maybe we received a request by uid/uuid
    uuids = list(filter(lambda val: fapi.is_uuid(val), [uid, resource_type]))
    if uuids:
        uid = fapi.get_uuid(uuids[0]).hex
        # pass the resource type so the annotation-stored snapshot of that
        # type is preferred (e.g. a Specimen, which has no counterpart content
        # type) before falling back to the IContentToFHIR adapter
        fhir_type = resource_type if not fapi.is_uuid(resource_type) else None
        resource = fapi.get_fhir_resource(
            uid, resource_type=fhir_type, default=None
        )
        if resource:
            return resource

        fapi.fail(msg="Not Found", status=404)

    # DiagnosticReport search (polling endpoint)
    if resource_type == "DiagnosticReport" and not uid:
        return get_diagnostic_report_bundle(context, request)

    # ServiceRequest search (polling endpoint)
    if resource_type == "ServiceRequest" and not uid:
        return get_service_request_bundle(context, request)

    # Device list (Instrument objects converted to FHIR Device)
    if resource_type == "Device" and not uid:
        return get_device_bundle(context, request)

    # Specimen listing: annotation-backed, no native SENAITE content type
    if resource_type == "Specimen" and not uid:
        return get_specimen_bundle(context, request)

    # all resources from the defined type
    portal_type = japi.resource_to_portal_type(resource_type)
    if portal_type is None:
        fapi.fail(msg="Not Found", status=404)

    # TODO Return a FHIR batch of resources?
    return japi.get_batched(portal_type=portal_type, uid=uid,
                            endpoint=ENDPOINT_GET)


@add_route("/<string:resource_type>", ENDPOINT_POST, methods=["POST"])
def post(context, request, resource_type=None):
    # disable CSRF
    req.disable_csrf_protection()

    # get the FHIR resources from the request
    resources = get_fhir_resources()

    entries = []
    for resource in resources:

        # Skip if creation or update of this resource is not supported
        if not fapi.can_create_or_update(resource):
            continue

        # create or update the counterpart object
        try:
            if_none_exist = conditions.get_if_none_exist(resource)
            if if_none_exist:
                # Conditional create: evaluate the ifNoneExist precondition
                # instead of the generic find-or-create flow below. A match
                # discards the submitted body entirely (no fapi.update) --
                # only the FHIR id used by this bundle is linked to it.
                obj = conditions.find_by_if_none_exist(resource, if_none_exist)  # noqa: E501
                if obj:
                    fapi.link_fhir_resource(obj, resource)
                    status = "200 OK"
                else:
                    obj = fapi.create(resource)
                    status = "201 Created"
            else:
                obj = find_object_for(resource)
                if not obj:
                    obj = fapi.create(resource)
                    status = "201 Created"
                else:
                    obj = fapi.update(obj, resource)
                    status = "200 OK"
        except (ServiceRequestValidationError, ObservationValidationError) as e:  # noqa: E501
            transaction.abort()
            code = getattr(e, "code", "business-rule")
            status_code = 400
            if code == "conflict":
                status_code = 409
            elif code == "multiple-matches":
                status_code = 412

            request.response.setStatus(status_code)
            issue = {
                "severity": "error",
                "code": code,
                "details": {"text": str(e)},
                "expression": e.expression,
            }
            return OperationOutcome({"issue": [issue]})
        except Exception:
            # Unexpected failure: roll back the whole bundle (all-or-none),
            # log the details server-side and return a generic error. Never
            # leak the internal exception text to the client.
            transaction.abort()
            logger.exception(
                "Bundle POST failed while processing %s/%s",
                resource.resourceType, resource.id)
            request.response.setStatus(500)
            issue = {
                "severity": "error",
                "code": "exception",
                "details": {
                    "text": "Internal error while processing the %s resource"
                            % resource.resourceType,
                },
                "expression": ["%s.id" % resource.resourceType],
            }
            return OperationOutcome({"issue": [issue]})

        # build the response entry
        fullUrl = "%s/%s" % (resource.resourceType, resource.id)
        modified = api.get_modification_date(obj) if obj else dtime.now()
        modified = dtime.to_iso_format(modified)

        # set up the basics of the response entry for this item
        entry = {
            "fullUrl": fullUrl,
            "response": {
                "status": status,
                "lastModified": modified,
            }
        }
        entries.append(entry)

        # If the resource is a ServiceRequest, process any Specimen resources
        if resource.resourceType == "ServiceRequest" and obj:
            specimen_entries = process_bundle_specimen(
                resource, obj, status, modified
            )
            entries.extend(specimen_entries)

        # An Observation carries a result for an existing Analysis; once
        # applied (see ResourceToAnalysisResult), submit it
        if resource.resourceType == "Observation" and obj:
            do_action_for(obj, "submit")
            obs = fapi.to_fhir_resource(obj, default=None)
            # Reference ranges are SENAITE-owned metadata. They are returned
            # to result consumers in the DiagnosticReport workflow, never in
            # the instrument/middleware result-submission exchange
            obs.pop("referenceRange", None)
            if resource.text:
                obs["text"] = resource.text
            return obs

    # create the BundleResponse
    resp = {
        "resourceType": "Bundle",
        "id": str(fapi.generate_UUID()),
        "meta": {
            "profile": [to_fhir_profile_url("SenaiteBundleResponse")]
        },
        "type": "transaction-response",
        "entry": entries,
    }
    return BundleResponseResource(resp)


def process_bundle_specimen(sr_resource, ar_obj, ar_status, ar_modified):
    """Store each Specimen referenced by a ServiceRequest into the AR's
    annotation storage and return bundle-response entries for them.

    Specimen has no independent SENAITE content type: it is persisted as
    annotation data on the AnalysisRequest so it can be fetched later via
    GET /Specimen/<uid> without callers needing to know SENAITE internals.
    The Specimen status mirrors the ServiceRequest/AR status per design.

    :param sr_resource: the ServiceRequest FHIR resource (carries ``_bundle``)
    :param ar_obj: the AnalysisRequest content object
    :param ar_status: HTTP status string used for the AR entry
    :param ar_modified: ISO-formatted last-modified timestamp of the AR
    :returns: list of bundle-response entry dicts, one per specimen
    """
    bundle = sr_resource.get("_bundle")
    if not bundle or not sr_resource.specimen:
        return []

    entries = []
    for spec_ref in sr_resource.specimen:
        specimen = bundle.first_entry("id", str(spec_ref.UUID()))
        if not specimen:
            continue

        # Persist the Specimen dict in the AR's annotation storage and index
        # its UID in the FHIR catalog so search_by_fhir_uid can find the AR.
        fapi.link_fhir_resource(ar_obj, specimen, secondary=True)

        sample_type = SampleTypeFinder(specimen).find()
        if sample_type and ar_obj.getSampleType() != sample_type:
            ar_obj.setSampleType(sample_type)
            ar_obj.reindexObject()

        # The IG requires the Specimen entry, and only it, to carry the full
        # server-populated resource: that is how the consumer learns the
        # internal Sample ID. Fail rather than return an entry without it
        rendered_specimen = fapi.get_fhir_resource(
            ar_obj, resource_type="Specimen")
        entries.append({
            "fullUrl": "Specimen/{}".format(specimen.id),
            "resource": dict(rendered_specimen),
            "response": {
                "status": ar_status,
                "lastModified": ar_modified,
            },
        })

    return entries


@add_route("/<string:resource_type>/<string(length=32):uid>/$revoke",
           ENDPOINT_REVOKE, methods=["POST"])
@add_route("/<string:resource_type>/<string(length=36):uid>/$revoke",
           ENDPOINT_REVOKE, methods=["POST"])
def revoke(context, request, resource_type, uid):
    # disable CSRF
    req.disable_csrf_protection()

    # ensure there is a counterpart object registered for the given uid
    uid = fapi.get_uuid(uid).hex
    obj = api.get_object_by_uid(uid, default=None)
    if not obj:
        fapi.fail("Object not found", status=404)

    # ensure the object found is from the expected type
    implementer = dict(RESOURCE_TYPE_TO_CONTENT).get(resource_type)
    if not implementer:
        fapi.fail("Resource type '%s' is not supported" % resource_type)
    if not implementer.providedBy(obj):
        fapi.fail("Unexpected content type: %s" % api.get_portal_type(obj),
                  status=406)

    # get the FHIR resource that represents the revocation
    resources = get_fhir_resources()
    if not resources:
        fapi.fail("No revocation resource found for '%s'" % resource_type)
    if len(resources) > 1:
        fapi.fail("Revoke with multiple entries is not supported")

    resource = resources[0]
    if not isinstance(resource, ServiceRequestRevocationResource):
        fapi.fail("Not a ServiceRevocationResource")

    # get the reason(s) for rejection/cancellation
    reject_reason = resource.rejection_reason
    reject_allowed = wapi.is_transition_allowed(obj, "reject")
    cancel_allowed = wapi.is_transition_allowed(obj, "cancel")

    if not any([reject_allowed, cancel_allowed]):
        # return a ServiceRequestRevocationError
        request.response.setStatus(403)
        issue = {
            "severity": "error",
            "code": "forbidden",
            "details": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/operation-outcome",  # noqa: E501
                    "code": "MSG_LOCAL_FAIL",
                }],
                "text": "Revoke is not allowed for this resource",
            },
            "expression": ["%s.status" % resource_type],
        }
        return ServiceRequestRevocationError({"issue": [issue]})

    if reject_allowed and not cancel_allowed:
        transition = "reject"
    elif cancel_allowed and not reject_allowed:
        transition = "cancel"
    else:
        # TODO: This is ambiguous when both/neither transitions are allowed;
        # confirm the intended behavior with product/functional owners
        transition = "reject" if reject_reason else "cancel"

    if reject_reason:
        obj.setRejectionReasons(reject_reason)

    success, message = do_action_for(obj, transition)
    if not success:
        # prevent partial commits (e.g. reason was set before transition)
        transaction.abort()
        # return a ServiceRequestRevocationError
        request.response.setStatus(403)
        issue = {
            "severity": "error",
            "code": "forbidden",
            "details": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/operation-outcome",  # noqa: E501
                    "code": "MSG_LOCAL_FAIL",
                }],
                "text": message,
            },
            "expression": ["%s.status" % resource_type],
        }
        return ServiceRequestRevocationError({"issue": [issue]})

    resource = fapi.to_fhir_action_resource(obj, "revoke")
    return resource


def get_specimen_bundle(context, request):
    """Return all Specimens as a FHIR searchset bundle.

    Specimens have no independent SENAITE content type. For ARs created via
    the FHIR bundle API the Specimen is stored as annotation data and returned
    as-is. For ARs created natively in SENAITE (no annotation) a Specimen is
    synthesized on-the-fly from the AR's SampleType and DateSampled so that
    FHIR clients never need to know about SENAITE internals.

    Supports optional ``_lastUpdated`` (e.g. ``gt2026-01-01T00:00:00Z``) to
    filter by the underlying AR's modification date.
    """
    params = request.form
    since = parse_last_updated(params.get("_lastUpdated", ""))
    if isinstance(since, OperationOutcome):
        return since

    query = {"portal_type": "AnalysisRequest"}
    if since:
        query["modified"] = {"query": since, "range": "min"}
    brains = api.search(query)

    entries = []
    for brain in brains:
        ar = api.get_object(brain, default=None)
        if not ar:
            continue
        specimen = fapi.get_fhir_resource(
            ar, resource_type="Specimen", default=None
        )
        if not specimen:
            continue
        entries.append({
            "fullUrl": "Specimen/{}".format(specimen.id),
            "resource": dict(specimen),
            "search": {"mode": "match"},
        })

    bundle_data = {
        "resourceType": "Bundle",
        "id": str(fapi.generate_UUID()),
        "type": "searchset",
        "total": len(entries),
    }
    if entries:
        bundle_data["entry"] = entries

    return ResultsBundleResource(bundle_data)


def get_diagnostic_report_bundle(_context, request):
    """Handle GET /DiagnosticReport with _lastUpdated, _summary, _include.

    Builds a SenaiteResultsBundle (searchset) containing:
      - DiagnosticReport entries with search.mode = "match"
      - Observation entries with search.mode = "include" when
        _include=Observation:result is requested, appended after the
        matches
    """
    params = request.form

    since = parse_last_updated(params.get("_lastUpdated", ""))
    if isinstance(since, OperationOutcome):
        return since
    summary = params.get("_summary", "").lower()

    if summary != "true":
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "required",
            "details": {
                "text": "_summary=true is required for this endpoint",
            },
            "diagnostics": "This endpoint only supports requests with _summary=true. Include _summary=true as a query parameter.",  # noqa: E501
            "expression": ["_summary"],
        }
        return OperationOutcome({"issue": [issue]})

    include_specs = parse_include_params(params, "DiagnosticReport")
    if isinstance(include_specs, OperationOutcome):
        return include_specs

    query = {"portal_type": "AnalysisRequest"}
    if since:
        query["modified"] = {"query": since, "range": "min"}
    brains = api.search(query)

    entries = []
    total_match = 0

    for brain in brains:
        sample = api.get_object(brain, default=None)
        if not sample:
            continue
        reports = sample.getReports()
        if not reports:
            continue

        # Get the most recent report for this sample
        last_report = reports[-1]
        dr = fapi.to_fhir_resource(last_report, default=None)
        if not dr:
            continue

        total_match += 1

        dr_dict = dict(dr)
        strip_presented_form_data(dr_dict)

        entries.append({
            "fullUrl": "DiagnosticReport/{}".format(dr.id),
            "resource": dr_dict,
            "search": {"mode": "match"},
        })

    if include_specs:
        # Resolve references only from the resources already matched
        match_resources = [entry["resource"] for entry in entries]
        entries.extend(
            resolve_included_resources(
                match_resources, include_specs, "DiagnosticReport")
        )

    now = dtime.to_localized_time(dtime.now(), long_format=True)
    bundle_data = {
        "resourceType": "Bundle",
        "id": str(fapi.generate_UUID()),
        "meta": {
            "profile": [to_fhir_profile_url("SenaiteResultsBundle")],
        },
        "type": "searchset",
        "timestamp": now,
        "total": total_match,
    }

    if entries:
        bundle_data["entry"] = entries

    return ResultsBundleResource(bundle_data)


def get_service_request_bundle(_context, request):
    """Handle GET /ServiceRequest with _lastUpdated, intent, status,
    optional _sort, _count, _offset and _include (polling endpoint).

    Builds a SenaiteResultsBundle (searchset) containing the
    instrument-scoped SenaiteInstrumentServiceRequest entries (intent
    "filler-order") derived from Analyses, i.e. the ones created by
    ``AnalysisToInstrumentServiceRequest``.

    ``_include=Patient:subject`` and ``_include=Specimen:specimen`` include
    each page's referenced Patients and Specimens, respectively.
    """
    params = request.form

    since = parse_last_updated(params.get("_lastUpdated", ""))
    if isinstance(since, OperationOutcome):
        return since

    intent = params.get("intent", "")
    if intent != "filler-order":
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "required",
            "details": {
                "text": "intent=filler-order is required for this endpoint",
            },
            "diagnostics": "This endpoint only supports requests with intent=filler-order. Include intent=filler-order as a query parameter.",  # noqa: E501
            "expression": ["intent"],
        }
        return OperationOutcome({"issue": [issue]})

    status = params.get("status", "")
    if status != "active":
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "required",
            "details": {
                "text": "status=active is required for this endpoint",
            },
            "diagnostics": "This endpoint only supports requests with status=active. Include status=active as a query parameter.",  # noqa: E501
            "expression": ["status"],
        }
        return OperationOutcome({"issue": [issue]})

    sort = params.get("_sort", "")
    if sort and sort != "lastUpdated":
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "invalid",
            "details": {
                "text": "Only _sort=lastUpdated is supported",
            },
            "diagnostics": "This endpoint always returns results in a stable lastUpdated-descending order. When _sort is provided it must be set to lastUpdated.",  # noqa: E501
            "expression": ["_sort"],
        }
        return OperationOutcome({"issue": [issue]})

    pagination = parse_pagination_params(params)
    if isinstance(pagination, OperationOutcome):
        return pagination
    count, offset = pagination

    include_specs = parse_include_params(params, "ServiceRequest")
    if isinstance(include_specs, OperationOutcome):
        return include_specs

    # review_states of Analysis objects that map to the "active" FHIR status
    active_statuses = [
        review_state
        for review_state, fhir_status in INSTRUMENT_SERVICE_REQUEST_STATUSES
        if review_state and fhir_status == "active"
    ]

    query = {
        "portal_type": "Analysis",
        "review_state": active_statuses,
    }
    brains = api.search(query)

    matches = []

    for brain in brains:
        analysis = api.get_object(brain, default=None)
        if not analysis:
            continue

        if since and api.get_modification_date(analysis) < since:
            continue

        sr = fapi.to_fhir_resource(
            analysis, resource_type="ServiceRequest", default=None)
        if not sr:
            # never linked (no Instrument was ever assigned)
            continue

        matches.append((dtime.to_dt(sr["authoredOn"]), sr))

    # sort descending by authoredOn
    matches.sort(key=lambda match: match[0], reverse=True)

    total_match = len(matches)
    page = matches[offset:offset + count] if count > 0 else []

    entries = [{
        "fullUrl": "ServiceRequest/{}".format(service_request.id),
        "resource": dict(service_request),
        "search": {"mode": "match"},
    } for _, service_request in page]

    if include_specs:
        # Resolve references only from the resources already on this page
        page_resources = [entry["resource"] for entry in entries]
        entries.extend(
            resolve_included_resources(
                page_resources, include_specs, "ServiceRequest")
        )

    now = to_fhir_datetime(dtime.now())
    bundle_data = {
        "resourceType": "Bundle",
        "id": str(fapi.generate_UUID()),
        "type": "searchset",
        "timestamp": now,
        "total": total_match,
        "link": build_page_links(request, offset, count, total_match),
    }

    if entries:
        bundle_data["entry"] = entries

    return ResultsBundleResource(bundle_data)


def build_page_links(request, offset, count, total):
    """Build the Bundle.link "self"/"next"/"previous" entries for a paged
    searchset, preserving the request's own query parameters.
    """
    links = [build_page_link(request, "self", offset, count)]

    if count > 0 and offset + count < total:
        links.append(build_page_link(request, "next", offset + count, count))

    if offset > 0:
        previous_offset = max(offset - count, 0) if count > 0 else 0
        links.append(
            build_page_link(request, "previous", previous_offset, count))

    return links


def build_page_link(request, relation, offset, count):
    """Build a single Bundle.link entry for the given _offset/_count page
    """
    params = dict(request.form)
    params["_count"] = count
    params["_offset"] = offset
    return {
        "relation": relation,
        "url": "%s?%s" % (request.URL, urlencode(params, doseq=True)),
    }


def parse_last_updated(value):
    """Parse a FHIR _lastUpdated value into a catalog min-range boundary
    """
    if not value:
        return None

    if value.startswith("gt"):
        value = value[2:]

    since = dtime.to_DT(value)
    if not since:
        request = req.get_request()
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "invalid",
            "details": {
                "text": "Malformed _lastUpdated value",
            },
            "diagnostics": "_lastUpdated must be a valid FHIR instant, for example gt2026-05-28T00:00:00Z.",  # noqa: E501
            "expression": ["_lastUpdated"],
        }
        return OperationOutcome({"issue": [issue]})

    return since


def parse_pagination_params(params):
    """Parse and validate the ``_count``/``_offset`` paging parameters
    """
    raw_count = params.get("_count", "")
    raw_offset = params.get("_offset", "")

    count = int(raw_count) if raw_count else DEFAULT_BUNDLE_PAGE_COUNT
    offset = int(raw_offset) if raw_offset else 0

    if count < 0 or offset < 0:
        request = req.get_request()
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "invalid",
            "details": {
                "text": "Malformed _count/_offset value",
            },
            "diagnostics": "_count and _offset must be non-negative integers.",  # noqa: E501
            "expression": ["_count", "_offset"],
        }
        return OperationOutcome({"issue": [issue]})

    return count, offset


def get_include_reference_fields(resource_type):
    """Returns the ``_include`` specs supported by the endpoint that matches
    on the given resource type, mapped to the reference field each one
    resolves.

    :param resource_type: FHIR resource type the endpoint matches on
    :returns: dict of {`_include` spec: reference field}
    """
    fields = dict(INCLUDE_REFERENCE_FIELDS).get(resource_type) or {}
    # return a copy, so the constant cannot be modified by the caller
    return dict(fields)


def parse_include_params(params, resource_type):
    """Parse and validate the ``_include`` query parameter.

    Accepts a single value, a comma-separated list of values, or multiple
    ``_include`` query parameters. Each value must be one of the specs the
    endpoint supports; any other value results in a 400 OperationOutcome.

    :param params: request.form-like mapping
    :param resource_type: FHIR resource type the endpoint matches on
    :returns: list of requested include specs (str), or an OperationOutcome
    """
    supported = get_include_reference_fields(resource_type)
    raw = params.get("_include", [])
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    specs = [spec for value in values for spec in value.split(",") if spec]

    unsupported = [spec for spec in specs if spec not in supported]
    if unsupported:
        request = req.get_request()
        request.response.setStatus(400)
        issue = {
            "severity": "error",
            "code": "not-supported",
            "details": {
                "text": "Unsupported _include value(s): %s" % ", ".join(unsupported),  # noqa: E501
            },
            "diagnostics": "Supported _include values for this endpoint: %s" % ", ".join(sorted(supported)),  # noqa: E501
            "expression": ["_include"],
        }
        return OperationOutcome({"issue": [issue]})

    return specs


def resolve_included_resources(resources, include_specs, resource_type):
    """Return include-mode Bundle entries referenced by ``resources``.

    :param resources: FHIR resources to scan
    :param include_specs: `_include` specs to resolve
    :param resource_type: FHIR resource type the endpoint matches on
    :returns: Bundle entries with ``search.mode = "include"``
    """
    entries = []
    included_refs = set()
    reference_fields = get_include_reference_fields(resource_type)

    for spec in include_specs:
        field = reference_fields.get(spec)
        if not field:
            continue
        target_type = spec.split(":", 1)[0]

        for resource in resources:
            value = resource.get(field)
            candidates = value if isinstance(value, list) else [value]

            for candidate in candidates:
                reference = (candidate or {}).get("reference")
                if not reference or "/" not in reference:
                    continue

                ref_type, ref_uid = reference.split("/", 1)
                if ref_type != target_type or not fapi.is_uuid(ref_uid):
                    continue

                # normalize to hex so the SENAITE-UID fast path in
                # to_fhir_resource/get_object is used, rather than relying
                # on the referenced object being indexed in the FHIR catalog
                ref_uid = fapi.get_uuid(ref_uid).hex
                if (target_type, ref_uid) in included_refs:
                    continue
                included_refs.add((target_type, ref_uid))

                included = fapi.to_fhir_resource(
                    ref_uid, resource_type=target_type, default=None
                )

                if not included:
                    continue

                entries.append({
                    "fullUrl": "{}/{}".format(target_type, included.id),
                    "resource": dict(included),
                    "search": {"mode": "include"},
                })

    return entries


def strip_presented_form_data(dr_dict):
    """Remove the base64 PDF payload from presentedForm
    """
    for attachment in dr_dict.get("presentedForm") or []:
        attachment.pop("data", None)


def get_device_bundle(_context, request):
    """Handle GET /Device with optional ?_lastUpdated=gt<datetime> filter.

    Returns a FHIR searchset Bundle containing SENAITE Instruments
    converted to Device resources. When _lastUpdated is provided only
    instruments modified after that instant are included.
    """
    params = request.form

    since = parse_last_updated(params.get("_lastUpdated", ""))
    if isinstance(since, OperationOutcome):
        return since

    brains = api.search({"portal_type": "Instrument"})

    entries = []
    for brain in brains:
        instrument = api.get_object(brain, default=None)
        if not instrument:
            continue
        if since:
            modified = dtime.to_DT(api.get_modification_date(instrument))
            if not modified or modified <= since:
                continue
        device = fapi.to_fhir_resource(instrument, default=None)
        if not device:
            continue
        entries.append({
            "fullUrl": "Device/{}".format(device.id),
            "resource": dict(device),
            "search": {"mode": "match"},
        })

    now = dtime.to_localized_time(dtime.now(), long_format=True)
    bundle_data = {
        "resourceType": "Bundle",
        "id": str(fapi.generate_UUID()),
        "type": "searchset",
        "timestamp": now,
        "total": len(entries),
    }
    if entries:
        bundle_data["entry"] = entries
    return ResultsBundleResource(bundle_data)


def get_fhir_resources():
    """Returns the resources from the request
    """
    resources = []

    # get the FHIR raw records
    records = req.get_request_data()
    for record in records:
        # convert to a FHIR resource
        resource = fapi.to_fhir_resource(record)

        # if the resource is a Bundle, extract all contained resources
        if IBundleResource.providedBy(resource):
            for entry in resource.entry:
                # convert each entry to a FHIR resource
                entry_res = fapi.to_fhir_resource(entry)
                if not entry_res:
                    continue
                # add to the resources list
                resources.append(entry_res)

        # append the resource
        resources.append(resource)

    return resources
