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
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from pygeoapi.provider.postgresql import PostgreSQLProvider
from pygeoapi.provider.base import ProviderQueryError

PSUEDO_COUNT_LIMIT = os.getenv('PSUEDO_COUNT_LIMIT', 5000000)
COUNT_FUNCTION = """
DROP FUNCTION IF EXISTS count_estimate;
CREATE FUNCTION count_estimate(query text)
  RETURNS integer
  LANGUAGE plpgsql AS
$func$
DECLARE
    rec   record;
    rows  integer;
BEGIN
    FOR rec IN EXECUTE 'EXPLAIN ' || query LOOP
        rows := substring(rec."QUERY PLAN" FROM ' rows=([[:digit:]]+)');
        EXIT WHEN rows IS NOT NULL;
    END LOOP;

    RETURN rows;
END
$func$;
"""

LOGGER = logging.getLogger(__name__)


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

        :returns: pygeoapi.provider.base.PostgreSQLProvider
        """
        LOGGER.debug('Initialising Pseudo-count PostgreSQL provider.')
        super().__init__(provider_def)

    def query(self, offset=0, limit=10, resulttype='results',
              bbox=[], datetime_=None, properties=[], sortby=[],
              select_properties=[], skip_geometry=False, q=None,
              filterq=None, crs_transform_spec=None, **kwargs):
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
        property_filters = self._get_property_filters(properties)
        cql_filters = self._get_cql_filters(filterq)
        bbox_filter = self._get_bbox_filter(bbox)
        time_filter = self._get_datetime_filter(datetime_)
        order_by_clauses = self._get_order_by_clauses(sortby, self.table_model)
        selected_properties = self._select_properties_clause(select_properties,
                                                             skip_geometry)

        LOGGER.debug('Querying PostGIS')
        # Execute query within self-closing database Session context
        with Session(self._engine) as session:
            results = (session.query(self.table_model)
                       .filter(property_filters)
                       .filter(cql_filters)
                       .filter(bbox_filter)
                       .filter(time_filter)
                       .options(selected_properties))

            try:
                if filterq:
                    raise ProviderQueryError('No Pseudo-count during CQL')
                elif resulttype == 'hits':
                    raise ProviderQueryError('No Pseudo-count during hits')

                matched = self._get_pseudo_count(results)

            except ProviderQueryError as err:
                LOGGER.warning(f'Warning during psuedo-count {err}')
                matched = results.count()

            except Exception as err:
                LOGGER.warning(f'Error during psuedo-count {err}')
                matched = results.count()

            LOGGER.debug(f'Found {matched} result(s)')

            LOGGER.debug('Preparing response')
            response = {
                'type': 'FeatureCollection',
                'features': [],
                'numberMatched': matched,
                'numberReturned': 0
            }

            if resulttype == "hits" or not results:
                return response

            crs_transform_out = self._get_crs_transform(crs_transform_spec)

            for item in results.order_by(*order_by_clauses).offset(offset).limit(limit):  # noqa
                response['numberReturned'] += 1
                response['features'].append(
                    self._sqlalchemy_to_feature(item, crs_transform_out)
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
        compiled = results.statement.compile(
            self._engine, compile_kwargs={"literal_binds": True})

        with Session(self._engine) as s:
            s.execute(COUNT_FUNCTION)
            compiled_query = select(text(f"count_estimate('{compiled}')"))
            matched = (s.execute(compiled_query)
                       .scalar())

        if matched < PSUEDO_COUNT_LIMIT:
            LOGGER.debug('Using precise count')
            matched = results.count()

        return matched

    def __repr__(self):
        return f'<PseudoPostgreSQLProvider> {self.table}'
