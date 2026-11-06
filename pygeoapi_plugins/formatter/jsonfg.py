# =================================================================
#
# Authors: Francesco Bartoli <xbartolone@gmail.com>
#          Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2025 Francesco Bartoli
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
"""JSON-FG capabilities
Returns content as JSON-FG representations
"""

import logging

# import osgeo if using geojson2jsonfg
# from osgeo import gdal
from pygeoapi.crs import (
    DEFAULT_CRS,
    crs_transform_feature,
    get_crs,
    get_transform_from_crs,
)
from pygeoapi.util import url_join

from pygeoapi_plugins.formatter.json_ import JSONFormatter

LOGGER = logging.getLogger(__name__)


class JSONFGFormatter(JSONFormatter):
    """JSON-FG formatter, written as `JSONFormatter` writes JSON"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.jsonfg.JSONFGFormatter`
        """

        super().__init__(formatter_def)
        self.name = 'jsonfg'
        self.f = 'jsonfg'

    def write(
        self, options: dict | None = None, data: dict | None = None
    ) -> bytes:
        """
        Generate data in JSON-FG format

        :param options: JSON-FG formatting options
        :param data: dict of GeoJSON data

        :returns: bytes representation of format
        """

        options = options or {}
        format_conditions = [
            data is None,
            isinstance(data, dict) and not data.get('features'),
        ]
        if any(format_conditions):
            LOGGER.warning('No features to write to JSON-FG')
            return b''

        provider_def = options.get('provider_def', {})
        time_field = provider_def.get('time_field')
        content_crs = options.get('content_crs') or DEFAULT_CRS
        crs_in = get_crs(content_crs)
        crs_out = get_crs(DEFAULT_CRS)
        transform_func = get_transform_from_crs(
            crs_in, crs_out, always_xy=True
        )

        jsonfg = {
            'type': 'FeatureCollection',
            'featureType': 'OGRGeoJSON',
            'featureSchema': None,
            'coordRefSys': content_crs,
            'conformsTo': [
                'http://www.opengis.net/spec/json-fg-1/1.0/conf/core',
                'http://www.opengis.net/spec/json-fg-1/1.0/conf/types-schemas',
            ],
            'features': [],
            'links': data.get('links', []),
        }

        try:
            [collection_url] = [
                link['href']
                for link in data.get('links', [])
                if link.get('rel') == 'collection'
            ]
            jsonfg['featureSchema'] = url_join(collection_url, 'jsonfg/schema')
        except ValueError:
            LOGGER.warning('No collection link found in data')
            jsonfg.pop('featureSchema')

        for feature in data.get('features', []):
            if time_field:
                feature['time'] = feature['properties'].pop(time_field)

            if content_crs != DEFAULT_CRS:
                feature['place'] = feature.get('geometry', None)
                crs_transform_feature(feature, transform_func)

            jsonfg['features'].append(feature)

        return super().write(options, jsonfg)

    def __repr__(self):
        return f'<JSONFGFormatter> {self.name}'
