# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2023 Benjamin Webb
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

import pytest

from pygeoapi_plugins.provider.sparql import SPARQLProvider


@pytest.fixture()
def config():
    return {
        'name': 'pygeoapi_plugins.provider.sparql.SPARQLProvider',
        'type': 'feature',
        'data': 'tests/data/places.csv',
        'id_field': 'index',
        'geometry': {'x_field': 'lon', 'y_field': 'lat'},
        'sparql_provider': 'CSV',
        'sparql_query': {
            'endpoint': 'https://dbpedia.org/sparql',
            'bind': {'name': 'uri', 'variable': '?subject'},
            'where': [
                '?subject dbo:populationTotal ?population',
                {
                    'predicate': '<http://dbpedia.org/ontology/country>',
                    'object': '?country',
                },
                {'predicate': 'dbpedia2:leaderName', 'object': '?leader'},
            ],
            'filter': [
                'FILTER (isIRI(?leader) || (isLiteral(?leader) && (!bound(datatype(?leader)) || datatype(?leader) = xsd:string)))'
            ],
        },
    }


def test_query(config):
    p = SPARQLProvider(config)

    base_fields = p.p.get_fields()
    assert len(base_fields) == 3
    assert base_fields['city']['type'] == 'string'
    assert base_fields['uri']['type'] == 'string'

    fields = p.get_fields()
    assert len(fields) == 3
    for field in base_fields:
        assert field in fields

    results = p.query()
    assert len(results['features']) == 8

    feature = p.get('0')
    assert feature['id'] == '0'
    assert feature['properties']['city'] == 'Berlin'
    assert feature['properties']['population'] == '3677472'
    assert feature['properties']['country'] == 'http://dbpedia.org/resource/Germany'  # noqa
    assert feature['geometry']['coordinates'][0] == 13.405
    assert feature['geometry']['coordinates'][1] == 52.52

    feature2 = p.get('2')
    assert feature2['properties']['city'] == 'New York'
    assert (
        feature2['properties']['country'] == 'http://dbpedia.org/resource/United_States'
    )  # noqa


def test_query_missing_where(config):
    config['sparql_query']['where'][0] = '?subject dbo:populationTotal'
    p = SPARQLProvider(config)
    feature = p.get('0')
    assert feature['id'] == '0'
    assert feature['properties']['city'] == 'Berlin'
    assert 'population' not in feature['properties']
    assert feature['properties']['country'] == 'http://dbpedia.org/resource/Germany'  # noqa
    assert feature['geometry']['coordinates'][0] == 13.405
    assert feature['geometry']['coordinates'][1] == 52.52
