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
                'FILTER (isIRI(?leader) || (isLiteral(?leader) && (!bound(datatype(?leader)) || datatype(?leader) = xsd:string)))'  # noqa
            ],
        },
    }


@pytest.fixture()
def huc_config():
    return {
        'name': 'pygeoapi_plugins.provider.sparql.SPARQLProvider',
        'type': 'feature',
        'data': 'tests/data/hu02.gpkg',
        'id_field': 'HUC2',
        'sparql_provider': 'pygeoapi_plugins.provider.geopandas_.GeoPandasProvider',
        'sparql_query': {
            'endpoint': 'https://graph.geoconnex.us',
            'prefixes': {
                'hyf': '<https://www.opengis.net/def/schema/hy_features/hyf/>'
            },
            'bind': {'name': 'uri', 'variable': '?huc'},
            'select': '?huc ?hucLevel (GROUP_CONCAT(?containedCatchment; SEPARATOR="|") AS ?hucs)',
            'groupby': '?huc ?hucLevel',
            'where': [
                '?containedCatchment hyf:containingCatchment ?huc',
            ],
            'filter': [
                'BIND(REPLACE(STR(?containedCatchment), "^.*ref/(hu[0-9]+)/.*$", "$1") AS ?hucLevel)'
            ],
        },
    }


@pytest.fixture()
def mainstem_config():
    return {
        'name': 'pygeoapi_plugins.provider.sparql.SPARQLProvider',
        'type': 'feature',
        'data': 'tests/data/mainstem.json',
        'id_field': 'id',
        'sparql_provider': 'GeoJSON',
        'sparql_query': {
            'endpoint': 'https://graph.geoconnex.us',
            'prefixes': {
                'schema': '<https://schema.org/>',
                'gsp': '<http://www.opengis.net/ont/geosparql#>',
                'hyf': '<https://www.opengis.net/def/schema/hy_features/hyf/>',
            },
            'bind': {'name': 'uri', 'variable': '?mainstem'},
            'select': '?mainstem ?datasets',
            'where': [
                '?monitoringLocation hyf:HydroLocationType ?type',
                '?monitoringLocation hyf:referencedPosition/hyf:HY_IndirectPosition/hyf:linearElement ?mainstem',
                '?monitoringLocation schema:subjectOf ?dataset',
                '?monitoringLocation gsp:hasGeometry/gsp:asWKT ?wkt',
                '?dataset schema:variableMeasured ?var',
                '?dataset schema:url ?url',
                '?dataset schema:distribution ?distribution',
                '?dataset schema:description ?datasetDescription',
                '?dataset schema:temporalCoverage ?temporalCoverage',
                '?dataset schema:name ?siteName',
                '?var schema:name ?variableMeasured',
                '?var schema:unitText ?variableUnit',
                '?var schema:measurementTechnique ?measurementTechnique',
                '?distribution schema:name ?distributionName',
                '?distribution schema:contentUrl ?distributionURL',
                '?distribution schema:encodingFormat ?distributionFormat',
            ],
            'filter': [
                """
                BIND(
                    CONCAT(
                        '{',
                        '"monitoringLocation":"', STR(?monitoringLocation),
                        '","siteName":"', STR(?siteName),
                        '","datasetDescription":"', STR(?datasetDescription),
                        '","type":"', STR(?type),
                        '","url":"', STR(?url),
                        '","variableMeasured":"', STR(?variableMeasured),
                        '","variableUnit":"', STR(?variableUnit),
                        '","measurementTechnique":"', STR(?measurementTechnique),
                        '","temporalCoverage":"', STR(?temporalCoverage),
                        '","distributionName":"', STR(?distributionName),
                        '","distributionURL":"', STR(?distributionURL),
                        '","distributionFormat":"', STR(?distributionFormat),
                        '","wkt":"', STR(?wkt),
                        '"}'
                    ) AS ?datasets
                )
                """
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
        feature2['properties']['country'] == 'http://dbpedia.org/resource/United_States'  # noqa
    )


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


def test_query_nested_results(huc_config):
    p = SPARQLProvider(huc_config)

    feature_id = '01'
    feature = p.get(feature_id)

    for result in feature['properties']['datasets']:
        hucLevel = result['hucLevel']
        hucs = result['hucs']

        match hucLevel:
            case 'hu04':
                assert len(hucs) == 10
            case 'hu06':
                assert len(hucs) == 11
            case 'hu08':
                assert len(hucs) == 58
            case 'hu10':
                assert len(hucs) == 413

        for huc in hucs:
            assert huc.startswith('https://geoconnex.us/ref/' + hucLevel)
            assert huc.split('/')[-1].startswith(feature_id)


def test_query_mainstem_result(mainstem_config):
    p = SPARQLProvider(mainstem_config)

    feature = p.get('381404')

    assert len(feature['properties']['datasets']) >= 8

    expected_keys = [
        'monitoringLocation',
        'siteName',
        'datasetDescription',
        'type',
        'url',
        'variableMeasured',
        'variableUnit',
        'measurementTechnique',
        'temporalCoverage',
        'wkt',
        'distributionName',
        'distributionURL',
        'distributionFormat',
    ]

    for dataset in feature['properties']['datasets']:
        assert all(k in dataset for k in expected_keys)


def test_sparql_with_limit(mainstem_config):
    mainstem_config['sparql_query']['limit'] = 5
    p = SPARQLProvider(mainstem_config)

    feature = p.get('381404')

    assert len(feature['properties']['datasets']) == 5

    mainstem_config['sparql_query']['limit'] = 'Notanummber'
    p = SPARQLProvider(mainstem_config)

    feature = p.get('381404')

    assert len(feature['properties']['datasets']) == 3707

    mainstem_config['sparql_query']['limit'] = 0
    p = SPARQLProvider(mainstem_config)

    feature = p.get('381404')

    assert len(feature['properties']['datasets']) == 3707
