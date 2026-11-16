# =================================================================
#
# Authors: Jorge Samuel Mendes de Jesus <jorge.dejesus@protonmail.com>
#          Tom Kralidis <tomkralidis@gmail.com>
#          Mary Bucknell <mbucknell@usgs.gov>
#          John A Stevenson <jostev@bgs.ac.uk>
#          Colin Blackburn <colb@bgs.ac.uk>
#          Francesco Bartoli <xbartolone@gmail.com>
#
# Copyright (c) 2018 Jorge Samuel Mendes de Jesus
# Copyright (c) 2023 Tom Kralidis
# Copyright (c) 2022 John A Stevenson and Colin Blackburn
# Copyright (c) 2023 Francesco Bartoli
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

import os
from sqlalchemy import Text, cast, func, literal, literal_column, null, select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session
from geoalchemy2 import Geometry
from geoalchemy2.functions import (
    ST_AsGeoJSON,
    ST_FlipCoordinates,
    ST_Transform,
)

from pygeoapi.crs import get_crs, get_srid, get_transform_from_spec
from pygeoapi.provider.base import ProviderQueryError
from pygeoapi.provider.sql import PostgreSQLProvider

from pygeoapi_plugins.formatter.json_ import GeoJSONFeature

# Tables estimated below this many rows are counted precisely.
# PSUEDO_COUNT_LIMIT is the original, misspelled name of the variable.
PSEUDO_COUNT_LIMIT = int(
    os.getenv('PSEUDO_COUNT_LIMIT')
    or os.getenv('PSUEDO_COUNT_LIMIT')
    or '5000000'
)

LOGGER = logging.getLogger(__name__)

# Second copy of the id column, which ST_AsGeoJSON(record) moves out of
# properties into the feature id, so the id stays in properties as well
_ID = '_pygeoapi_id'

# ST_AsGeoJSON's own default number of decimal places
_MAX_DECIMAL_DIGITS = 9


