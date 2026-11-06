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


import io
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import pytest

from pygeoapi_plugins.formatter.shape import (
    GPKGFormatter,
    KMLFormatter,
    PGDUMPFormatter,
    ShapefileFormatter,
)


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
            },
            {
                'type': 'Feature',
                'id': '789-012',
                'geometry': {'type': 'Point', 'coordinates': [120.9, 14.6]},
                'properties': {'name': 'Manila', 'foo': 'baz'},
            },
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


def test_shapefile_formatter(fixture):
    f = ShapefileFormatter({})
    result = f.write(data=fixture, options={'dataset': 'islands'})

    assert f.mimetype == 'application/zip'
    assert f.f == 'shp'
    assert f.extension == 'zip'
    assert f.attachment is True

    with zipfile.ZipFile(io.BytesIO(result)) as zipf:
        names = zipf.namelist()
        for ext in ('shp', 'shx', 'dbf', 'prj'):
            assert f'islands.{ext}' in names

    gdf = gpd.read_file(io.BytesIO(result))
    assert len(gdf) == 2
    assert list(gdf['name']) == ['Dinagat Islands', 'Manila']
    assert gdf.geometry[0].x == 125.6
    assert 'CRS84' in gdf.crs.name


def test_shapefile_formatter_default_name(fixture):
    result = ShapefileFormatter({}).write(data=fixture)

    with zipfile.ZipFile(io.BytesIO(result)) as zipf:
        assert 'data.shp' in zipf.namelist()


def test_kml_formatter(fixture):
    f = KMLFormatter({})
    result = f.write(data=fixture)

    assert f.mimetype == 'application/vnd.google-earth.kml+xml'
    assert f.f == 'kml'
    assert f.extension == 'kml'
    assert f.attachment is True

    root = ET.fromstring(result)
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    placemarks = root.findall('.//kml:Placemark', ns)
    assert len(placemarks) == 2

    coordinates = placemarks[0].find('.//kml:coordinates', ns).text
    assert coordinates.strip().startswith('125.6,10.1')


def test_gpkg_formatter(fixture):
    f = GPKGFormatter({})
    result = f.write(data=fixture)

    assert f.mimetype == 'application/geopackage+sqlite3'
    assert f.f == 'gpkg'
    assert f.extension == 'gpkg'
    assert f.attachment is True

    assert result[:16] == b'SQLite format 3\x00'

    with tempfile.NamedTemporaryFile(suffix='.gpkg') as tmp:
        tmp.write(result)
        tmp.flush()

        gdf = gpd.read_file(tmp.name)
        assert len(gdf) == 2
        assert list(gdf['name']) == ['Dinagat Islands', 'Manila']
        assert gdf.geometry[0].x == 125.6
        assert 'CRS84' in gdf.crs.name


def test_pgdump_formatter(fixture):
    f = PGDUMPFormatter({})
    result = f.write(data=fixture)

    assert f.mimetype == 'application/sql'
    assert f.f == 'pgdump'
    assert f.extension == 'sql'
    assert f.attachment is True

    sql = result.decode()
    assert 'CREATE TABLE' in sql
    assert 'Dinagat Islands' in sql
    assert 'Manila' in sql


@pytest.mark.parametrize(
    'formatter',
    [ShapefileFormatter, KMLFormatter, GPKGFormatter, PGDUMPFormatter],
)
@pytest.mark.parametrize(
    'data', [None, {'type': 'FeatureCollection', 'features': []}]
)
def test_shape_formatters_no_features(formatter, data):
    assert formatter({}).write(data=data) == ''
