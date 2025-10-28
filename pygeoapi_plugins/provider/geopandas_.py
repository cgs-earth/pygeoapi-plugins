# =================================================================
#
# Authors: Colton Loftus
#
# Copyright (c) 2025 Colton Loftus
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

import datetime
import geopandas
import pandas
import shapely.geometry
import logging
from shapely import box
from collections import OrderedDict
from typing import Literal, Optional
from typing import TypedDict
from collections import defaultdict
from pygeoapi.provider.base import (
    BaseProvider,
    ProviderInvalidDataError,
    ProviderItemNotFoundError,
    ProviderNoDataError,
    ProviderQueryError,
)
from pygeoapi.crs import crs_transform

LOGGER = logging.getLogger(__name__)

# All types exposed by shapely
PossibleGeometries = (
    shapely.geometry.LineString
    | shapely.geometry.multilinestring.MultiLineString
    | shapely.geometry.multipoint.MultiPoint
    | shapely.geometry.multipolygon.MultiPolygon
    | shapely.geometry.point.Point
    | shapely.geometry.polygon.LinearRing
    | shapely.geometry.polygon.Polygon
)


class FeatureGeometry(TypedDict):
    coordinates: list[PossibleGeometries]
    type: str


# Non exhaustive


class FeatureProperties(TypedDict):
    # These are likely to be included but can be specified with other names
    # timestamp: Optional[str]
    # geometry: Optional[FeatureGeometry]
    pass


class Feature(TypedDict):
    type: Literal['Feature']
    # Optional if skipping geometry
    geometry: Optional[PossibleGeometries]
    properties: FeatureProperties
    id: str


class SortDict(TypedDict):
    property: str
    order: Literal['+', '-']


class FeatureCollection(TypedDict):
    type: Literal['FeatureCollection']
    features: list[Feature]
    numberMatched: int
    numberReturned: int


