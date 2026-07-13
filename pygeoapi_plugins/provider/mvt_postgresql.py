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

from copy import deepcopy
from enum import Enum
from geoalchemy2.functions import (
    Box2D,
    ST_Area,
    ST_AsMVTGeom,
    ST_AsMVT,
    ST_Extent,
    ST_Simplify,
    ST_SimplifyVW,
    ST_SimplifyPreserveTopology,
    ST_SnapToGrid,
    ST_Transform,
)

from sqlalchemy.sql import select, func
from sqlalchemy.orm import Session
from pygeofilter.parsers.ecql import parse as parse_ecql_text

from pygeoapi.provider.mvt_postgresql import MVTPostgreSQLProvider
from pygeoapi.provider.tile import ProviderTileNotFoundError
from pygeoapi.provider.sql import PostgreSQLProvider
from pygeoapi.crs import get_srid

from pygeoapi.util import url_join, human_size

LOGGER = logging.getLogger(__name__)


class SimplifyMethods(Enum):
    """Enum for geometry simplification methods"""

    ST_Simplify = ST_Simplify
    ST_SimplifyPreserveTopology = ST_SimplifyPreserveTopology
    ST_SimplifyVW = ST_SimplifyVW
    ST_SnapToGrid = ST_SnapToGrid

    def __call__(self, *args, **kwargs):
        # Extract the function out of the tuple value and execute it
        return self.value(*args, **kwargs)


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
        try:
            simplify_method = provider_def.get(
                'simplify_method', 'ST_SimplifyPreserveTopology'
            )
            if self.simplify_geometry:
                self.simplify_method = SimplifyMethods[simplify_method]
        except KeyError:
            msg = (
                'Incorrect simplification method provided. Must be one of: '
                + ', '.join(SimplifyMethods._member_names_)
            )
            LOGGER.error(msg)
            raise RuntimeError(msg)

        # Apply filters to low zoom levels
        self.tile_threshold = provider_def.get('tile_threshold')
        # Filter based on on features bigger than a grid
        # within the tiles of dimensions `min_pixel` x `min_pixel`.
        # The larger the value, the smaller a feature needs to be
        # for it to be rendered as a pixel in the tile.
        self.min_pixel = provider_def.get('min_pixel', 512)

        # Maximum number of features in a tile
        self.tile_limit = provider_def.get('tile_limit', 0)
        geom_column = getattr(self.table_model, self.geom)
        with Session(self._engine) as session:
            (geom_type,) = session.query(
                func.ST_GeometryType(geom_column).label('geom_type')
            ).first()  # type: ignore
            self.tile_limit_order = (
                func.random() if 'point' in geom_type.lower()
                else ST_Area(Box2D(geom_column)).desc()
            )
        # Maximum tile size (in MB)
        self.tile_size = provider_def.get('tile_size', 0) * 1024 * 1024

        self.min_zoom = provider_def['options']['zoom']['min']
        self.max_zoom = provider_def['options']['zoom']['max']

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

        # Get the tile envelope from the tiling scheme
        LOGGER.debug(f'Querying {self.table} for MVT tile {z}/{x}/{y}')
        envelope = self.get_envelope(z, y, x, tileset_schema.tileMatrixSet)
        envelope_srid = get_srid(tileset_schema.crs)
        mvt_cte = self._get_mvt_cte(
            envelope, envelope_srid, z, self.tile_limit)
        mvt_query = select(ST_AsMVT(mvt_cte, self.layer))

        # Log the compiled query
        compiled_query = mvt_query.compile(
            self._engine, compile_kwargs={'literal_binds': True}
        )
        LOGGER.debug(f'Compiled query for {z}/{x}/{y}:\n{compiled_query}')

        # Execute the query
        with Session(self._engine) as session:
            result = session.execute(mvt_query).scalar()
            if result is None:
                return

            result_bytes = bytes(result)
            result_size = len(result_bytes)
            if self.tile_size and self.tile_size < result_size:
                LOGGER.debug(
                    'Tile exceeds configured size\n'
                    f'Provider maximum size: {human_size(self.tile_size)}\n'
                    f'Tile size: {human_size(result_size)}'
                )

                matched = session.query(func.count(mvt_cte)).scalar()
                new_limit = int(matched * (self.tile_size / result_size))

                new_mvt_cte = self._get_mvt_cte(
                    envelope, envelope_srid, z, new_limit)

                new_mvt_query = select(ST_AsMVT(new_mvt_cte, self.layer))
                new_result = session.execute(new_mvt_query).scalar()
                if new_result is None:
                    return

                result_bytes = bytes(new_result)
                result_size = len(result_bytes)

        LOGGER.debug(f'Returning tile of size: {human_size(result_size)}')
        return result_bytes

    def get_vendor_metadata(
        self,
        dataset,
        server_url,
        layer=None,
        tileset=None,
        title=None,
        description=None,
        keywords=None,
        **kwargs,
    ):
        """Create TileJSON representation"""
        service_url = url_join(
            server_url, f'collections/{dataset}/tiles/{tileset}'
        )
        tiles_url = url_join(
            service_url, '{tileMatrix}/{tileRow}/{tileCol}?f=mvt'
        )
        tilejson_url = url_join(service_url, 'metadata?f=tilejson')

        metadata = dict()
        metadata['tilejson'] = '3.0.0'
        metadata['name'] = title
        metadata['attribution'] = None
        metadata['description'] = description
        metadata['tiles'] = tiles_url
        metadata['tilejson_url'] = tilejson_url
        metadata['minzoom'] = self.min_zoom
        metadata['maxzoom'] = self.max_zoom

        geom_column = getattr(self.table_model, self.geom)
        stmt = select(ST_Extent(geom_column))
        with Session(self._engine) as session:
            extent = (
                str(session.execute(stmt).scalar())
                .removeprefix('BOX(')
                .removesuffix(')')
                .replace(',', ' ')
                .split()
            )
            minx, miny, maxx, maxy = map(float, extent)
            metadata['bounds'] = f'{minx}, {miny}, {maxx}, {maxy}'
            metadata['center'] = f'{maxx - minx}, {maxy - miny}'

        _fields = deepcopy(self._fields)
        self._fields = {}
        metadata['vector_layers'] = [
            {
                'id': layer,
                'description': '',
                'minzoom': self.min_zoom,
                'maxzoom': self.max_zoom,
                'fields': {
                    c: v['type']
                    for c, v in PostgreSQLProvider.get_fields(self).items()
                },
            }
        ]
        self._fields = _fields

        return metadata

    def get_metadata(self, *args, **kwargs):
        """Create Tile Metadata"""
        metadata = MVTPostgreSQLProvider.get_metadata(self, *args, **kwargs)
        if kwargs.get('metadata_format') == 'html':
            metadata['metadata'] = self.get_vendor_metadata(*args, **kwargs)
            metadata['tilejson_url'] = metadata['metadata']['tilejson_url']

        return metadata

    def _get_mvt_cte(self, envelope, envelope_srid, z, tile_limit):
        """
        Gets tile MVT Query

        :param envelope: the tile envelope
        :param envelope_srid: the SRID of the tile envelope
        :param z: the zoom level
        :param tile_limit: limit tiles based on number of features

        :returns: a SQLAlchemy CTE query that returns the MVT tile features
        """
        # Get the feature and geometry columns
        feature_id = getattr(self.table_model, self.id_field)
        geom_column = getattr(self.table_model, self.geom)

        # Store envelope in geometry column's SRID
        storage_srid = get_srid(self.storage_crs)
        same_srid = envelope_srid == storage_srid
        LOGGER.debug(
            f'out_srid: {envelope_srid}, storage_srid: {storage_srid}'
        )
        src_envelope = (
            envelope if same_srid else ST_Transform(envelope, storage_srid)
        )

        # Create filters
        filters = [geom_column.intersects(src_envelope)]
        if z < self.disable_at_z:
            filters2 = self._handle_z_filter(src_envelope, z)
            filters.extend(filters2)

        # Simplify geometry
        if self.simplify_geometry:
            tolerance = 1 / 10 ** (z // 2)
            tolerance = min(tolerance, 0.1)
            geom_column = self.simplify_method(geom_column, tolerance)

        # Transform geometry to tile CRS if needed
        if same_srid is False:
            geom_column = ST_Transform(geom_column, envelope_srid)

        # Build the query
        query = select(
            feature_id.label('id'),
            ST_AsMVTGeom(geom_column, envelope).label('mvtgeom'),
            *self.fields.values(),
        ).filter(*filters)

        # Apply tile limit if set
        if tile_limit:
            query = query.order_by(self.tile_limit_order).limit(tile_limit)

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
            tile_threshold = parse_ecql_text(
                self.tile_threshold.format(z=z or 1)
            )
            filters.append(self._get_cql_filters(tile_threshold))

        else:
            # Filter features based on tile extents
            geom_column = getattr(self.table_model, self.geom)
            bbox_area = ST_Area(Box2D(geom_column)).label('bbox_area')
            min_pixel_area = ST_Area(src_envelope) / self.min_pixel**2
            filters.append(bbox_area > min_pixel_area)

        return filters
