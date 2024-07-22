# =================================================================
#
# Authors: Colton Loftus
#
# Copyright (c) 2024 Colton Loftus
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

import datetime

import geopandas as gpd
import pytest
import shapely

from pygeoapi.provider.base import ProviderItemNotFoundError
from pygeoapi.provider.geopandas_ import GeoPandasProvider
from tests.util import get_test_file_path


@pytest.fixture()
def config():
    return {
        'name': 'CSV',
        'type': 'feature',
        'data': get_test_file_path('data/obs.csv'),
        'id_field': 'id',
        'geometry': {'x_field': 'long', 'y_field': 'lat'},
    }


@pytest.fixture()
def station_config():
    return {
        'name': 'CSV',
        'type': 'feature',
        'data': get_test_file_path('data/station_list.csv'),
        'id_field': 'wigos_station_identifier',
        'geometry': {'x_field': 'longitude', 'y_field': 'latitude'},
    }


@pytest.fixture()
def gpkg_config():
    return {
        'name': 'gpkg',
        'type': 'feature',
        'data': get_test_file_path('data/hu02.gpkg'),
        'id_field': 'HUC2',
    }


def test_csv_query(config):
    p = GeoPandasProvider(config)

    fields = p.get_fields()
    assert len(fields) == 4
    assert ['id', 'stn_id', 'datetime', 'value'] == list(fields.keys())
    assert fields['value']['type'] == 'number'
    assert fields['stn_id']['type'] == 'integer'

    results = p.query()
    assert len(results['features']) == 5
    assert results['numberMatched'] == 5
    assert results['numberReturned'] == 5
    assert results['features'][0]['id'] == '371'
    assert results['features'][0]['properties']['value'] == 89.9

    assert results['features'][0]['geometry']['coordinates'][0] == -75.0
    assert results['features'][0]['geometry']['coordinates'][1] == 45.0

    results = p.query(limit=1)
    assert len(results['features']) == 1
    assert results['features'][0]['id'] == '371'

    results = p.query(offset=2, limit=1)
    assert len(results['features']) == 1
    assert results['features'][0]['id'] == '238'
    # should just be stn_id, datetime and value
    assert len(results['features'][0]['properties']) == 3

    results = p.query(select_properties=['value'])
    assert len(results['features'][0]['properties']) == 1

    results = p.query(select_properties=['value', 'stn_id'])
    assert len(results['features'][0]['properties']) == 2

    results = p.query(skip_geometry=True)
    assert results['features'][0]['geometry'] is None

    results = p.query(properties=[('stn_id', '604')])
    assert len(results['features']) == 1
    assert results['numberMatched'] == 1
    assert results['numberReturned'] == 1

    results = p.query(properties=[('stn_id', '35')])
    assert len(results['features']) == 2
    assert results['numberMatched'] == 2
    assert results['numberReturned'] == 2

    results = p.query(properties=[('stn_id', '35'), ('value', '93.9')])
    assert len(results['features']) == 1

    config['properties'] = ['value', 'stn_id']
    p = GeoPandasProvider(config)
    results = p.query()
    assert len(results['features'][0]['properties']) == 2


def test_csv_get(config):
    p = GeoPandasProvider(config)

    result = p.get('964')
    assert result['id'] == '964'
    assert result['properties']['value'] == 99.9


def test_csv_get_not_existing_item_raise_exception(config):
    """Testing query for a not existing object"""
    p = GeoPandasProvider(config)
    with pytest.raises(ProviderItemNotFoundError):
        p.get('404')


def test_csv_get_station(station_config):
    p = GeoPandasProvider(station_config)

    results = p.query(limit=20)
    assert len(results['features']) == 20
    assert results['numberMatched'] == 79
    assert results['numberReturned'] == 20

    result = p.get('0-20000-0-16337')
    assert result['properties']['station_name'] == 'BONIFATI (16337-0)'

    result = p.get('0-454-2-AWSNAMITAMBO')
    assert result['properties']['station_name'] == 'NAMITAMBO'


# Make sure the way we are filtering the dataframe works in general outside of the provider
def test_intersection():
    gdf = gpd.read_file(get_test_file_path('data/hu02.gpkg'))
    gdf = gdf[gdf['HUC2'] == '01']

    minx, miny, maxx, maxy = -70.5, 43.0, -70.0, 43.3
    polygon = shapely.geometry.Polygon(
        [(minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny)]
    )
    box = shapely.box(minx, miny, maxx, maxy)
    huc_range: shapely.geometry.MultiPolygon = gdf['geometry'].iloc[0]

    assert isinstance(huc_range, shapely.geometry.MultiPolygon)
    assert isinstance(polygon, shapely.geometry.Polygon)
    assert shapely.intersects(polygon, huc_range) == True  # noqa
    assert shapely.intersects(box, huc_range) == True  # noqa

    gdf = gpd.read_file(get_test_file_path('data/hu02.gpkg'))
    box = shapely.box(minx, miny, maxx, maxy)
    gdf = gdf[gdf['geometry'].intersects(box)]

    assert len(gdf) == 1


