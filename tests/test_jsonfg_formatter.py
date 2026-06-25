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

import json
import pytest

from pygeoapi_plugins.formatter.jsonfg import JSONFGFormatter


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


@pytest.fixture()
def spatiotemporal_fixture():
    data = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'id': '123-456',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [13981728.0436351, 1130195.397638891],
                },
                'properties': {
                    'name': 'Dinagat Islands',
                    'foo': 'bar',
                    'timestamp': '2020-01-01T00:00:00Z',
                },
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


def test_jsonfg__formatter(fixture):
    f = JSONFGFormatter({'geom': True})
    result = f.write(data=fixture)
    f_jsonfg = json.loads(result)

    assert f.mimetype == 'application/fg+json'

    assert f_jsonfg['type'] == 'FeatureCollection'
    assert f_jsonfg['features'][0]['type'] == 'Feature'
    assert f_jsonfg['features'][0]['geometry']['type'] == 'Point'
    assert f_jsonfg['features'][0]['geometry']['coordinates'] == [125.6, 10.1]
    assert f_jsonfg['features'][0]['properties']['name'] == 'Dinagat Islands'
    assert f_jsonfg['features'][0]['properties']['foo'] == 'bar'

    assert f_jsonfg['featureType'] == 'OGRGeoJSON'
    assert f_jsonfg['conformsTo']
    assert (
        f_jsonfg['coordRefSys']
        == 'http://www.opengis.net/def/crs/OGC/1.3/CRS84'
    )

    assert len(f_jsonfg['links']) == 1


def test_jsonfg_spatiotemporal_formatter(spatiotemporal_fixture):
    f = JSONFGFormatter({'geom': True})
    options = {
        'provider_def': {'time_field': 'timestamp'},
        'content_crs': 'http://www.opengis.net/def/crs/EPSG/0/3857',
    }
    result = f.write(data=spatiotemporal_fixture, options=options)
    f_jsonfg = json.loads(result)

    assert f.mimetype == 'application/fg+json'

    assert f_jsonfg['type'] == 'FeatureCollection'
    assert f_jsonfg['features'][0]['type'] == 'Feature'
    assert f_jsonfg['features'][0]['geometry']['type'] == 'Point'
    assert f_jsonfg['features'][0]['geometry']['coordinates'] == pytest.approx(
        [125.6, 10.1]
    )
    assert f_jsonfg['features'][0]['properties']['name'] == 'Dinagat Islands'
    assert f_jsonfg['features'][0]['properties']['foo'] == 'bar'

    assert (
        f_jsonfg['coordRefSys'] == 'http://www.opengis.net/def/crs/EPSG/0/3857'
    )
    assert f_jsonfg['features'][0]['place']['coordinates'] == [
        13981728.0436351,
        1130195.397638891,
    ]

    assert f_jsonfg['features'][0]['time'] == '2020-01-01T00:00:00Z'

    assert len(f_jsonfg['links']) == 1
