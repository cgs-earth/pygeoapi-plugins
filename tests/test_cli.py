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


import os

import pytest
import yaml
from click.testing import CliRunner

from pygeoapi_plugins.cli import get_cache_providers, mvt_cache
from pygeoapi_plugins.provider.mvt_cache import MVTPostgresFilesystem

FILESYSTEM_CACHE = 'pygeoapi_plugins.provider.mvt_cache.MVTPostgresFilesystem'
PASSWORD = os.environ.get('POSTGRESQL_PASSWORD', 'postgres')

def _tile_provider(name, **extra):
    return {
        'type': 'tile',
        'name': name,
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
        **extra,
    }


def _collection(*providers):
    return {'type': 'collection', 'providers': list(providers)}


@pytest.fixture()
def cache_def(tmp_path):
    # Cache zoom levels 0 and 1 only, to keep the test quick. With
    # disable_at_z 0, small features are kept, so these tiles are not empty
    return _tile_provider(
        FILESYSTEM_CACHE,
        cache_directory=str(tmp_path / 'tiles'),
        disable_cache_at_z=2,
        disable_at_z=0,
    )


@pytest.fixture()
def config(cache_def):
    return {
        'resources': {
            'waterways': _collection(cache_def),
            'uncached': _collection(_tile_provider('MVT-postgresql')),
            'places': _collection(
                {'type': 'feature', 'name': 'CSV', 'data': 'x.csv'}
            ),
            'intersector': {'type': 'process'},
        }
    }


@pytest.fixture()
def config_file(tmp_path, config):
    path = tmp_path / 'pygeoapi.config.yml'
    path.write_text(yaml.safe_dump(config), encoding='utf-8')
    return path


def test_get_cache_providers(config, cache_def):
    # Only tile providers that cache, by name or dotted path
    assert get_cache_providers(config) == {'waterways': cache_def}


def test_pre_cache(config_file, cache_def):
    result = CliRunner().invoke(mvt_cache, ['pre-cache', str(config_file)])

    assert result.exit_code == 0, result.output
    assert 'Pre-caching waterways (WebMercatorQuad)' in result.output
    assert 'Pre-caching waterways (WorldCRS84Quad)' in result.output
    assert 'uncached' not in result.output

    p = MVTPostgresFilesystem(cache_def)
    assert p.get_tiles_from_cache(
        p.get_layer(), 'WebMercatorQuad', z=0, y=0, x=0
    )

    # Nothing is cached from disable_cache_at_z up
    cached = {
        path.parent.parent.name for path in p.cache_directory.rglob('*.pbf')
    }
    assert cached <= {'0', '1'}

    # A second run finds the cache filled and skips rendering
    result = CliRunner().invoke(mvt_cache, ['pre-cache', str(config_file)])
    assert result.exit_code == 0, result.output


def test_pre_cache_config_env(config_file):
    result = CliRunner().invoke(
        mvt_cache,
        ['pre-cache', '-c', 'waterways'],
        env={'PYGEOAPI_CONFIG': str(config_file)},
    )
    assert result.exit_code == 0, result.output
    assert 'Pre-caching waterways' in result.output


def test_pre_cache_no_config():
    result = CliRunner().invoke(
        mvt_cache, ['pre-cache'], env={'PYGEOAPI_CONFIG': None}
    )
    assert result.exit_code != 0
    assert "Missing argument 'CONFIG_FILE'" in result.output


def test_pre_cache_collection(config_file):
    result = CliRunner().invoke(
        mvt_cache, ['pre-cache', str(config_file), '--collection', 'waterways']
    )
    assert result.exit_code == 0, result.output
    assert 'Pre-caching waterways' in result.output


@pytest.mark.parametrize('collection', ['uncached', 'places', 'missing'])
def test_pre_cache_not_cached(config_file, collection):
    result = CliRunner().invoke(
        mvt_cache, ['pre-cache', str(config_file), '-c', collection]
    )

    assert result.exit_code != 0
    assert f'No MVT cache provider for collection(s): {collection}' in (
        result.output
    )


def test_pre_cache_none(tmp_path):
    path = tmp_path / 'pygeoapi.config.yml'
    path.write_text(yaml.safe_dump({'resources': {}}), encoding='utf-8')

    result = CliRunner().invoke(mvt_cache, ['pre-cache', str(path)])

    assert result.exit_code != 0
    assert 'No collections use an MVT cache provider' in result.output