class PseudoPostgreSQLProvider(PostgreSQLProvider):
    """
    A PostgreSQL provider that estimates `numberMatched` for large
    queries from the query planner, instead of counting every row
    """

    def __init__(self, provider_def):
        """
        PseudoPostgreSQLProvider Class constructor

        :param provider_def: provider definitions from yml pygeoapi-config.
                             data, id_field, name set in parent class
                             data contains the connection information

        :returns: pygeoapi_plugins.provider.postgresql.PseudoPostgreSQLProvider
        """
        LOGGER.debug('Initialising Pseudo-count PostgreSQL provider.')
        super().__init__(provider_def)

    def query(
        self,
        offset=0,
        limit=10,
        resulttype='results',
        bbox=[],
        datetime_=None,
        properties=[],
        sortby=[],
        select_properties=[],
        skip_geometry=False,
        q=None,
        filterq=None,
        crs_transform_spec=None,
        **kwargs,
    ):
        """
        Query Postgis for all the content.
        e,g: http://localhost:5000/collections/hotosm_bdi_waterways/items?
        limit=1&resulttype=results

        :param offset: starting record to return (default 0)
        :param limit: number of records to return (default 10)
        :param resulttype: return results or hit limit (default results)
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param datetime_: temporal (datestamp or extent)
        :param properties: list of tuples (name, value)
        :param sortby: list of dicts (property, order)
        :param select_properties: list of property names
        :param skip_geometry: bool of whether to skip geometry (default False)
        :param q: full-text search term(s)
        :param filterq: CQL query as text string
        :param crs_transform_spec: `CrsTransformSpec` instance, optional

        :returns: GeoJSON FeatureCollection
        """

        LOGGER.debug('Preparing filters')
        # Filter helpers return True when there is nothing to filter
        filters = [
            f
            for f in (
                self._get_property_filters(properties),
                self._get_cql_filters(filterq),
                self._get_bbox_filter(bbox),
                self._get_datetime_filter(datetime_),
            )
            if f is not True
        ]
        order_by_clauses = self._get_order_by_clauses(sortby, self.table_model)
        selected_properties = self._select_properties_clause(
            select_properties, skip_geometry
        )

        LOGGER.debug('Querying PostGIS')
        # Execute query within self-closing database Session context
        with Session(self._engine) as session:
            results = (
                session.query(self.table_model)
                .filter(*filters)
                .options(selected_properties)
            )

            LOGGER.debug('Preparing response')
            response = {
                'type': 'FeatureCollection',
                'features': [],
                'numberReturned': 0,
            }

            if resulttype == 'hits':
                LOGGER.debug('No pseudo-count during hits')
                response['numberMatched'] = results.count()
            elif self.count:
                try:
                    response['numberMatched'] = self._get_pseudo_count(results)
                except (SQLAlchemyError, LookupError, TypeError) as err:
                    LOGGER.warning(f'Error during pseudo-count {err}')
                    response['numberMatched'] = results.count()
            else:
                LOGGER.debug('Count disabled')

            LOGGER.debug(f'Found {response.get("numberMatched")} result(s)')

            if resulttype == 'hits' or not results:
                return response

            crs_transform_out = (
                get_transform_from_spec(crs_transform_spec)
                if crs_transform_spec
                else None
            )

            for item in (
                results.order_by(*order_by_clauses).offset(offset).limit(limit)
            ):
                response['numberReturned'] += 1
                response['features'].append(
                    self._sqlalchemy_to_feature(
                        item, crs_transform_out, select_properties
                    )
                )

        return response

    def _get_pseudo_count(self, results):
        """
        Estimate the number of matching rows from the query planner, using
        `EXPLAIN`. If the estimate is below `PSEUDO_COUNT_LIMIT`, the precise
        count is returned instead.

        :param results: SQLAlchemy `Query` of the filtered table

        :returns matched: `int` of the estimated or precise count
        """
        LOGGER.debug('Getting pseudo-count')
        compiled = results.statement.compile(self._engine)

        # Read the planner's row estimate, binding filter values as params
        with self._engine.connect() as conn:
            plan = conn.exec_driver_sql(
                f'EXPLAIN (FORMAT JSON) {compiled}', compiled.params
            ).scalar_one()
        matched = plan[0]['Plan']['Plan Rows']

        if matched < PSEUDO_COUNT_LIMIT:
            LOGGER.debug('Using precise count')
            matched = results.count()

        return matched

    def __repr__(self):
        return f'<PseudoPostgreSQLProvider> {self.table}'


