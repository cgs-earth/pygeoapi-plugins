# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2025 Benjamin Webb
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

import json
from json.decoder import JSONDecodeError
from pathlib import Path

import pytest
from pygeoapi.provider.base import (
    ProviderConnectionError,
    ProviderItemNotFoundError,
    ProviderQueryError,
)

from pygeoapi_plugins.provider.ckan import CKANProvider

# Made-up records shaped like a CKAN datastore_search result
DATA = Path(__file__).parent / 'data' / 'ckan_reservoirs.json'


class FakeResponse:
    """The parts of `requests.Response` the CKAN provider uses"""

    def __init__(self, payload=None, status_code=200, text=None):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self.text is not None:
            raise JSONDecodeError('Expecting value', self.text, 0)
        return self.payload


class FakeCKAN:
    """
    Stands in for the provider's `requests.Session`, answering
    datastore_search requests from local records the way CKAN does
    """

    def __init__(self, data):
        self.resource_id = data['resource_id']
        self.fields = data['fields']
        self.records = data['records']
        self.requests = []
        self.response = None  # Set to return a fixed response instead

    def get(self, url, params=None):
        params = dict(params or {})
        self.requests.append(params)
        return self.response or FakeResponse(self.search(params))

    def search(self, params):
        if params.get('resource_id') != self.resource_id:
            return {'success': False, 'error': {'__type': 'Not Found Error'}}

        records = [dict(r) for r in self.records]

        # filters: exact match on each field
        filters = json.loads(params.get('filters', '{}'))
        records = [
            r
            for r in records
            if all(str(r.get(k)) == str(v) for k, v in filters.items())
        ]

        # q: every term is a word in some field
        terms = str(params.get('q', '')).upper().split()
        records = [
            r
            for r in records
            if all(
                any(term in str(v).upper().split() for v in r.values())
                for term in terms
            )
        ]

        # sort: "field asc, field desc", applied last key first
        for clause in reversed(params.get('sort', '').split(',')):
            if clause.strip():
                field, _, order = clause.strip().partition(' ')
                records.sort(
                    key=lambda r: r[field], reverse=order.lower() == 'desc'
                )

        total = len(records)
        offset = int(params.get('offset', 0))
        limit = int(params.get('limit', 100))
        records = records[offset : offset + limit]

        fields = self.fields
        if params.get('fields'):
            names = params['fields'].split(',')
            fields = [f for f in fields if f['id'] in names]
            records = [{k: r[k] for k in r if k in names} for r in records]

        return {
            'success': True,
            'result': {
                'resource_id': self.resource_id,
                'fields': [dict(f) for f in fields],
                'records': records,
                'offset': offset,
                'limit': limit,
                'total': total,
            },
        }


@pytest.fixture()
def ckan(monkeypatch):
    fake = FakeCKAN(json.loads(DATA.read_text(encoding='utf-8')))
    monkeypatch.setattr('pygeoapi_plugins.provider.ckan.Session', lambda: fake)
    return fake


@pytest.fixture()
def config(ckan):
    return {
        'name': 'pygeoapi_plugins.provider.ckan.CKAN',
        'type': 'feature',
        'data': 'https://catalog.newmexicowaterdata.org/api/3/action/datastore_search',  # noqa
        'resource_id': '08369d21-520b-439e-97e3-5ecb50737887',
        'id_field': '_id',
        'x_field': 'LONDD',
        'y_field': 'LATDD',
    }


def test_query(config):
    p = CKANProvider(config)

    fields = p.get_fields()
    assert len(fields) == 9
    assert fields['DAMNAME']['type'] == 'text'
    assert fields['RES_ID']['type'] == 'numeric'

    results = p.query()
    assert len(results['features']) == 10
    assert results['numberMatched'] == 12
    assert results['numberReturned'] == 10

    assert results['features'][0]['id'] == 1
    assert results['features'][0]['properties']['DAMNAME'] == 'NAVAJO'
    assert results['features'][0]['geometry']['coordinates'][0] == -107.609
    assert results['features'][0]['geometry']['coordinates'][1] == 36.8078

    assert results['features'][2]['id'] == 3
    assert results['features'][2]['properties']['DAMNAME'] == 'LA JARA LAKE'
    assert results['features'][2]['geometry']['coordinates'][0] == -107
    assert results['features'][2]['geometry']['coordinates'][1] == 36.74

    results = p.query(limit=1)
    assert len(results['features']) == 1
    assert results['features'][0]['id'] == 1

    results = p.query(offset=2, limit=1)
    assert len(results['features']) == 1
    assert results['features'][0]['id'] == 3

    results = p.query(limit=12)
    assert len(results['features']) == 12
    assert results['numberMatched'] == 12
    assert results['numberReturned'] == 12

    results = p.query(skip_geometry=True)
    assert results['features'][0]['geometry'] is None


