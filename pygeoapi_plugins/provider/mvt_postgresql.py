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
    ST_Area,
    ST_AsMVTGeom,
    ST_AsMVT,
    ST_SimplifyPreserveTopology,
    ST_Transform,
)

from sqlalchemy.sql import select
from sqlalchemy.orm import Session
from pygeofilter.parsers.ecql import parse as parse_ecql_text

from pygeoapi.provider.mvt_postgresql import MVTPostgreSQLProvider
from pygeoapi.provider.tile import ProviderTileNotFoundError
from pygeoapi.crs import get_srid

LOGGER = logging.getLogger(__name__)


class MVTPostgreSQLProvider_(MVTPostgreSQLProvider):
    """
    MVT PostgreSQL Provider
    Provider for serving tiles rendered on-the-fly from
    feature tables in PostgreSQL
    """

    db_search_path = ('public',)

    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi_plugins.provider.mvt_postgresql.MVTPostgreSQLProvider_
        """
        MVTPostgreSQLProvider.__init__(self, provider_def)

        self.layer = provider_def.get('layer', self.table)
        self.disable_at_z = provider_def.get('disable_at_z', 6)
        self.simplify_geometry = provider_def.get('simplify_geometry', True)

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
        # Validate and convert z, y, x to integers
        z, y, x = map(int, [z, y, x])  # type: ignore

        # Find the tiling scheme for the requested tileset
        [tileset_schema] = [
            schema
            for schema in self.get_tiling_schemes()
            if tileset == schema.tileMatrixSet
        ]
        if not self.is_in_limits(tileset_schema, z, x, y):
            LOGGER.warning(f'Tile {z}/{x}/{y} not found')
            raise ProviderTileNotFoundError

        # Build the MVT query
        LOGGER.debug(f'Querying {self.table} for MVT tile {z}/{x}/{y}')
        mvt_cte = self._get_mvt_cte(tileset_schema, z, y, x)
        mvt_query = select(ST_AsMVT(mvt_cte, self.layer))

        # Log the compiled query
        compiled_query = mvt_query.compile(
            self._engine, compile_kwargs={'literal_binds': True}
        )
        LOGGER.debug(f'Compiled query for {z}/{x}/{y}:\n{compiled_query}')

        # Execute the query
        with Session(self._engine) as session:
            result = session.execute(mvt_query).scalar()

        return bytes(result) if result else None

    def _get_mvt_cte(self, tileset_schema, z: int, y: int, x: int):
        """
        Gets tile MVT Query

        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index

        :returns: a SQLAlchemy CTE query that returns the MVT tile features
        """
        # Get the feature and geometry columns
        feature_id = getattr(self.table_model, self.id_field)
        geom_column = getattr(self.table_model, self.geom)

        # Get the tile envelope from the tiling scheme
        envelope = self.get_envelope(z, y, x, tileset_schema.tileMatrixSet)

        storage_srid = get_srid(self.storage_crs)
        out_srid = get_srid(tileset_schema.crs)
        same_srid = out_srid == storage_srid
        LOGGER.debug(f'out_srid: {out_srid}, storage_srid: {storage_srid}')
        # Store envelope in geometry column's SRID
        src_envelope = envelope if same_srid else ST_Transform(envelope, storage_srid)

        # Create filters
        filters = [geom_column.intersects(src_envelope)]
        if z < self.disable_at_z:
            # Create zoom-based filters
            filters2 = self._handle_z_filter(src_envelope, z)
            filters.extend(filters2)

        # Simplify geometry
        if self.simplify_geometry:
            # Adjust the tolerance based on zoom
            tolerance = 1 / 10 ** (z // 2)
            geom_column = ST_SimplifyPreserveTopology(geom_column, tolerance)

        # Transform geometry to tile CRS if needed
        if same_srid is False:
            geom_column = ST_Transform(geom_column, out_srid)

        # Build the query
        query = select(
            feature_id.label('id'),
            ST_AsMVTGeom(geom_column, envelope).label('mvtgeom'),
            *self.fields.values(),
        ).filter(*filters)

        # Apply tile limit if set
        if self.tile_limit:
            query = query.limit(self.tile_limit)

        # Return as CTE
        return query.cte('mvtcte').table_valued()

    def _handle_z_filter(self, src_envelope, z) -> list:
        """
        Handles zoom level filters for the MVT query.

        :param src_envelope: the tile envelope in the geometry column's SRID
        :param z: the zoom level of the tile

        :returns: a list of SQLAlchemy filter expressions to apply to the query
        """

        LOGGER.debug(f'Filtering features at zoom level {z}')
        filters = []
        if self.tile_threshold:
            # Filter features based on tile_threshold CQL expression
            tile_threshold = parse_ecql_text(self.tile_threshold.format(z=z or 1))
            filters.append(self._get_cql_filters(tile_threshold))

        else:
            # Filter features based on tile extents
            geom_column = getattr(self.table_model, self.geom)
            bbox_area = ST_Area(Box2D(geom_column)).label('bbox_area')
            min_pixel_area = ST_Area(src_envelope) / self.min_pixel**2
            filters.append(bbox_area > min_pixel_area)

        return filters
