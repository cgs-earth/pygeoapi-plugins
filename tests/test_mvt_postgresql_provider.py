# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
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

import os
import pytest


from pygeoapi_plugins.provider.mvt_postgresql import MVTPostgreSQLProvider_

PASSWORD = os.environ.get('POSTGRESQL_PASSWORD', 'postgres')
SERVER_URL = 'http://localhost'
DATASET = 'hotosm_bdi_waterways'


@pytest.fixture()
def config():
    return {
        'name': 'MVT-postgresql',
        'type': 'tile',
        'data': {
            'host': '127.0.0.1',
            'dbname': 'test',
            'user': 'postgres',
            'password': PASSWORD,
            'search_path': ['osm', 'public'],
        },
        'id_field': 'osm_id',
        'table': 'hotosm_bdi_waterways',
        'geom_field': 'foo_geom',
        'options': {'zoom': {'min': 0, 'max': 15}},
        'format': {
            'name': 'pbf',
            'mimetype': 'application/vnd.mapbox-vector-tile',
        },
        'storage_crs': 'http://www.opengis.net/def/crs/EPSG/0/4326',
    }


def test_disable_at_z(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 10, 595, 521

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile) == 74047

    config['disable_at_z'] = 11
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 69732
    assert len(tile2) < len(tile)


def test_tile_filter(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 10, 595, 521

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile) == 74047

    config['tile_threshold'] = "waterway = 'river'"
    config['disable_at_z'] = 12
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 7612
    assert len(tile2) < len(tile)


def test_tile_filter_with_z(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 10, 595, 521

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile) == 74047

    config['tile_threshold'] = "z_index = '-{z}'"
    config['disable_at_z'] = 12
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 577
    assert len(tile2) < len(tile)


def test_tile_limit(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 10, 595, 521

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile) == 74047

    config['tile_limit'] = 1000
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 74047
    assert len(tile2) <= len(tile)

    config['tile_limit'] = 500
    p = MVTPostgreSQLProvider_(config)
    tile3 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile3) == 59142
    assert len(tile3) < len(tile)
    assert len(tile3) < len(tile2)

    config['tile_limit'] = 100
    p = MVTPostgreSQLProvider_(config)
    tile4 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile4) == 18408
    assert len(tile4) < len(tile)
    assert len(tile4) < len(tile2)
    assert len(tile4) < len(tile3)


def test_tile_simplify(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 10, 595, 521

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )

    config['simplify_geometry'] = True
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 29405
    assert len(tile2) < len(tile)

    config['disable_at_z'] = 12
    p = MVTPostgreSQLProvider_(config)
    tile3 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile3) == 25372
    assert len(tile3) < len(tile)
    assert len(tile3) < len(tile2)


def test_simplify_low_zoom(config):
    tileset = 'WebMercatorQuad'
    z, x, y = 4, 9, 8

    p = MVTPostgreSQLProvider_(config)
    tile = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile) == 19922

    config['simplify_geometry'] = True
    p = MVTPostgreSQLProvider_(config)
    tile2 = p.get_tiles(
        tileset=tileset,
        z=z,
        x=x,
        y=y,
    )
    assert len(tile2) == 10076
    assert len(tile2) < len(tile)