class PostgreSQLGeoJSONProvider(PostgreSQLProvider):
    """
    A PostgreSQL provider that renders features as GeoJSON in the
    database with ST_AsGeoJSON, instead of converting them in Python.
    Requires PostGIS 3.5 or later.
    """

    def __init__(self, provider_def: dict):
        """
        PostgreSQLGeoJSONProvider Class constructor

        :param provider_def: provider definitions from yml pygeoapi-config.

        :returns: pygeoapi_plugins.provider.postgresql.PostgreSQLGeoJSONProvider
        """
        super().__init__(provider_def)

        # Decimal places ST_AsGeoJSON rounds coordinates to
        self.max_decimal_digits = int(
            provider_def.get('max_decimal_digits', _MAX_DECIMAL_DIGITS)
        )
        if self.max_decimal_digits < 0:
            raise ValueError('max_decimal_digits must not be negative')

    def query(
        self,
        offset=0,
        limit=10,
        resulttype='results',
        bbox=[],
        datetime_=None,
        properties=[],
        sortby=[],
        select_properties=[],
        skip_geometry=False,
        q=None,
        filterq=None,
        crs_transform_spec=None,
        **kwargs,
    ):
        """
        Query PostGIS, which writes each feature as GeoJSON text with
        `ST_AsGeoJSON(record)`. PostGIS also reprojects the geometry for a
        CRS transform, and writes a null geometry when it is skipped.

        :param offset: starting record to return (default 0)
        :param limit: number of records to return (default 10)
        :param resulttype: return results or hit limit (default results)
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param datetime_: temporal (datestamp or extent)
        :param properties: list of tuples (name, value)
        :param sortby: list of dicts (property, order)
        :param select_properties: list of property names
        :param skip_geometry: bool of whether to skip geometry (default False)
        :param q: full-text search term(s)
        :param filterq: CQL query as text string
        :param crs_transform_spec: `CrsTransformSpec` instance, optional

        :returns: GeoJSON FeatureCollection
        """
        LOGGER.debug('Preparing filters')
        # Filter helpers return True when there is nothing to filter
        filters = [
            f
            for f in (
                self._get_property_filters(properties),
                self._get_cql_filters(filterq),
                self._get_bbox_filter(bbox),
                self._get_datetime_filter(datetime_),
            )
            if f is not True
        ]
        order_by_clauses = self._get_order_by_clauses(sortby, self.table_model)

        response = {
            'type': 'FeatureCollection',
            'features': [],
            'numberReturned': 0,
        }

        with self._engine.connect() as conn:
            if self.count or resulttype == 'hits':
                count = select(func.count()).select_from(self.table_model)
                matched = conn.execute(count.where(*filters)).scalar_one()
                response['numberMatched'] = matched
                LOGGER.debug(f'Found {matched} result(s)')
            if resulttype == 'hits':
                return response

            geometry = self._geometry(skip_geometry, crs_transform_spec)

            id_column = getattr(self.table_model, self.id_field)
            table = (
                select(
                    id_column.label(_ID),
                    *self._columns(select_properties),
                    geometry.label(self.geom),
                )
                .where(*filters)
                .order_by(*order_by_clauses)
                .offset(offset)
                .limit(limit)
                .subquery('t')
            )
            statement = select(
                ST_AsGeoJSON(
                    literal_column('t.*'),
                    self.geom,
                    self.max_decimal_digits,
                    False,
                    _ID,
                )
            ).select_from(table)

            LOGGER.debug('Querying PostGIS')
            try:
                rows = conn.execute(statement)
            except ProgrammingError as err:
                # 42883 is undefined_function: before PostGIS 3.5,
                # ST_AsGeoJSON(record) has no id_column argument
                if getattr(err.orig, 'pgcode', None) == '42883':
                    msg = 'PostgreSQLGeoJSONProvider requires PostGIS 3.5+'
                    LOGGER.error(f'{msg}: {err.orig}')
                    raise ProviderQueryError(user_msg=msg) from err
                raise

            response['features'] = [GeoJSONFeature(row[0]) for row in rows]

        response['numberReturned'] = len(response['features'])
        return response

    def _columns(self, select_properties):
        """
        Property columns for the feature, chosen as the core
        `_select_properties_clause` chooses them

        :param select_properties: list of property names

        :returns: `list` of mapped columns
        """
        if select_properties:
            names = sorted(set(select_properties), key=select_properties.index)
        else:
            names = list(self.fields.keys())
        if self.properties and names:
            names = list(self.properties)

        table_columns = self.table_model.__table__.columns
        return [
            getattr(self.table_model, name)
            for name in names
            if name in table_columns
        ]

    def _geometry(self, skip_geometry=False, crs_transform_spec=None):
        """
        Geometry column for the feature, reprojected by PostGIS when there
        is a CRS transform. Coordinates are flipped wherever the core
        provider's pyproj transform reads or writes them northing first.

        :param skip_geometry: `bool`, optional
        :param crs_transform_spec: `CrsTransformSpec` instance, optional

        :returns: SQL expression of the geometry
        """
        if skip_geometry:
            return cast(null(), Geometry)

        geom = getattr(self.table_model, self.geom)
        if crs_transform_spec is None:
            return geom

        source = get_crs(crs_transform_spec.source_crs_uri)
        target = get_crs(crs_transform_spec.target_crs_uri)
        always_xy = crs_transform_spec.always_xy

        if not always_xy and _northing_first(source):
            geom = ST_FlipCoordinates(geom)

        srid = get_srid(target)
        to_crs = srid if srid else cast(literal(target.to_wkt()), Text)
        geom = ST_Transform(geom, to_crs)

        if not always_xy and _northing_first(target):
            geom = ST_FlipCoordinates(geom)

        return geom


def _northing_first(crs):
    """
    Whether a CRS lists its northing (or southing) axis first, as
    EPSG:4326 does

    :param crs: `pyproj.CRS` instance

    :returns: `bool`
    """
    axes = crs.axis_info
    return bool(axes) and axes[0].direction.lower() in ('north', 'south')
