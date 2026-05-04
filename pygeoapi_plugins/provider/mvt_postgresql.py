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
    Box2D,
    ST_AsMVTGeom,
    ST_AsMVT,
    ST_SimplifyVW,
    ST_Transform,
    ST_Area, 

)

from sqlalchemy.sql import select
from sqlalchemy.orm import Session
from pygeofilter.parsers.ecql import parse as parse_ecql_text

from pygeoapi.provider.mvt_postgresql import MVTPostgreSQLProvider
from pygeoapi.provider.tile import ProviderTileNotFoundError
from pygeoapi.crs import get_crs

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

        :returns: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
        """
        MVTPostgreSQLProvider.__init__(self, provider_def)

        self.layer = provider_def.get('layer', self.table)
        self.disable_at_z = provider_def.get('disable_at_z', 6)
        self.simplify_geometry = provider_def.get('simplify_geometry', False)

        # Apply filters to low zoom levels
        self.tile_threshold = provider_def.get('tile_threshold')
        self.min_pixel = provider_def.get('min_pixel', 512)

        # Maximum number of features in a tile
        self.tile_limit = provider_def.get('tile_limit', 0)

    def get_layer(self):
        """
        Use table name as layer name

        :returns: `str` of layer name
        """
        return self.layer

    def get_tiles(
        self, layer=None, tileset=None, z=None, y=None, x=None, *args, **kwargs
    ):
        """
        Gets tile

        :param layer: mvt tile layer
        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index

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

        mvt_cte = self._get_geom_cte(layer, tileset_schema, z, y, x)

        mvtquery = select(ST_AsMVT(mvt_cte, layer))

        LOGGER.error(mvtquery.compile(self._engine, compile_kwargs={"literal_binds": True}))
        with Session(self._engine) as session:
            result = bytes(session.execute(mvtquery).scalar()) or None

        return result

    def _get_geom_cte(
        self, layer=None, tileset_schema=None, z=None, y=None, x=None, *args, **kwargs
    ):
        feature_column = getattr(self.table_model, self.id_field)
        geom_column = getattr(self.table_model, self.geom)

        z_filtered = z < self.disable_at_z
        out_srid = get_crs(tileset_schema.crs).to_string()
        storage_srid = get_crs(self.storage_crs).to_string()
        envelope = self.get_envelope(z, y, x, tileset_schema.tileMatrixSet)

        if out_srid != storage_srid:
            src_envelope = ST_Transform(envelope, storage_srid)
            out_envelope = envelope
        else:
            src_envelope = envelope
            out_envelope = envelope

        filters = [
            geom_column.intersects(src_envelope)
        ]

        if self.tile_threshold and z_filtered:
            # Filter features based on tile_threshold CQL expression
            tile_threshold = parse_ecql_text(
                self.tile_threshold.format(z=z or 1)
            )
            filters.append(
                self._get_cql_filters(tile_threshold)
            )

        elif z_filtered:
            # Filter features based on tile extents
            LOGGER.debug(f'Filtering features at zoom level {z}')
            bbox_area = ST_Area(Box2D(geom_column)).label('bbox_area')

            min_pixel_area = ST_Area(envelope) / self.min_pixel ** 2
            filters.append(bbox_area > min_pixel_area)

        if self.simplify_geometry and z_filtered:
            geom_column = ST_SimplifyVW(geom_column, 1 / 10 ** (z + 1))

        if out_srid != storage_srid:
            geom_column = ST_Transform(geom_column, out_srid)

        geom_subquery = (
            select(feature_column.label('id'), geom_column.label('geom'))
            .filter(*filters)
            .subquery()
        )

        mvt_geom = ST_AsMVTGeom(
            geom_subquery.c.geom, out_envelope
        ).label('mvtgeom')

        selects = self.fields.values()

        return (
            select(geom_subquery.c.id, mvt_geom, *selects)
            .select_from(geom_subquery)
            .join(self.table_model, feature_column == geom_subquery.c.id)
            .cte('mvtcte')
            .table_valued()
        )
