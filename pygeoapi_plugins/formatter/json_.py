# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2026 Lincoln Institute of Land Policy
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================
"""JSON capabilities
Returns content as JSON without HTML-escaping the serialized output
"""

import logging

import orjson

from pygeoapi.formatter.base import (
    BaseFormatter,
    FormatterSerializationError,
)
from pygeoapi.util import json_serial


LOGGER = logging.getLogger(__name__)


class JSONFormatter(BaseFormatter):
    """JSON formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.json_.JSONFormatter`
        """

        geom = formatter_def.get('geom', False)

        super().__init__({'name': 'json', 'geom': geom})
        self.mimetype = 'application/geo+json'
        self.f = 'json'
        self.extension = 'json'

    def write(self, options: dict = {}, data: dict | None = {}) -> bytes:
        """
        Generate data in JSON format

        Unlike `pygeoapi.util.to_json`, `<` and `>` are left as-is
        rather than being cast to `&lt;` and `&gt;`.

        :param options: JSON formatting options
        :param data: dict of GeoJSON data

        :returns: bytes representation of format
        """

        if data is None:
            LOGGER.warning('No data to write to JSON')
            return bytes()

        option = orjson.OPT_INDENT_2 if options.get('pretty') else None

        if data.get('type') == 'Feature':
            data = _embed_geometry(data)
        elif 'features' in data:
            data = {
                **data,
                'features': [_embed_geometry(f) for f in data['features']],
            }

        try:
            return orjson.dumps(data, default=json_serial, option=option)
        except orjson.JSONEncodeError as err:
            LOGGER.error(err)
            raise FormatterSerializationError('Error writing JSON output')

    def __repr__(self):
        return f'<JSONFormatter> {self.name}'


def _embed_geometry(feature: dict) -> dict:
    """
    Embed a pre-serialized geometry (e.g. from ST_AsGeoJSON) verbatim,
    rather than encoding it as a quoted JSON string

    :param feature: `dict` of GeoJSON feature

    :returns: `dict` of GeoJSON feature
    """

    geometry = feature.get('geometry')
    if isinstance(geometry, (str, bytes)):
        return {**feature, 'geometry': orjson.Fragment(geometry)}

    return feature
