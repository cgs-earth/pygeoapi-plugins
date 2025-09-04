# =================================================================
#
# Author: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2025 Center for Geospatial Solutions
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

import io
import math
import os
import logging
import zipfile

from pygeoapi.config import get_config
from pygeoapi.plugin import load_plugin
from pygeoapi.process.base import BaseProcessor
from pygeoapi.openapi import get_oas
from pygeoapi.util import (
    url_join,
    filter_dict_by_key_value,
    get_provider_by_type,
)

from pygeoapi_plugins.formatter.xml import XMLFormatter


LOGGER = logging.getLogger(__name__)

CONFIG = get_config()
COLLECTIONS = filter_dict_by_key_value(CONFIG['resources'], 'type', 'collection')

PROCESS_DEF = CONFIG['resources']['sitemap-generator']
PROCESS_DEF.update(
    {
        'version': '0.2.0',
        'id': 'sitemap-generator',
        'title': 'Sitemap Generator',
        'description': ('A process that returns a sitemap ofall pygeoapi endpoints.'),
        'links': [
            {
                'type': 'text/html',
                'rel': 'about',
                'title': 'information',
                'href': 'https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview',  # noqa
                'hreflang': 'en-US',
            }
        ],
        'inputs': {
            'include-common': {
                'title': {'en': 'Include OGC API - Common'},
                'description': {
                    'en': 'Boolean value controlling the generation of a sitemap '
                    'for OGC API - Common endpoints'
                },
                'keywords': {'en': ['sitemap', 'ogc', 'OGC API - Common', 'pygeoapi']},
                'schema': {'type': 'boolean', 'default': True},
                'minOccurs': 0,
                'maxOccurs': 1,
                'metadata': None,  # TODO how to use?
            },
            'include-features': {
                'title': {'en': 'Include OGC API - Features'},
                'description': {
                    'en': 'Boolean value controlling the generation of a sitemap '
                    'for individual OGC API - Features endpoints'
                },
                'keywords': {
                    'en': ['sitemap', 'ogc', 'OGC API - Features', 'pygeoapi']
                },
                'schema': {'type': 'boolean', 'default': True},
                'minOccurs': 0,
                'maxOccurs': 1,
                'metadata': None,  # TODO how to use?
            },
            'zip': {
                'title': {'en': 'ZIP response'},
                'description': {'en': 'Boolean whether to ZIP the response'},
                'keywords': {'en': ['sitemap', 'zip', 'pygeoapi']},
                'schema': {'type': 'boolean', 'default': False},
                'minOccurs': 0,
                'maxOccurs': 1,
                'metadata': None,  # TODO how to use?
            },
        },
        'outputs': {
            'common.xml': {
                'title': {'en': 'OGC API - Common Sitemap'},
                'description': {
                    'en': 'A sitemap of the OGC API - Common end points for the '
                    'pygeoapi instance.'
                },
                'schema': {'type': 'object', 'contentMediaType': 'application/json'},
            },
            'sitemap.zip': {
                'title': {'en': 'Sitemap'},
                'description': {'en': 'A sitemap of the pygeoapi instance'},
                'schema': {'type': 'object', 'contentMediaType': 'application/zip'},
            },
        },
        'example': {'inputs': {'include-features': False}},
    }
)


class SitemapProcessor(BaseProcessor):
    """Sitemap Processor"""

    def __init__(self, processor_def):
        """
        Initialize object

        :param processor_def: provider definition

        :returns: pygeoapi.process.sitemap.SitemapProcessor
        """
        LOGGER.debug('SitemapProcesser init')
        super().__init__(processor_def, PROCESS_DEF)
        self.config = CONFIG
        self.base_url = self.config['server']['url']
        self.xml = XMLFormatter({})

    def execute(self, data, outputs=None):
        """
        Execute Sitemap Process

        :param data: processor arguments
        :param outputs: processor outputs

        :returns: 'application/json'
        """
        mimetype = 'application/json'
        common = data.get('include-common', True)
        features = data.get('include-features', True)
        if data.get('zip'):
            LOGGER.debug('Returning zipped response')
            zip_output = io.BytesIO()
            with zipfile.ZipFile(zip_output, 'w') as zipf:
                for filename, content in self.generate(common, features):
                    zipf.writestr(filename, content)
            return 'application/zip', zip_output.getvalue()

        else:
            LOGGER.debug('Returning response')
            return mimetype, dict(self.generate(common, features))

    def generate(self, include_common, include_features):
        """
        Execute Sitemap Process

        :param include_common: Include OGC API - Common endpoints
        :param include_features: Include OGC API - Features endpoints

        :returns: 'application/json'
        """
        if include_common:
            LOGGER.debug('Generating common.xml')
            oas = {'features': []}
            for path in get_oas(self.config).get('paths', []):
                if r'{jobId}' not in path and r'{featureId}' not in path:
                    path_uri = url_join(self.base_url, path)
                    oas['features'].append({'@id': path_uri})
            yield ('common.xml', self.xml.write(data=oas))

        if include_features:
            LOGGER.debug('Generating collections sitemap')
            for name, c in COLLECTIONS.items():
                LOGGER.debug(f'Generating sitemap(s) for {name}')
                p = get_provider_by_type(c['providers'], 'feature')
                provider = load_plugin('provider', p)
                hits = provider.query(resulttype='hits').get('numberMatched')
                iterations = range(math.ceil(hits / 50000))
                for i in iterations:
                    yield (f'{name}__{i}.xml', self._generate(i, name, provider))

    def _generate(self, index, dataset, provider, n=50000):
        """
        Private Function: Generate sitemap

        :param index: feature list index
        :param dataset: OGC API Provider name
        :param provider: OGC API Provider definition
        :param n: Number per index

        :returns: List of GeoJSON Features
        """

        content = provider.query(offset=(n * index), limit=n, skip_geometry=True)
        content['links'] = []
        content = self.geojson2linkedlist(
            content, dataset, id_field=(provider.uri_field or 'id')
        )
        return self.xml.write(data=content)

    def get_collections_url(self, *args):
        return url_join(self.base_url, 'collections', *args)
    
    def geojson2linkedlist(self, content, dataset, id_field):
        for feature in content['features']:
            id = str(feature['id'])
            feature['@id'] = (
                self.get_collections_url(dataset, 'items', id)
                if id_field == 'id' else
                feature['properties'].get(id_field)    
            )

        return content

    def __repr__(self):
        return f'<SitemapProcessor> {self.name}'
