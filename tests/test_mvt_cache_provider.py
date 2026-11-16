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
from pygeoapi_plugins.provider.mvt_cache import (
    MVTPostgresFilesystem,
    MVTPostgresCache,
    MVTPostgresRedis,
)


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
        'format': {
            'name': 'pbf',
            'mimetype': 'application/vnd.mapbox-vector-tile',
        },
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


def test_redis_cache(config):
    config['redis_host'] = 'localhost'
    config['redis_port'] = 6379
    config['disable_cache_at_z'] = 14

    p = MVTPostgresRedis(config)

    # Start from an empty cache, as Redis keeps tiles between runs
    key = p._get_tile_key('default', TILESET, Z, Y, X, 'pbf')
    p.db.delete(key)

    try:
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
    finally:
        p.db.delete(key)


@pytest.mark.parametrize('cache_empty_tiles', [True, False])
@pytest.mark.parametrize(
    'provider', [MVTPostgresFilesystem, MVTPostgresCache, MVTPostgresRedis]
)
def test_cache_empty_tiles(config, provider, cache_empty_tiles):
    # A tile in the Atlantic, far from the Burundi test data
    z, x, y = 5, 0, 0

    d = TemporaryDirectory()
    config['cache_directory'] = d.name
    config['cache_empty_tiles'] = cache_empty_tiles

    p = provider(config)

    def clear_cache():
        # Redis and the cache table keep tiles between tests. The table's
        # force_create only drops it once per process, so delete the tile.
        if provider is MVTPostgresRedis:
            p.db.delete(p._get_tile_key('default', TILESET, z, y, x, 'pbf'))
        elif provider is MVTPostgresCache:
            table = p.cache_model
            with p._engine.begin() as conn:
                conn.execute(
                    table.delete().where(
                        table.c.z == z, table.c.x == x, table.c.y == y
                    )
                )

    clear_cache()
    try:
        assert p.get_tiles_from_cache(tileset=TILESET, z=z, x=x, y=y) is None

        tile = p.get_tiles(tileset=TILESET, z=z, x=x, y=y)
        assert tile == b''

        cached = p.get_tiles_from_cache(tileset=TILESET, z=z, x=x, y=y)
        assert cached == (b'' if cache_empty_tiles else None)

        # A cached empty tile is served from the cache
        assert p.get_tiles(tileset=TILESET, z=z, x=x, y=y) == b''
    finally:
        clear_cache()
        d.cleanup()
