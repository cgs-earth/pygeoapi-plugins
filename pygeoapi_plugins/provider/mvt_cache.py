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

import logging

import functools
import multiprocessing as mp
from pathlib import Path
from sqlalchemy import (
    Table,
    MetaData,
    String,
    Column,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    Index,
)
from sqlalchemy.sql import select
from sqlalchemy.orm import Session
from time import sleep


from pygeoapi_plugins.provider.mvt_postgresql import MVTPostgreSQLProvider_


LOGGER = logging.getLogger(__name__)


class MVTCacheProvider(MVTPostgreSQLProvider_):
    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition
        """
        super().__init__(provider_def)

        self.disable_cache_at_z = provider_def.get('disable_cache_at_z', 6)

    def get_tiles(self, layer=None, tileset=None, z=None, y=None, x=None, format_=None):
        """
        Gets tile

        :param layer: mvt tile layer
        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index
        :param format_: tile format

        :returns: an encoded mvt tile
        """
        z, y, x = map(int, [z, y, x])

        if z < self.disable_cache_at_z:
            LOGGER.debug('Checking for cached tile')
            tile = self.get_tiles_from_cache(layer, tileset, z, y, x)

            if tile is not None:
                LOGGER.debug('Returning cached tile')
                return tile

        LOGGER.debug('Tile not found in cache, rendering tile')
        tile = MVTPostgreSQLProvider_.get_tiles(self, layer, tileset, z, y, x, format_)

        if z < self.disable_cache_at_z and tile is not None:
            LOGGER.debug('Caching tile')
            assert self.save_tiles_to_cache(tile, layer, tileset, z, y, x)

        return tile

    def run_pre_cache(self, schema=None):
        """
        Run pre-cache to generate tiles for zoom levels
        """
        zoom_level = min(self.disable_cache_at_z, len(schema.tileMatrices))
        layers = [
            (self.get_layer(), schema.tileMatrixSet, z, y, x)
            for z in range(zoom_level)
            for y in range(schema.tileMatrices[z]['matrixHeight'])
            for x in range(schema.tileMatrices[z]['matrixWidth'])
        ]

        for layer in layers:
            while len(mp.active_children()) == 2:
                sleep(0.1)

            p = mp.Process(target=self.get_tiles, args=layer)
            p.start()

    def get_tiles_from_cache(
        self,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        """
        Gets tile from cache

        :param layer: mvt tile layer
        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index

        :returns: an encoded mvt tile or None
        """
        raise NotImplementedError()

    def save_tiles_to_cache(
        self,
        tile,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        """
        Saves tile to cache

        :param tile: an encoded mvt tile
        :param layer: mvt tile layer
        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index
        """
        raise NotImplementedError()


class MVTPostgresFilesystem(MVTCacheProvider):
    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi_plugins.provider.mvt_cache.MVTPostgresFilesystem
        """
        super().__init__(provider_def)

        self.cache_directory = Path(
            provider_def.get('cache_directory', '/tmp/mvt_cache')
        )

        if provider_def.get('pre_cache', False):
            for schema in self.get_tiling_schemes():
                self.run_pre_cache(schema)

    def get_tiles_from_cache(
        self,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        tile_ = self._get_tile_path(layer, tileset, z, y, x)

        if tile_.exists() and tile_.is_file():
            with open(tile_, 'rb') as fh:
                return fh.read()

    def save_tiles_to_cache(
        self,
        tile,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        tile_ = self._get_tile_path(layer, tileset, z, y, x)

        if tile and isinstance(tile, bytes):
            tile_.parent.mkdir(parents=True, exist_ok=True)

            LOGGER.debug(f'Saving tile to {tile_}')
            with open(tile_, 'wb') as fh:
                try:
                    fh.write(tile)
                except TypeError as e:
                    LOGGER.error(f'Error while writing tile: {e}')
                    return False

        return True

    def _get_tile_path(self, layer, tileset, z, y, x):
        z, y, x = map(str, [z, y, x])
        return (self.cache_directory / layer / tileset / z / y / x).with_suffix('.pbf')


class MVTPostgresCache(MVTCacheProvider):
    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi_plugins.provider.mvt_cache.MVTPostgresCache
        """
        super().__init__(provider_def)

        self.cache_table = provider_def.get('mvt_table', self.table + '_mvt')
        self.cache_model = create_cache_table(
            self.cache_table,
            self.db_search_path,
            self._engine,
            provider_def.get('force_create', False),
        )

        if provider_def.get('pre_cache', False):
            for schema in self.get_tiling_schemes():
                self.run_pre_cache(schema)

    def get_tiles_from_cache(
        self,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        x, y, z = map(int, [x, y, z])

        query = select(self.cache_model.c.tile).where(
            self.cache_model.c.layer == layer,
            self.cache_model.c.tilematrixset == tileset,
            self.cache_model.c.z == z,
            self.cache_model.c.x == x,
            self.cache_model.c.y == y,
        )
        with Session(self._engine) as session:
            result = session.execute(query).scalar()
            if result:
                LOGGER.debug(f'Found cached tile {tileset}/{z}/{x}/{y}')
                return bytes(result)

    def save_tiles_to_cache(
        self,
        tile,
        layer='default',
        tileset=None,
        z=None,
        y=None,
        x=None,
    ):
        if tile and isinstance(tile, bytes):
            query = self.cache_model.insert().values(
                layer=layer, tilematrixset=tileset, z=z, y=y, x=x, tile=tile
            )
            with Session(self._engine) as session:
                try:
                    session.execute(query)
                    session.commit()
                    LOGGER.debug(f'Saved tile {tileset}/{z}/{x}/{y} to cache')
                except Exception as e:
                    LOGGER.error(f'Error while saving tile to cache: {e}')
                    return False

        return True


@functools.cache
def create_cache_table(
    table_name: str, db_search_path: tuple[str], engine, force_create: bool = False
):
    """Create cache table if it does not exist"""
    metadata = MetaData(schema=db_search_path[0])

    table = Table(
        table_name,
        metadata,
        Column('layer', String(50), nullable=False),
        Column('tilematrixset', String(50), nullable=False),
        Column('z', Integer, nullable=False),
        Column('x', Integer, nullable=False),
        Column('y', Integer, nullable=False),
        Column('tile', LargeBinary, nullable=False),
        # composite PK enforces uniqueness
        PrimaryKeyConstraint('layer', 'tilematrixset', 'z', 'x', 'y'),
        # covering index for fast lookups by key
        Index(f'idx_{table_name}_lookup', 'layer', 'tilematrixset', 'z', 'x', 'y'),
    )

    if force_create:
        metadata.drop_all(engine, [table], checkfirst=True)

    metadata.create_all(engine, [table], checkfirst=True)

    return table
