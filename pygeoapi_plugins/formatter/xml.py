# =================================================================
#
# Author: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2023 Center for Geospatial Solutions
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

from datetime import datetime
import io
import logging
import xml.etree.ElementTree as ET

from pygeoapi.formatter.base import BaseFormatter, FormatterSerializationError

LOGGER = logging.getLogger(__name__)

URLSET = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>
"""
URLSET_FOREACH = """
<url>
    <loc>{}</loc>
    <lastmod>{}</lastmod>
</url>
"""


class XMLFormatter(BaseFormatter):
    """XML formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi.formatter.xml.XMLFormatter`
        """

        geom = False
        self.uri_field = formatter_def.get('uri_field')
        super().__init__({'name': 'xml', 'geom': geom})
        self.mimetype = 'application/xml; charset=utf-8'

    def write(self, options: dict = {}, data: dict = None) -> str:
        """
        Generate data in XML format

        :param options: XML formatting options
        :param data: dict of GeoJSON data

        :returns: string representation of format
        """

        try:
            feature = list(data['features'][0])
        except IndexError:
            LOGGER.error('no features')
            return str()

        lastmod = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        root = ET.fromstring(URLSET)
        tree = ET.ElementTree(root)
        try:
            ET.indent(tree)
        except AttributeError:
            LOGGER.warning('Unable to indent')

        try:
            for i, feature in enumerate(data['features']):
                if i >= 50000:
                    LOGGER.warning('Maximum size of sitemap reached')
                    break

                try:
                    loc = feature['properties'][self.uri_field]
                except KeyError:
                    loc = feature['@id']

                _ = URLSET_FOREACH.format(loc, lastmod)
                root.append(ET.fromstring(_))

        except ValueError as err:
            LOGGER.error(err)
            raise FormatterSerializationError('Error writing XML output')

        output = io.BytesIO()
        tree.write(output, encoding='utf-8', xml_declaration=True)
        return output.getvalue()

    def __repr__(self):
        return f'<XMLFormatter> {self.name}'
