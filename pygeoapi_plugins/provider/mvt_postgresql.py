# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
#          
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

from geoalchemy2.functions import (ST_Transform, ST_AsMVTGeom,
                                   ST_AsMVT, ST_CurveToLine,
                                   ST_XMax, ST_XMin, ST_YMax, ST_YMin)

from sqlalchemy.sql import select, desc
from sqlalchemy.orm import Session

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

        self.max_items_per_tile = provider_def.get('max_items_per_tile', 0)
        self.disable_at_z = provider_def.get('disable_at_z', 6)
        self.layer = provider_def.get('layer', self.table)


    def get_layer(self):
        """
        Use table name as layer name

        :returns: `str` of layer name
        """
        return self.layer

    def get_tiles(self, layer='default', tileset=None,
                  z=None, y=None, x=None, format_=None):
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
            schema for schema in self.get_tiling_schemes()
            if tileset == schema.tileMatrixSet
        ]
        if not self.is_in_limits(tileset_schema, z, x, y):
            LOGGER.warning(f'Tile {z}/{x}/{y} not found')
            return ProviderTileNotFoundError

        storage_srid = get_crs_from_uri(self.storage_crs).to_string()
        out_srid = get_crs_from_uri(tileset_schema.crs).to_string()
        envelope = self.get_envelope(z, y, x, tileset)

        geom_column = getattr(self.table_model, self.geom)
        geom_filter = geom_column.intersects(
            ST_Transform(envelope, storage_srid)
        )

        mvtgeom = (
            ST_AsMVTGeom(
                ST_Transform(ST_CurveToLine(geom_column), out_srid),
                ST_Transform(envelope, out_srid))
            .label('mvtgeom')
        )

        mvtrow = (
            select(mvtgeom, *self.fields.values())
            .filter(geom_filter)
        )

        if self.max_items_per_tile and z < self.disable_at_z:
            bbox_area = (
                (ST_XMax(geom_column) - ST_XMin(geom_column)) *
                (ST_YMax(geom_column) - ST_YMin(geom_column))
            ).label('bbox_area')

            mvtrow = (
                mvtrow
                .order_by(desc(bbox_area))
                .limit(self.max_items_per_tile)
            )

        mvtquery = select(
            ST_AsMVT(mvtrow.cte('mvtrow').table_valued(), layer)
        )

        with Session(self._engine) as session:
            result = bytes(
                session.execute(mvtquery).scalar()
            ) or None

        return result
