# =================================================================
#
# Authors: Ben Webb <bwebb@lincolninst.edu>
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


import copy
import json
import pickle

import orjson
import pytest
from pygeoapi.formatter.base import FormatterSerializationError
from pygeoapi.linked_data import jsonldify_geometry
from pygeoapi.util import to_json

from pygeoapi_plugins.formatter.json_ import (
    GeoJSONFeature,
    GeoJSONGeometry,
    JSONFormatter,
)

POINT = '{"type":"Point","coordinates":[125.6,10.1]}'


@pytest.fixture()
def fixture():
    data = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'id': '123-456',
                'geometry': {'type': 'Point', 'coordinates': [125.6, 10.1]},
                'properties': {'name': 'Dinagat Islands', 'foo': 'bar'},
            }
        ],
        'links': [
            {
                'rel': 'self',
                'type': 'application/geo+json',
                'title': 'GeoJSON',
                'href': 'http://example.com',
            }
        ],
    }

    return data


def test_json_formatter(fixture):
    f = JSONFormatter({'geom': True})
    result = f.write(data=fixture)

    assert isinstance(result, bytes)
    assert f.mimetype == 'application/geo+json'
    assert f.f == 'json'
    assert f.extension == 'json'
    assert json.loads(result) == fixture


def test_json_formatter_no_escape(fixture):
    fixture['features'][0]['properties']['name'] = '<b>Dinagat</b>'
    result = JSONFormatter({}).write(data=fixture)

    assert b'<b>Dinagat</b>' in result
    assert b'&lt;' not in result


def test_json_formatter_pretty(fixture):
    result = JSONFormatter({}).write(data=fixture, options={'pretty': True})

    assert b'\n  "type"' in result
    assert json.loads(result) == fixture


def test_json_formatter_no_data():
    assert JSONFormatter({}).write(data=None) == b''


def test_json_formatter_unserializable(fixture):
    fixture['features'][0]['properties']['foo'] = object()

    with pytest.raises(FormatterSerializationError):
        JSONFormatter({}).write(data=fixture)


@pytest.mark.parametrize('geometry', [POINT, POINT.encode()])
def test_json_formatter_string_geometry(fixture, geometry):
    expected = copy.deepcopy(fixture)
    fixture['features'][0]['geometry'] = geometry

    result = JSONFormatter({}).write(data=fixture)

    assert json.loads(result) == expected
    # The input is not modified
    assert fixture['features'][0]['geometry'] == geometry


def test_json_formatter_single_feature(fixture):
    feature = fixture['features'][0]
    expected = copy.deepcopy(feature)
    feature['geometry'] = GeoJSONGeometry(POINT)

    result = JSONFormatter({}).write(data=feature)

    assert json.loads(result) == expected


def test_json_formatter_geojson_geometry(fixture):
    expected = copy.deepcopy(fixture)
    geometry = GeoJSONGeometry(POINT)
    fixture['features'][0]['geometry'] = geometry

    result = JSONFormatter({}).write(data=fixture)

    assert json.loads(result) == expected
    # Written from raw, so the geometry is never parsed
    assert geometry._loaded is False


def test_json_formatter_geojson_feature(fixture):
    raw = orjson.dumps(fixture['features'][0])
    feature = GeoJSONFeature(raw)
    data = {**fixture, 'features': [feature]}

    result = JSONFormatter({}).write(data=data)

    # Written from raw, unchanged, and never parsed
    assert raw in result
    assert json.loads(result) == fixture
    assert feature._loaded is False
    # Read as a dict, it parses to the same feature
    assert dict(feature) == fixture['features'][0]


def test_geojson_geometry_none():
    assert GeoJSONGeometry(None) is None


def test_geojson_geometry_lazy():
    geometry = GeoJSONGeometry(POINT)

    assert geometry.raw == POINT
    assert geometry._loaded is False

    # Reading the geometry parses it
    assert geometry['coordinates'] == [125.6, 10.1]
    assert geometry._loaded is True


@pytest.mark.parametrize(
    'read',
    [
        lambda g: g['coordinates'],
        lambda g: g.get('coordinates'),
        lambda g: dict(g),
        lambda g: {**g},
        lambda g: list(g.items()),
        lambda g: list(g),
        lambda g: len(g),
        lambda g: 'coordinates' in g,
        lambda g: repr(g),
        lambda g: g == {},
    ],
)
def test_geojson_geometry_reads_parse(read):
    geometry = GeoJSONGeometry(POINT)
    read(geometry)

    assert geometry._loaded is True
    assert geometry == json.loads(POINT)
    assert len(geometry) == 2


def test_geojson_geometry_as_dict():
    expected = json.loads(POINT)

    assert json.loads(json.dumps(GeoJSONGeometry(POINT))) == expected
    assert json.loads(to_json(GeoJSONGeometry(POINT))) == expected
    assert copy.deepcopy(GeoJSONGeometry(POINT)) == expected


def test_geojson_geometry_jsonld():
    feature = {'id': '123-456', 'geometry': GeoJSONGeometry(POINT)}
    jsonldify_geometry(feature)

    wkt = feature['gsp:hasGeometry']['gsp:asWKT']['@value']
    assert wkt == 'POINT (125.6 10.1)'


def test_geojson_geometry_pickle():
    geometry = GeoJSONGeometry(POINT)
    geometry['bbox'] = [125.6, 10.1, 125.6, 10.1]

    restored = pickle.loads(pickle.dumps(geometry))

    assert isinstance(restored, GeoJSONGeometry)
    assert restored.raw == POINT
    assert restored == geometry


def test_geojson_geometry_type_not_first():
    raw = '{"coordinates":[125.6,10.1],"type":"Point"}'
    geometry = GeoJSONGeometry(raw)

    # Parsed straight away, as the type cannot be read from the start
    assert geometry._loaded is True
    assert geometry == json.loads(raw)


def test_geojson_geometry_unread_orjson():
    # orjson reads dict storage directly, so an unread geometry
    # only has its type; JSONFormatter writes raw instead
    geometry = GeoJSONGeometry(POINT)

    assert orjson.loads(orjson.dumps(geometry)) == {'type': 'Point'}
