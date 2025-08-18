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

from tempfile import TemporaryDirectory
from pygeoapi_plugins.provider.mvt_cache import MVTPostgresFilesystem, MVTPostgresCache


PASSWORD = os.environ.get('POSTGRESQL_PASSWORD', 'postgres')
SERVER_URL = 'http://localhost'
DATASET = 'hotosm_bdi_waterways'

TILESET = 'WebMercatorQuad'
Z, X, Y = 10, 595, 521


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
        'format': {'name': 'pbf', 'mimetype': 'application/vnd.mapbox-vector-tile'},
        'storage_crs': 'http://www.opengis.net/def/crs/EPSG/0/4326',
    }


def test_fs_miss_cache_disable_at_z(config):
    d = TemporaryDirectory()
    config['cache_directory'] = d.name

    p = MVTPostgresFilesystem(config)
    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        is None
    )

    tile = p.get_tiles(tileset=TILESET, z=Z, x=X, y=Y)

    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        != tile
    )

    d.cleanup()


def test_fs_disable_at_z(config):
    d = TemporaryDirectory()
    config['cache_directory'] = d.name
    config['disable_cache_at_z'] = 14

    p = MVTPostgresFilesystem(config)
    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        is None
    )

    tile = p.get_tiles(tileset=TILESET, z=Z, x=X, y=Y)

    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        == tile
    )

    d.cleanup()


def test_miss_cache_disable_at_z(config):
    config['force_create'] = True

    p = MVTPostgresFilesystem(config)
    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        is None
    )

    tile = p.get_tiles(tileset=TILESET, z=Z, x=X, y=Y)

    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        != tile
    )


def test_disable_at_z(config):
    config['force_create'] = True
    config['disable_cache_at_z'] = 14

    p = MVTPostgresCache(config)
    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        is None
    )

    tile = p.get_tiles(tileset=TILESET, z=Z, x=X, y=Y)

    assert (
        p.get_tiles_from_cache(
            tileset=TILESET,
            z=Z,
            x=X,
            y=Y,
        )
        == tile
    )
