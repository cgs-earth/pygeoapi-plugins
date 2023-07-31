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

import io
import math
import os
import logging
import zipfile

from pygeoapi.plugin import load_plugin
from pygeoapi.process.base import BaseProcessor
from pygeoapi.linked_data import geojson2jsonld
from pygeoapi.openapi import get_oas
from pygeoapi.util import (yaml_load, get_provider_default, url_join,
                           filter_dict_by_key_value)

from pygeoapi_plugins.formatter.xml import XMLFormatter


LOGGER = logging.getLogger(__name__)

with open(os.getenv('PYGEOAPI_CONFIG'), encoding='utf8') as fh:
    CONFIG = yaml_load(fh)
    COLLECTIONS = filter_dict_by_key_value(CONFIG['resources'],
                                           'type', 'collection')
    # TODO: Filter collections for those that support CQL


PROCESS_DEF = CONFIG['resources']['sitemap-generator']
PROCESS_DEF.update({
    'version': '0.1.0',
    'id': 'sitemap-generator',
    'title': 'Sitemap Generator',
    'description': ('A process that returns a sitemap of'
                    'all pygeoapi endpoints.'),
    'links': [{
        'type': 'text/html',
        'rel': 'about',
        'title': 'information',
        'href': 'https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview',  # noqa
        'hreflang': 'en-US'
    }],
    'inputs': {
        'zip': {
            'title': {
                'en': 'ZIP response'
            },
            'description': {
                'en': 'Boolean whether to ZIP the response'
            },
            'keywords': {
                'en': ['sitemap', 'pygeoapi']
            },
            'schema': {
                'type': 'boolean',
                'default': False
            },
            'minOccurs': 0,
            'maxOccurs': 1,
            'metadata': None,  # TODO how to use?
        },
    },
    'outputs': {
        'sitemap': {
            'title': {
                'en': 'Sitemap'
            },
            'description': {
                'en': 'A sitemap of the pygeoapi instance'
            },
            'schema': {
                'type': 'object',
                'contentMediaType': 'application/json'
            }
        }
    },
    'example': {
        'inputs': {
            'zip': False
        }
    }
})


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

    def execute(self, data):
        """
        Execute Sitemap Process

        :param data: processor arguments

        :returns: 'application/json'
        """
        mimetype = 'application/json'

        if data.get('zip'):
            LOGGER.debug('Returning zipped response')
            zip_output = io.BytesIO()
            with zipfile.ZipFile(zip_output, 'w') as zipf:
                for filename, content in self.generate():
                    zipf.writestr(filename, content)
            return 'application/zip', zip_output.getvalue()

        else:
            LOGGER.debug('Returning response')
            return mimetype, dict(self.generate())

    def generate(self):
        """
        Execute Sitemap Process

        :param data: processor arguments
        """
        LOGGER.debug('Generating core.xml')
        oas = {'features': []}
        for path in get_oas(self.config)['paths']:
            if r'{jobId}' not in path and r'{featureId}' not in path:
                path_uri = url_join(self.base_url, path)
                oas['features'].append({'@id': path_uri})
        yield ('core.xml', self.xml.write(data=oas))

        LOGGER.debug('Generating collections sitemap')
        for cname, c in COLLECTIONS.items():
            p = get_provider_default(c['providers'])
            provider = load_plugin('provider', p)
            _ = provider.query(resulttype='hits')
            hits = _['numberMatched']
            for i in range(math.ceil(hits / 50000)):
                sitemap_name = f'{cname}__{i}.xml'
                LOGGER.debug(f'Generating {sitemap_name}')
                yield (sitemap_name, self._generate(i, cname, provider))

    def _generate(self, index, dataset, provider, n=50000):
        """
        Private Function: Generate sitemap

        :param index: feature list index
        :param dataset: OGC API Provider name
        :param provider: OGC API Provider definition
        :param n: Number per index

        :returns: List of GeoJSON Features
        """

        content = provider.query(offset=(n*index), limit=n)
        content['links'] = []
        content = geojson2jsonld(
            self, content, dataset, id_field=(provider.uri_field or 'id')
        )
        return self.xml.write(data=content)

    def __repr__(self):
        return f'<SitemapProcessor> {self.name}'

    def get_collections_url(self):
        return f'{self.base_url}/collections'
