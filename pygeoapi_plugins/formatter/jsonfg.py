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
    get_transform_from_crs,
    get_crs,
)
from pygeoapi.formatter.base import BaseFormatter
from pygeoapi.util import to_json, url_join


LOGGER = logging.getLogger(__name__)


class JSONFGFormatter(BaseFormatter):
    """JSON-FG formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.jsonfg.JSONFGFormatter`
        """

        geom = False
        if 'geom' in formatter_def:
            geom = formatter_def['geom']

        super().__init__({'name': 'JSONFG', 'geom': geom})
        self.mimetype = 'application/geo+json'
        self.f = 'jsonfg'
        self.extension = 'json'

    def write(self, options: dict = {}, data: dict | None = {}) -> str:
        """
        Generate data in JSON-FG format

        :param options: JSON-FG formatting options
        :param data: dict of GeoJSON data

        :returns: string representation of format
        """

        format_conditions = [
            data is None,
            isinstance(data, dict) and not data.get('features'),
        ]
        if any(format_conditions):
            LOGGER.warning('No features to write to JSON-FG')
            return str()

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

        # The following code is an alternative implementation that uses GDAL
        # to convert GeoJSON to JSON-FG. It is currently commented out because
        # the direct manipulation of the GeoJSON structure is more
        # straightforward and does not require GDAL as a dependency. However,
        # if there are issues with the direct approach or if there is a need
        # for more complex transformations, the GDAL-based implementation can
        # be considered.
        #
        # try:
        #     links = data.get('links')
        #     output = geojson2jsonfg(data=data)
        #     output['links'] = links
        #     return to_json(output)
        # except ValueError as err:
        #     LOGGER.error(err)
        #     raise FormatterSerializationError('Error writing JSONFG output')

        return to_json(jsonfg)

    def __repr__(self):
        return f'<JSONFGFormatter> {self.name}'


# def geojson2jsonfg(data: dict) -> dict:
#     """
#     Return JSON-FG from a GeoJSON content.

#     :param data: dict of data

#     :returns: dict of converted GeoJSON (JSON-FG)
#     """
#     gdal.UseExceptions()
#     LOGGER.debug('Dump GeoJSON content into a data source')
#     try:
#         with gdal.OpenEx(json.dumps(data)) as srcDS:
#             tmpfile = f'/vsimem/{uuid.uuid1()}.json'
#             LOGGER.debug('Translate GeoJSON into a JSONFG memory file')
#             gdal.VectorTranslate(tmpfile, srcDS, format='JSONFG')
#             LOGGER.debug('Read JSONFG content from a memory file')
#             data = gdal.VSIFOpenL(tmpfile, 'rb')
#             if not data:
#                 raise ValueError('Failed to read JSONFG content')
#             gdal.VSIFSeekL(data, 0, 2)
#             length = gdal.VSIFTellL(data)
#             gdal.VSIFSeekL(data, 0, 0)
#             jsonfg = json.loads(gdal.VSIFReadL(1, length, data).decode())
#             return jsonfg
#     except Exception as e:
#         LOGGER.error(f'Failed to convert GeoJSON to JSON-FG: {e}')
#         raise
#     finally:
#         gdal.VSIFCloseL(data)