def test_gpkg_bbox_query(gpkg_config):
    p = GeoPandasProvider(gpkg_config)

    results = p.query(limit=1)
    assert len(results['features']) == 1

    results = p.query(offset=1, limit=1)
    assert len(results['features']) == 1

    results = p.query(skip_geometry=True)
    assert results['features'][0]['geometry'] is None

    results = p.query(properties=[('uri', 'https://geoconnex.us/ref/hu02/07')])
    assert len(results['features']) == 1
    assert (
        results['features'][0]['properties']['uri']
        == 'https://geoconnex.us/ref/hu02/07'
    )

    results = p.query(
        bbox=(0, 0, 0, 0), properties=[('uri', 'https://geoconnex.us/ref/hu02/07')]
    )
    assert len(results['features']) == 0

    # Should intersect with New England
    results = p.query(bbox=(-70.5, 43.0, -70.0, 43.3))
    assert len(results['features']) == 1
    assert results['features'][0]['id'] == '01'

    # Should intersect with Midatlantic and New England
    results = p.query(bbox=(-74.881, 40.566, -71.249, 41.27))
    assert len(results['features']) == 2
    assert results['features'][0]['id'] == '01'
    assert results['features'][1]['id'] == '02'


def test_gpkg_date_query(gpkg_config):
    p = GeoPandasProvider(gpkg_config)

    results = p.query(datetime_='2019-10-10')
    assert len(results['features']) == 1
    assert (
        results['features'][0]['properties']['LOADDATE'] == '2019-10-10 20:08:56+00:00'
    )

    results = p.query(datetime_='../1900-09-18T17:34:02.666+00:00')
    assert len(results['features']) == 0

    results = p.query(datetime_='2900-09-18/..')
    assert len(results['features']) == 0

    results = p.query(datetime_='2016-09-22')
    assert len(results['features']) == 1

    results = p.query(datetime_='2016-09-22/2016-11-23')
    assert len(results['features']) == 2
    assert (
        results['features'][0]['properties']['LOADDATE'] == '2016-10-11 21:37:03+00:00'
    )
    assert (
        results['features'][1]['properties']['LOADDATE'] == '2016-09-22 06:01:28+00:00'
    )

    results = p.query(datetime_='2000-01-01T00:00:00Z/2016-11-23')
    assert len(results['features']) == 2
    assert (
        results['features'][0]['properties']['LOADDATE'] == '2016-10-11 21:37:03+00:00'
    )
    assert (
        results['features'][1]['properties']['LOADDATE'] == '2016-09-22 06:01:28+00:00'
    )

    results = p.query(datetime_='2016')
    assert len(results['features']) == 2
    assert (
        results['features'][0]['properties']['LOADDATE'] == '2016-10-11 21:37:03+00:00'
    )
    assert (
        results['features'][1]['properties']['LOADDATE'] == '2016-09-22 06:01:28+00:00'
    )


def test_gpkg_sort_query(gpkg_config):
    p = GeoPandasProvider(gpkg_config)

    results = p.query(sortby=[{'property': 'LOADDATE', 'order': '-'}])
    # Sort by descending so we expect the newest date first
    assert (
        results['features'][0]['properties']['LOADDATE'] == '2019-10-31 16:20:07+00:00'
    )

    # Create a dummy row In order to test breaking ties
    dummy_row = {
        'uri': '_',
        'NAME': 'AAAAAAA_THIS_KEY_SHOULD_BE_SORTED_TO_BE_FIRST',
        'gnis_url': '_',
        'GNIS_ID': '_',
        'HUC2': '_',
        # Tie for the latest date in the dataset
        'LOADDATE': datetime.datetime.fromisoformat('2019-10-31T16:20:07+00:00'),
        'geometry': shapely.box(0, 0, 0, 0),
    }

    p.gdf = p.gdf._append(dummy_row, ignore_index=True)
    assert (len(p.gdf)) == 23

    results = p.query(
        sortby=[
            {'property': 'LOADDATE', 'order': '-'},
            {'property': 'NAME', 'order': '+'},
        ]
    )
    assert (
        results['features'][0]['properties']['NAME']
        == 'AAAAAAA_THIS_KEY_SHOULD_BE_SORTED_TO_BE_FIRST'
    )


def test_transaction(gpkg_config):
    p = GeoPandasProvider(gpkg_config)

    dummy_row = {
        'uri': '_',
        'NAME': '_',
        'gnis_url': '_',
        'GNIS_ID': '',
        'HUC2': '1111',
        'LOADDATE': datetime.datetime.fromisoformat('2019-10-31T16:20:07+00:00'),
        'geometry': shapely.box(0, 0, 0, 0),
    }

    id = p.create(dummy_row)

    assert id == '1111'

    assert len(p.gdf) == 23

    dummy_row_updated = {
        'uri': '_',
        'NAME': 'TEST_NAME',
        'gnis_url': '_',
        'GNIS_ID': '',
        'HUC2': '1111',
        'LOADDATE': datetime.datetime.fromisoformat('2019-10-31T16:20:08+00:00'),
        'geometry': shapely.box(0, 0, 0, 0),
    }

    success = p.update(dummy_row_updated['HUC2'], dummy_row_updated)

    assert len(p.gdf) == 23

    assert success

    res = p.get('1111')

    assert res['properties']['NAME'] == 'TEST_NAME'

    success = p.delete('1111')

    assert len(p.gdf) == 22
    assert success

    with pytest.raises(ProviderItemNotFoundError):
        res = p.get('1111')
