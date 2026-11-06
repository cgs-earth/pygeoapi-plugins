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

import geopandas as gpd
import pyarrow.parquet as pq
import pytest

from pygeoapi_plugins.formatter.parquet import ParquetFormatter


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


def test_parquet_formatter(fixture):
    f = ParquetFormatter({})
    result = f.write(data=fixture)

    assert f.mimetype == 'application/vnd.apache.parquet'
    assert f.f == 'parquet'
    assert f.extension == 'parquet'
    assert f.attachment is True

    assert isinstance(result, bytes)
    assert result[:4] == b'PAR1'

    gdf = gpd.read_parquet(io.BytesIO(result))
    assert len(gdf) == 2
    assert list(gdf['name']) == ['Dinagat Islands', 'Manila']
    assert list(gdf['foo']) == ['bar', 'baz']
    assert gdf.geometry[0].x == 125.6
    assert gdf.geometry[0].y == 10.1
    assert gdf.crs == 'OGC:CRS84'

    # No covering bbox by default
    assert 'xmin' not in pq.read_schema(io.BytesIO(result)).names


def test_parquet_formatter_crs(fixture):
    fixture['features'][0]['geometry']['coordinates'] = [
        13981728.0436351,
        1130195.397638891,
    ]
    options = {'content_crs': 'http://www.opengis.net/def/crs/EPSG/0/3857'}
    result = ParquetFormatter({}).write(data=fixture, options=options)

    gdf = gpd.read_parquet(io.BytesIO(result))
    assert gdf.crs.to_epsg() == 3857
    assert gdf.geometry[0].x == pytest.approx(13981728.0436351)


def test_parquet_formatter_schema_version(fixture):
    result = ParquetFormatter({'schema_version': '1.0.0'}).write(data=fixture)

    metadata = pq.read_metadata(io.BytesIO(result)).metadata
    assert b'"version": "1.0.0"' in metadata[b'geo']


def test_parquet_formatter_covering_bbox(fixture):
    f = ParquetFormatter({'write_covering_bbox': True})
    result = f.write(data=fixture)

    metadata = pq.read_metadata(io.BytesIO(result)).metadata
    assert b'"covering"' in metadata[b'geo']

    table = pq.read_table(io.BytesIO(result))
    assert table['bbox'][0].as_py() == {
        'xmin': 125.6,
        'ymin': 10.1,
        'xmax': 125.6,
        'ymax': 10.1,
    }


@pytest.mark.parametrize(
    'data', [None, {'type': 'FeatureCollection', 'features': []}]
)
def test_parquet_formatter_no_features(data):
    assert ParquetFormatter({}).write(data=data) == ''