def test_query_past_end(config, ckan):
    p = CKANProvider(config)
    results = p.query(limit=20)

    assert results['numberReturned'] == 12

    # Asks for more after a short page, and stops on an empty one
    offsets = [r['offset'] for r in ckan.requests if 'offset' in r]
    assert offsets == [0, 12]


def test_query_hits(config, ckan):
    p = CKANProvider(config)
    results = p.query(resulttype='hits')

    assert results['numberMatched'] == 12
    assert results['features'] == []
    assert ckan.requests[-1]['include_total'] == 'true'


def test_query_by_properties(config):
    p = CKANProvider(config)
    results = p.query(properties=[('SOURCE', 'E')])
    assert results['numberMatched'] == 6
    assert results['numberReturned'] == 6

    results = p.query(properties=[('RIVER', 'RIO CHAMA')])
    assert results['numberMatched'] == 2
    assert results['numberReturned'] == 2

    results = p.query(properties=[('SOURCE', 'E'), ('RIVER', 'RIO CHAMA')])
    assert results['numberMatched'] == 1
    assert results['numberReturned'] == 1
    assert results['features'][0]['properties']['DAMNAME'] == 'EL VADO'

    results = p.query(properties=[('STATE', 'NM')])
    assert results['numberMatched'] == 12
    assert results['numberReturned'] == 10


def test_query_sortby(config, ckan):
    p = CKANProvider(config)
    results = p.query()
    assert results['features'][0]['properties']['YEAR'] == 1963

    results = p.query(sortby=[{'property': 'YEAR', 'order': '+'}])
    assert results['features'][0]['properties']['YEAR'] == 1893
    assert ckan.requests[-1]['sort'] == 'YEAR asc'

    results = p.query(sortby=[{'property': 'YEAR', 'order': '-'}])
    assert results['features'][0]['properties']['YEAR'] == 1980
    assert ckan.requests[-1]['sort'] == 'YEAR desc'


def test_query_q(config):
    p = CKANProvider(config)
    results = p.query(q='RESERVOIR')
    assert results['numberMatched'] == 3
    assert results['numberReturned'] == 3

    results = p.query(q='LAKE')
    assert results['numberMatched'] == 6
    assert results['numberReturned'] == 6


def test_query_select_properties(config):
    p = CKANProvider(config)
    results = p.query()
    assert len(results['features'][0]['properties']) == 6

    results = p.query(select_properties=['DAMNAME'])
    assert len(results['features'][0]['properties']) == 1

    results = p.query(select_properties=['DAMNAME', 'STATE'])
    assert len(results['features'][0]['properties']) == 2

    config['properties'] = ['DAMNAME', 'RIVER']
    p = CKANProvider(config)
    results = p.query()
    assert len(results['features'][0]['properties']) == 2
    assert results['features'][0]['properties']['DAMNAME'] == 'NAVAJO'


def test_query_select_properties_unchanged(config):
    # The required fields are not added to the caller's list
    config['properties'] = ['DAMNAME']
    select = ['RIVER']
    CKANProvider(config).query(select_properties=select)
    assert select == ['RIVER']

    # Nor to the shared default, which would limit later queries
    config.pop('properties')
    results = CKANProvider(config).query()
    assert len(results['features'][0]['properties']) == 6


def test_get(config):
    p = CKANProvider(config)

    result = p.get(1)
    assert result['id'] == 1
    assert result['properties']['DAMNAME'] == 'NAVAJO'
    assert result['geometry']['coordinates'] == [-107.609, 36.8078]

    # Identifiers from a URL path are strings
    assert p.get('3')['properties']['DAMNAME'] == 'LA JARA LAKE'


def test_get_not_found(config):
    p = CKANProvider(config)

    with pytest.raises(ProviderItemNotFoundError):
        p.get(99)


def test_bad_resource_id(config):
    config['resource_id'] = 'not-a-resource'
    with pytest.raises(ProviderConnectionError):
        CKANProvider(config)


def test_http_error(config, ckan):
    p = CKANProvider(config)
    ckan.response = FakeResponse(status_code=500)

    with pytest.raises(ProviderConnectionError):
        p.query()


def test_not_json(config, ckan):
    p = CKANProvider(config)
    ckan.response = FakeResponse(text='<html>Just a moment...</html>')

    with pytest.raises(ProviderQueryError):
        p.query()
