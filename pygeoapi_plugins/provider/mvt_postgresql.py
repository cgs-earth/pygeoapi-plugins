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

from geoalchemy2.functions import (
    ST_Transform,
    ST_AsMVTGeom,
    ST_AsMVT,
    ST_XMax,
    ST_XMin,
    ST_YMax,
    ST_YMin,
)

from sqlalchemy.sql import select
from sqlalchemy.orm import Session
from pygeofilter.parsers.ecql import parse as parse_ecql_text

from pygeoapi.provider.mvt_postgresql import MVTPostgreSQLProvider
from pygeoapi.provider.tile import ProviderTileNotFoundError
from pygeoapi.util import get_crs_from_uri

LOGGER = logging.getLogger(__name__)


class MVTPostgreSQLProvider_(MVTPostgreSQLProvider):
    """
    MVT PostgreSQL Provider
    Provider for serving tiles rendered on-the-fly from
    feature tables in PostgreSQL
    """

    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi.provider.MVT.MVTPostgreSQLProvider
        """
        MVTPostgreSQLProvider.__init__(self, provider_def)

        self.layer = provider_def.get('layer', self.table)
        self.disable_at_z = provider_def.get('disable_at_z', 6)

        # Apply filters to low zoom levels
        self.tile_threshold = provider_def.get('tile_threshold')
        self.min_pixel = provider_def.get('min_pixel', 256)

        # Maximum number of features in a tile
        self.tile_limit = provider_def.get('tile_limit', 0)

    def get_layer(self):
        """
        Use table name as layer name

        :returns: `str` of layer name
        """
        return self.layer

    def get_tiles(
        self, layer='default', tileset=None, z=None, y=None, x=None, format_=None
    ):
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

        [tileset_schema] = [
            schema
            for schema in self.get_tiling_schemes()
            if tileset == schema.tileMatrixSet
        ]
        if not self.is_in_limits(tileset_schema, z, x, y):
            LOGGER.warning(f'Tile {z}/{x}/{y} not found')
            raise ProviderTileNotFoundError

        LOGGER.debug(f'Querying {self.table} for MVT tile {z}/{x}/{y}')

        storage_srid = get_crs_from_uri(self.storage_crs).to_string()
        out_srid = get_crs_from_uri(tileset_schema.crs).to_string()
        envelope = self.get_envelope(z, y, x, tileset)
        envelope = select(
            ST_Transform(envelope, storage_srid).label('src'),
            ST_Transform(envelope, out_srid).label('out'),
        ).cte('envelope')

        geom_column = getattr(self.table_model, self.geom)
        bbox_area = (ST_XMax(geom_column) - ST_XMin(geom_column)) * (
            ST_YMax(geom_column) - ST_YMin(geom_column)
        )
        mvtgeom = ST_AsMVTGeom(
            ST_Transform(geom_column, out_srid),
            envelope.c.out,
        ).label('mvtgeom')

        geom_filter = geom_column.intersects(envelope.c.src)
        mvtrow = select(mvtgeom, *self.fields.values()).filter(geom_filter)

        if self.tile_threshold and z < self.disable_at_z:
            # Filter features based on tile_threshold CQL expression
            tile_threshold = parse_ecql_text(self.tile_threshold.format(z=z or 1))
            filter_ = self._get_cql_filters(tile_threshold)
            mvtrow = mvtrow.filter(filter_)

        elif z < self.disable_at_z:
            # Filter features based on tile extents
            LOGGER.debug(f'Filtering features at zoom level {z}')
            min_pixel = (
                ST_XMax(envelope.c.src) - ST_XMin(envelope.c.src)
            ) / self.min_pixel
            mvtrow = mvtrow.filter(bbox_area > (min_pixel * min_pixel))

        if self.tile_limit:
            # Maximimum number of features in a tile
            LOGGER.debug(f'Filtering features based on tile limit {self.tile_limit}')
            mvtrow = mvtrow.order_by(bbox_area.desc()).limit(self.tile_limit)

        mvtrow = mvtrow.cte('mvtrow').table_valued()
        mvtquery = select(ST_AsMVT(mvtrow, layer))

        with Session(self._engine) as session:
            result = bytes(session.execute(mvtquery).scalar()) or None

        return result
