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

import json
import logging

import os
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, query_expression
from geoalchemy2.functions import ST_AsGeoJSON

from pygeoapi.crs import get_transform_from_spec
from pygeoapi.provider.sql import PostgreSQLProvider

PSUEDO_COUNT_LIMIT = int(os.getenv('PSUEDO_COUNT_LIMIT', '5000000'))

LOGGER = logging.getLogger(__name__)

# Mapped attribute holding the geometry rendered by ST_AsGeoJSON
_GEOJSON = '_pygeoapi_geojson'


class PseudoPostgreSQLProvider(PostgreSQLProvider):
    """Generic provider for Postgresql based on psycopg2
    using sync approach and server side
    cursor (using support class DatabaseCursor)
    """

    def __init__(self, provider_def):
        """
        PostgreSQLProvider Class constructor

        :param provider_def: provider definitions from yml pygeoapi-config.
                             data,id_field, name set in parent class
                             data contains the connection information
                             for class DatabaseCursor

        :returns: pygeoapi_plugins.provider.postgres.PseudoPostgreSQLProvider
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

            if resulttype == 'hits':
                LOGGER.debug('No pseudo-count during hits')
                matched = results.count()
            else:
                try:
                    matched = self._get_pseudo_count(results)
                except (SQLAlchemyError, LookupError, TypeError) as err:
                    LOGGER.warning(f'Error during pseudo-count {err}')
                    matched = results.count()

            LOGGER.debug(f'Found {matched} result(s)')

            LOGGER.debug('Preparing response')
            response = {
                'type': 'FeatureCollection',
                'features': [],
                'numberMatched': matched,
                'numberReturned': 0,
            }

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
        This function calculates the pseudo-count by executing a SQL query on
        the PostGIS database. If the obtained pseudo-count is less than a
        predefined limit, the function falls back to using the precise count.

        :param results: Results object containing the query results

        :returns matched: `int` of the pseudo-count for the given results
        """
        LOGGER.debug('Getting pseudo-count')
        compiled = results.statement.compile(self._engine)

        # Read the planner's row estimate, binding filter values as params
        with self._engine.connect() as conn:
            plan = conn.exec_driver_sql(
                f'EXPLAIN (FORMAT JSON) {compiled}', compiled.params
            ).scalar_one()
        matched = plan[0]['Plan']['Plan Rows']

        if matched < PSUEDO_COUNT_LIMIT:
            LOGGER.debug('Using precise count')
            matched = results.count()

        return matched

    def __repr__(self):
        return f'<PseudoPostgreSQLProvider> {self.table}'

class PostgreSQLGeoJSONProvider(PostgreSQLProvider):
    """
    A provider for querying a PostgreSQL database, rendering
    geometries in the database with ST_AsGeoJSON
    """

    def __init__(self, provider_def: dict):
        """
        PostgreSQLGeoJSONProvider Class constructor

        :param provider_def: provider definitions from yml pygeoapi-config.

        :returns: pygeoapi.provider.sql.PostgreSQLGeoJSONProvider
        """
        super().__init__(provider_def)

        # Table models are shared, so only map the expression once
        if not hasattr(self.table_model, _GEOJSON):
            setattr(self.table_model, _GEOJSON, query_expression())

    def get(self, identifier, crs_transform_spec=None, **kwargs) -> dict:
        """
        Query the provider for a specific feature id, see
        `GenericSQLProvider.get` for parameters

        :returns: GeoJSON Feature
        """
        feature = super().get(identifier, **kwargs)

        id_column = getattr(self.table_model, self.id_field)
        with Session(self._engine) as session:
            geojson = (
                session.query(self._geojson)
                .filter(id_column == feature['id'])
                .scalar()
            )
        feature['geometry'] = json.loads(geojson) if geojson else None

        return feature

    @property
    def _geojson(self):
        geom_column = getattr(self.table_model, self.geom)
        return ST_AsGeoJSON(geom_column)

    def _select_properties_clause(self, select_properties, skip_geometry):
        # Load the geometry as GeoJSON instead of the geometry column
        clause = super()._select_properties_clause(select_properties, True)
        if skip_geometry:
            return clause

        return clause.with_expression(
            getattr(self.table_model, _GEOJSON), self._geojson
        )

    def _sqlalchemy_to_feature(self, item, crs_transform_out=None,
                               select_properties=[]):
        """
        Helper function to transform an SQLAlchemy result to a
        GeoJSON feature

        :param item: SQLAlchemy result
        :param crs_transform_out: CRS transformation (unused)
        :param select_properties: additional properties to filter on

        :returns: `dict` of GeoJSON feature
        """
        item_dict = item.__dict__
        geojson = item_dict.get(_GEOJSON)
        keys = select_properties or self.fields.keys()

        return {
            'type': 'Feature',
            'id': item_dict[self.id_field],
            'geometry': json.loads(geojson) if geojson else None,
            'properties': {
                key: item_dict[key] for key in keys if key in item_dict
            }
        }
