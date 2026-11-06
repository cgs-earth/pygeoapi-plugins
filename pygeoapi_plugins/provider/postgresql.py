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

from geoalchemy2.functions import ST_AsGeoJSON
from pygeoapi.crs import get_transform_from_spec
from pygeoapi.provider.sql import PostgreSQLProvider
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, query_expression

from pygeoapi_plugins.formatter.json_ import GeoJSONGeometry

# Tables estimated below this many rows are counted precisely.
# PSUEDO_COUNT_LIMIT is the original, misspelled name of the variable.
PSEUDO_COUNT_LIMIT = int(
    os.getenv('PSEUDO_COUNT_LIMIT')
    or os.getenv('PSUEDO_COUNT_LIMIT')
    or '5000000'
)

LOGGER = logging.getLogger(__name__)

# Mapped attribute holding the geometry rendered by ST_AsGeoJSON
_GEOJSON = '_pygeoapi_geojson'

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
    A PostgreSQL provider that renders geometries as GeoJSON in the
    database with ST_AsGeoJSON, instead of converting them in Python
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

        # Table models are shared, so only map the expression once
        if not hasattr(self.table_model, _GEOJSON):
            setattr(self.table_model, _GEOJSON, query_expression())

    @property
    def _geojson(self):
        """
        SQL expression rendering the geometry column as GeoJSON

        :returns: `ST_AsGeoJSON` expression
        """
        geom_column = getattr(self.table_model, self.geom)
        return ST_AsGeoJSON(geom_column, self.max_decimal_digits)

    def _select_properties_clause(self, select_properties, skip_geometry):
        """
        Load the selected properties, and the geometry as GeoJSON in place
        of the geometry column

        :param select_properties: list of property names
        :param skip_geometry: bool of whether to skip geometry

        :returns: SQLAlchemy load options
        """
        clause = super()._select_properties_clause(select_properties, True)
        if skip_geometry:
            return clause

        return clause.with_expression(
            getattr(self.table_model, _GEOJSON), self._geojson
        )

    def _sqlalchemy_to_feature(
        self, item, crs_transform_out=None, select_properties=[]
    ):
        """
        Helper function to transform an SQLAlchemy result to a
        GeoJSON feature

        :param item: SQLAlchemy result
        :param crs_transform_out: CRS transformation (unused)
        :param select_properties: additional properties to filter on

        :returns: `dict` of GeoJSON feature
        """
        item_dict = item.__dict__
        if _GEOJSON not in item_dict:
            # Items loaded without the GeoJSON expression, such as by
            # `get`, still hold the geometry column
            return super()._sqlalchemy_to_feature(
                item, crs_transform_out, select_properties
            )

        geojson = item_dict[_GEOJSON]
        keys = select_properties or self.fields.keys()

        return {
            'type': 'Feature',
            'id': item_dict[self.id_field],
            'geometry': GeoJSONGeometry(geojson),
            'properties': {
                key: item_dict[key] for key in keys if key in item_dict
            },
        }
