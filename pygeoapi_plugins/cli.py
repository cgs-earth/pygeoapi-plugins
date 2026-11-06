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

"""pygeoapi CLI commands, run with `pygeoapi plugins`"""

import importlib
import logging

import click
from pygeoapi.plugin import PLUGINS, load_plugin
from pygeoapi.util import filter_dict_by_key_value, yaml_load

from pygeoapi_plugins.provider.mvt_cache import MVTCacheProvider

LOGGER = logging.getLogger(__name__)


def _provider_class(name: str) -> type | None:
    """
    Import the class of a provider, by its plugin name or dotted path

    :param name: provider `name` from the pygeoapi configuration

    :returns: provider class, or `None` if it cannot be imported
    """
    path = PLUGINS['provider'].get(name, name)
    module, _, class_ = path.rpartition('.')
    try:
        return getattr(importlib.import_module(module), class_)
    except (ImportError, AttributeError, ValueError):
        return None


def get_cache_providers(config: dict) -> dict:
    """
    Find the collections served by an MVT cache provider

    :param config: pygeoapi configuration

    :returns: `dict` of collection name to tile provider definition
    """
    collections = filter_dict_by_key_value(
        config.get('resources', {}), 'type', 'collection'
    )

    providers = {}
    for name, collection in collections.items():
        for provider_def in collection.get('providers', []):
            if provider_def.get('type') != 'tile':
                continue

            cls = _provider_class(provider_def.get('name', ''))
            if cls and issubclass(cls, MVTCacheProvider):
                providers[name] = provider_def

    return providers


@click.group('mvt-cache')
def mvt_cache():
    """Manage MVT tile caches"""


@mvt_cache.command('pre-cache')
@click.argument(
    'config_file',
    type=click.File(encoding='utf-8'),
    envvar='PYGEOAPI_CONFIG',
)
@click.option(
    '--collection',
    '-c',
    'collections',
    multiple=True,
    help='Collection to pre-cache (repeatable); default is all cached ones',
)
def pre_cache(config_file, collections):
    """
    Render and cache tiles below each provider's disable_cache_at_z

    CONFIG_FILE defaults to the PYGEOAPI_CONFIG environment variable.
    Collections whose cache already has their first tile are skipped.
    """
    config = yaml_load(config_file)
    providers = get_cache_providers(config)

    if collections:
        unknown = sorted(set(collections) - set(providers))
        if unknown:
            names = ', '.join(unknown)
            raise click.ClickException(
                f'No MVT cache provider for collection(s): {names}'
            )
        providers = {name: providers[name] for name in collections}

    if not providers:
        raise click.ClickException('No collections use an MVT cache provider')

    for name, provider_def in providers.items():
        provider = load_plugin('provider', provider_def)
        for schema in provider.get_tiling_schemes():
            click.echo(f'Pre-caching {name} ({schema.tileMatrixSet})')
            provider.run_pre_cache(schema)

    click.echo('Done')
