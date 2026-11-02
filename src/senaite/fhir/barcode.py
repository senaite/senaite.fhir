# -*- coding: utf-8 -*-

from __future__ import absolute_import

import base64
from io import BytesIO
from time import time

from barcode import Code128
from barcode.writer import SVGWriter
from plone.memoize import ram
from senaite.fhir.config import SPECIMEN_BARCODE_EXTENSION_URL


BARCODE_CONTENT_TYPE = "image/svg+xml"
BARCODE_CACHE_TTL = 60 * 60 * 2
BARCODE_OPTIONS = {
    "module_height": 12,
    "quiet_zone": 2.54,
    "write_text": False,
}


def _get_barcode_cache_key(method, sample_id):
    """Cache each sample's SVG barcode in RAM for two hours
    """
    return int(time() // BARCODE_CACHE_TTL), sample_id


@ram.cache(_get_barcode_cache_key)
def get_barcode_svg(sample_id):
    """Return a Code 128 SVG for ``sample_id``
    """
    output = BytesIO()
    barcode = Code128(sample_id, writer=SVGWriter())
    barcode.write(output, options=BARCODE_OPTIONS)
    return output.getvalue()


def get_barcode_extension(sample_id):
    """Return the base64-encoded SVG barcode extension for ``sample_id``."""
    svg = get_barcode_svg(sample_id)
    return {
        "url": SPECIMEN_BARCODE_EXTENSION_URL,
        "valueAttachment": {
            "contentType": BARCODE_CONTENT_TYPE,
            "data": base64.b64encode(svg),
        },
    }