class GeoPandasProvider(BaseProvider):
    """GeoPandas provider"""

    gdf: geopandas.GeoDataFrame

    def _set_time_field(self, provider_def: dict):
        """
        Set time field and check if there is a specific "LOADDATE" column or not
        """
        if 'time_field' in provider_def:
            self.time_field = provider_def['time_field']
        # else look for a column named LOADDATE
        elif 'LOADDATE' in self.gdf.columns:
            self.time_field = 'LOADDATE'
        else:
            for col in self.gdf.columns:
                if isinstance(
                    self.gdf[col].iloc[0], (datetime.date, datetime.datetime)
                ):
                    self.time_field = col
                    break
            else:
                LOGGER.warning('No time field found')
                return

        self.gdf[self.time_field] = pandas.to_datetime(self.gdf[self.time_field])

    def _filter_by_date(
        self, df: geopandas.GeoDataFrame, datetime_: str
    ) -> geopandas.GeoDataFrame:
        """
        Filter by date
        """
        dateRange = datetime_.split('/')

        if _START_AND_END := len(dateRange) == 2:  # noqa F841
            start, end = dateRange

            # python does not accept Z at the end of the datetime even though that is a valid ISO 8601 datetime
            if start.endswith('Z'):
                start = start.replace('Z', '+00:00')

            if end.endswith('Z'):
                end = end.replace('Z', '+00:00')

            start = (
                datetime.datetime.min
                if start == '..'
                else datetime.datetime.fromisoformat(start)
            )
            end = (
                datetime.datetime.max
                if end == '..'
                else datetime.datetime.fromisoformat(end)
            )
            start, end = (
                start.replace(tzinfo=datetime.timezone.utc),
                end.replace(tzinfo=datetime.timezone.utc),
            )

            if start > end:
                raise ProviderQueryError(
                    'Start date must be before end date but got {} and {}'.format(
                        start, end
                    )
                )

            # If the user just passes in 2019/.. this still handles the match for all days in 2019
            # since the iso format will create the start as 2019-01-01
            return df[(df[self.time_field] >= start) & (df[self.time_field] <= end)]

        elif _ONLY_MATCH_ONE_DATE := len(dateRange) == 1:  # noqa
            dates: geopandas.GeoSeries = df[self.time_field]

            # By casting to a string we can use .str.contains to coarsely check.
            # We want 2019-10 to match 2019-10-01, 2019-10-02, etc.
            return df[dates.astype(str).str.startswith(datetime_)]
        else:
            raise ProviderQueryError(
                "datetime_ must be a date or date range with two dates separated by '/' but got {}".format(
                    datetime_
                )
            )

    def _set_geometry_fields(self, provider_def: dict):
        """
        Set geometry fields and check both if there is a point-based csv or a shapely geometry column
        """
        # Check if it was specified in the config, try the CSV geo style and otherwise use the standard shapely geo format
        if 'geometry' in provider_def:
            if (
                provider_def['geometry']['x_field']
                and provider_def['geometry']['y_field']
            ):
                self.geometry_x = provider_def['geometry']['x_field']
                self.geometry_y = provider_def['geometry']['y_field']
                self._exclude_from_fields.append(self.geometry_x)
                self._exclude_from_fields.append(self.geometry_y)

            # Unclear if there can be other types of geometries manually specified in the config
            # Otherwise we would just read it in as a shapely geometry\
            # else:
            #     self.geometry_col = provider_def["geometry"]
            #     self._exclude_from_fields.append(self.geometry_col)

        # If we don't have x,y coords as separate columns then look for a geometry column
        elif 'geometry' in self.gdf.columns:
            self.geometry_col = 'geometry'
            self._exclude_from_fields.append(self.geometry_col)

        # If we don't have any of the above, find the first geometry column and assume that is where the geometry is
        else:
            for col in self.gdf.columns:
                if hasattr(col, 'geom_type'):
                    self.geometry_col = col
                    self._exclude_from_fields.append(self.geometry_col)
                    break
            else:
                # Assuming that there is no reason to read in geometric data without geometry
                LOGGER.warning('No geometry column found')

    def __init__(self, provider_def: dict):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi.provider.base.GeoPandasProvider
        """

        super().__init__(provider_def)

        try:
            self.gdf = geopandas.read_file(provider_def['data'])
        except FileNotFoundError as ex:
            raise ProviderNoDataError(
                f'Tried to read GeoDataFrame: {ex} but it does not exist'
            )
        except Exception as ex:
            raise ProviderInvalidDataError(f'Failed to read GeoDataFrame: {ex}')

        # These fields should not be returned in the property list for a query
        self._exclude_from_fields: list[str] = []

        self._set_time_field(provider_def)
        self._set_geometry_fields(provider_def)

        self.gdf[self.id_field] = self.gdf[self.id_field].astype(str)

        # Without below, the CSV reads std_id as an object dtype
        # And fails the CSV provider tests. Maybe a way to do this better
        # that is more generalizable?
        if 'stn_id' in self.gdf.columns:
            self.gdf['stn_id'] = self.gdf['stn_id'].astype('int64')
        if 'value' in self.gdf.columns:
            self.gdf['value'] = self.gdf['value'].astype('float64')

        self._exclude_from_properties: list[str] = self._exclude_from_fields + [
            self.id_field
        ]

        self._fields = None  # Initialize _fields attribute before it is set

        self.fields = self.get_fields()  # Assign initial fields using get_fields()

    def get_fields(self) -> dict[str, any]:
        """
        Get provider field information (names, types)

        Example response: {'field1': 'string', 'field2': 'number'}}

        :returns: dict of field names and their associated JSON Schema types
        """
        if not self._fields:
            if len(self.gdf) == 0:
                raise ProviderNoDataError('No data found to get fields from')

            field_mapper = {
                col: self.gdf[col].dtype.name
                for col in self.gdf.columns
                if col not in self._exclude_from_fields
            }

            # Pandas has a different names for types than the OAF spec
            pandas_dtypes_to_ours = {
                'float64': 'number',
                'int64': 'integer',
                'object': 'string',
            }

            pandas_default = defaultdict(lambda: 'string')
            pandas_default.update(pandas_dtypes_to_ours)

            self._fields = {
                k: {'type': pandas_default[v]} for k, v in field_mapper.items()
            }

        return self._fields

    @property
    def fields(self) -> dict[str, any]:
        """Return the private _fields attribute if it exists, otherwise set it"""
        if hasattr(self, '_fields'):
            return self._fields
        else:
            return self.get_fields()

    @fields.setter
    def fields(self, fields_dict: dict[str, any]):
        """Set the fields attribute"""
        self._fields = fields_dict

    @crs_transform
    def query(
        self,
        offset=0,
        limit=10,
        resulttype: Literal['results', 'hits'] = 'results',
        identifier=None,
        bbox: list[float] = [],
        datetime_: Optional[str] = None,
        properties: list[tuple[str, str]] = [],
        select_properties=[],
        sortby: list[SortDict] = [],
        skip_geometry=False,
        q=None,
        **kwargs,
    ) -> FeatureCollection:
        """
        Query data with GeoPandas

        :param offset: starting record to return (default 0)
        :param limit: number of records to return (default 10)
        :param datetime_: temporal (datestamp or extent)
        :param identifier: feature id
        :param resulttype: return results or hit limit (default results)
        :param properties: Properties with specific values to select list of tuples (name, value)
        :param select_properties: list of general properties to select regardless of values
        :param sortby: How to return the sorted features list of dicts (property, order)
        :param skip_geometry: bool of whether to skip geometry (default False)
        :param q: full-text search term(s)

        :returns: dict of GeoJSON FeatureCollection
        """

        if q is not None:
            raise NotImplementedError('q not implemented for GeoPandasProvider')

        found, result = False, False
        feature_collection: FeatureCollection = {
            'type': 'FeatureCollection',
            'features': [],
            'numberMatched': 0,
            'numberReturned': 0,
        }

        if identifier is not None:
            # If we are querying for just one feature, we may have a different limit than the default
            # TODO should this be min? So min or this limit and limit in the function call?
            limit = self.query(resulttype='hits')['numberMatched']

        # Create a dummy backup that we can overwrite
        df: geopandas.GeoDataFrame = self.gdf

        if properties:
            for prop in properties:
                (column_name, val_to_filter_by) = prop

                # Only keep rows where the property is the right value

                # We need to convert this to a string since it appears the properties are always strings,
                # but our dataframe contains integers or floats
                df = df[df[column_name].astype(str) == val_to_filter_by]

        if resulttype == 'hits':
            # If we are querying for just the number matched, we don't
            # datetime_obj to further process the df and can simply return len
            feature_collection['numberMatched'] = len(df)
            return feature_collection

        if _BBOX_DEFINED := len(bbox) == 4:  # noqa
            minx, miny, maxx, maxy = bbox
            bbox_geom = box(minx, miny, maxx, maxy)
            df = df[df['geometry'].intersects(bbox_geom)]
        elif _INVALID_BBOX := (len(bbox) != 4 and len(bbox) != 0):  # noqa
            raise ProviderQueryError(
                'bbox must be a list of 4 values got {}'.format(len(bbox))
            )

        if sortby:
            sort_keys = [sort_key['property'] for sort_key in sortby]

            for sort_specifier in sortby:
                if '+' != sort_specifier['order'] and '-' != sort_specifier['order']:
                    raise ProviderQueryError(
                        'sortby order must be + or - got {}'.format(
                            sort_specifier['order']
                        )
                    )

            sort_directions = [
                True if sort_key['order'] == '+' else False for sort_key in sortby
            ]

            df = df.sort_values(by=sort_keys, ascending=sort_directions)

        if datetime_ is not None:
            df = self._filter_by_date(df, datetime_)

        for _, row in df.iterrows():
            feature: Feature = {
                'type': 'Feature',
                'id': str(row[self.id_field]),
                'properties': OrderedDict(),
                'geometry': {'type': None, 'coordinates': None},
            }

            if skip_geometry:
                feature['geometry'] = None
            else:
                if hasattr(self, 'geometry_x') and hasattr(self, 'geometry_y'):
                    feature['geometry']['coordinates'] = [
                        float(row[self.geometry_x]),
                        float(row[self.geometry_y]),
                    ]
                    feature['geometry']['type'] = 'Point'
                elif hasattr(self, 'geometry_col'):
                    feature['geometry']['coordinates'] = shapely.to_geojson(
                        row[self.geometry_col]
                    )
                    feature['geometry']['type'] = row[self.geometry_col].geom_type
                else:
                    raise ProviderQueryError(
                        'The config passed in does not specify which geometry column to use'
                    )

            for key, value in row.items():
                properties_to_keep = set(self.properties) | (set(select_properties))

                # If no properties are specified to filter by, we have a no-op filter
                KEEP_ALL = len(properties_to_keep) == 0

                if KEEP_ALL or key in properties_to_keep:
                    if key not in self._exclude_from_properties:
                        feature['properties'][key] = value

            if identifier and feature[self.id_field] == identifier:
                found = True
                result = feature

            feature_collection['features'].append(feature)
            feature_collection['numberMatched'] = len(feature_collection['features'])

        if identifier:
            return None if not found else result

        feature_collection['features'] = feature_collection['features'][
            offset : offset + limit
        ]
        feature_collection['numberReturned'] = len(feature_collection['features'])

        # After we have used the timestamps for querying we need to convert them back to strings
        for feature in feature_collection['features']:
            if self.time_field in feature['properties']:
                feature['properties'][self.time_field] = str(
                    feature['properties'][self.time_field]
                )

        return feature_collection

    @crs_transform
    def get(self, identifier: str, **kwargs):
        """
        query the provider by id

        :param identifier: feature id

        :returns: dict of single GeoJSON feature
        """
        #
        res: geopandas.GeoSeries = self.gdf[
            self.gdf[self.id_field].astype(str) == identifier
        ].squeeze(axis=0)
        if res.empty:
            err = f'item {identifier} not found'
            LOGGER.error(err)
            raise ProviderItemNotFoundError(err)

        feature: Feature = {}
        feature['type'] = 'Feature'
        feature['id'] = res[self.id_field]
        feature['properties'] = {k: v for k, v in res.items()}
        return feature

    def create(self, item):
        """
        Create a new item

        :param item: `dict` of new item

        :returns: identifier of created item
        """

        if len(item) != len(self.gdf.columns):
            raise ProviderQueryError('Item to update does not match dataframe shape')

        self.gdf = self.gdf._append(item, ignore_index=True)

        return self.gdf[self.id_field].iloc[-1]

    def update(self, identifier, item: dict[str, any]):
        """
        Updates an existing item

        :param identifier: feature id
        :param item: `dict` of partial or full item

        :returns: `bool` of update result
        """

        if len(self.gdf) == 0:
            raise ProviderNoDataError('No data in provider')

        if len(item) != len(self.gdf.columns):
            raise ProviderQueryError('Item to update does not match dataframe shape')

        if identifier not in self.gdf[self.id_field].values:
            return False

        # Find the index of the row that matches the identifier
        index = self.gdf[self.gdf[self.id_field] == identifier].index[0]

        # Update the row with the new item values
        for key, value in item.items():
            self.gdf.at[index, key] = value

        # Return True to indicate successful update
        return True

    def delete(self, identifier):
        """
        Deletes an existing item

        :param identifier: item id

        :returns: `bool` of deletion result
        """
        try:
            self.gdf = self.gdf[self.gdf[self.id_field] != identifier]
            return True
        except Exception as e:
            LOGGER.error(e)
            return False

    def __repr__(self):
        return f'<GeoPandasProvider> {self.type}'
