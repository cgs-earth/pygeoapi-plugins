# =================================================================
#
# Authors: Ben Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2024 Ben Webb
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

from pygeoapi.provider.base import ProviderNoDataError
from pygeoapi.provider.base_edr import BaseEDRProvider
from pygeoapi.provider.sensorthings import SensorThingsProvider

LOGGER = logging.getLogger(__name__)


class SensorThingsEDRProvider(BaseEDRProvider, SensorThingsProvider):
    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi.provider.rasterio_.RasterioProvider
        """
        provider_def['entity'] = 'ObservedProperties'
        BaseEDRProvider.__init__(self, provider_def)
        SensorThingsProvider.__init__(self, provider_def)
        self.expand['ObservedProperties'] = 'Datastreams/Thing/Locations,Datastreams/Observations' # noqa
        self.time_field = 'Datastreams/Observations/resultTime'
        self._fields = {}
        self.get_fields()

    def get_fields(self):
        if not self._fields:
            r = self._get_response(self._url,
                                   entity='ObservedProperties',
                                   expand='Datastreams')
            try:
                _ = r['value'][0]
            except IndexError:
                LOGGER.warning('could not get fields; returning empty set')
                return {}

            for feature in r['value']:
                id = feature['@iot.id']
                key = feature['name']
                try:
                    UoM = feature['Datastreams'][0]['unitOfMeasurement']
                except IndexError:
                    continue

                self._fields[id] = {
                    'type': 'number',
                    'title': key,
                    'x-ogc-unit': UoM['symbol']
                }

        return self._fields

    @BaseEDRProvider.register(output_formats=['GeoJSON'])
    def items(self, **kwargs):
        pass

    @BaseEDRProvider.register(output_formats=['GeoJSON'])
    def locations(self, select_properties=[], bbox=[],
                  datetime_=None, location_id=None, **kwargs):
        """
        Extract data from collection collection

        :param datetime_: temporal (datestamp or extent)
        :param select_properties: list of parameters
        :param bbox: bbox geometry (for cube queries)
        :param location_id: location identifier

        :returns: GeoJSON FeatureCollection
        """

        fc = {
            'type': 'FeatureCollection',
            'features': []
        }

        params = {}
        filter = ''
        expand = [
            'Datastreams($select=description,name,unitOfMeasurement)',
            'Datastreams/Thing($select=@iot.id)',
            'Datastreams/Thing/Locations($select=location)'
        ]

        if location_id:
            return self.get(location_id)

        if select_properties:
            properties = [['@iot.id', f"'{p}'"] for p in select_properties]
            ret = [f'{name} eq {value}' for (name, value) in properties]
            params['$filter'] = ' or '.join(ret)

        filter = f'$filter={self._make_dtf(datetime_)};' if datetime_ else ''
        expand.append(f'Datastreams/Observations({filter}$select=result;$top=1)') # noqa

        if bbox:
            geom_filter = self._make_bbox(bbox, 'Datastreams')
            expand[0] = f'Datastreams($filter={geom_filter})'

        expand = ','.join(expand)
        response = self._get_response(url=self._url, params=params,
                                      entity='ObservedProperties',
                                      expand=expand)

        for property in response['value']:
            for datastream in property['Datastreams']:
                if len(datastream['Observations']) == 0:
                    continue

                fc['features'].append(
                    self._make_feature(
                        datastream['Thing'],
                        entity='Things'
                    )
                )

        if location_id:
            return fc['features'][0]
        else:
            return fc

    @BaseEDRProvider.register(output_formats=['CoverageJSON'])
    def cube(self, select_properties=[], bbox=[],
             datetime_=None, **kwargs):
        """
        Extract data from collection collection

        :param datetime_: temporal (datestamp or extent)
        :param select_properties: list of parameters
        :param bbox: bbox geometry (for cube queries)
        :param location_id: location identifier

        :returns: CovJSON CovCollection
        """

        cc = {
            'type': 'CoverageCollection',
            'domainType': 'PointSeries',
            'parameters': {},
            'coverages': []
        }

        params = {}

        geom_filter = self._make_bbox(bbox, 'Datastreams')
        expand = [
            f'Datastreams($filter={geom_filter};$select=description,name,unitOfMeasurement)', # noqa
            'Datastreams/Thing($select=@iot.id)',
            'Datastreams/Thing/Locations($select=location)',
        ]

        if select_properties:
            properties = [['@iot.id', f"'{p}'"] for p in select_properties]
            ret = [f'{name} eq {value}' for (name, value) in properties]
            params['$filter'] = ' or '.join(ret)

        filter = f'$filter={self._make_dtf(datetime_)};' if datetime_ else ''
        expand.append(f'Datastreams/Observations({filter}$orderby=phenomenonTime;$select=result,phenomenonTime,resultTime)') # noqa

        expand = ','.join(expand)
        response = self._get_response(url=self._url, params=params,
                                      entity='ObservedProperties',
                                      expand=expand)

        for feature in response['value']:
            try:
                _ = feature['Datastreams'][0]
                self._make_coverage_collection(feature, cc)
            except IndexError:
                continue
            
        if cc['parameters'] == {} or cc['coverages'] == []:
            msg = 'No data found'
            LOGGER.warning(msg)
            raise ProviderNoDataError(msg)

        return cc

    @BaseEDRProvider.register(output_formats=['CoverageJSON'])
    def area(self, wkt, select_properties=[],
             datetime_=None, **kwargs):
        """
        Extract data from collection collection

        :param wkt: `shapely.geometry` WKT geometry
        :param select_properties: list of parameters
        :param datetime_: temporal (datestamp or extent)
        :param location_id: location identifier

        :returns: CovJSON CovCollection
        """

        cc = {
            'type': 'CoverageCollection',
            'domainType': 'PointSeries',
            'parameters': {},
            'coverages': []
        }

        params = {}

        expand = [
            f"Datastreams($filter=st_within(Thing/Locations/location,geography'{wkt}');$select=description,name,unitOfMeasurement)", # noqa
            'Datastreams/Thing($select=@iot.id)',
            'Datastreams/Thing/Locations($select=location)',
        ]

        if select_properties:
            properties = [['@iot.id', f"'{p}'"] for p in select_properties]
            ret = [f'{name} eq {value}' for (name, value) in properties]
            params['$filter'] = ' or '.join(ret)

        filter = f'$filter={self._make_dtf(datetime_)};' if datetime_ else ''
        expand.append(f'Datastreams/Observations({filter}$orderby=phenomenonTime;$select=result,phenomenonTime,resultTime)') # noqa

        expand = ','.join(expand)
        response = self._get_response(url=self._url, params=params,
                                      entity='ObservedProperties',
                                      expand=expand)

        for feature in response['value']:
            try:
                _ = feature['Datastreams'][0]
                self._make_coverage_collection(feature, cc)
            except IndexError:
                continue
            
        if cc['parameters'] == {} or cc['coverages'] == []:
            msg = 'No data found'
            LOGGER.warning(msg)
            raise ProviderNoDataError(msg)

        return cc

    def _generate_coverage(self, datastream, id):
        times, values = \
            self._expand_observations(datastream)
        thing = datastream['Thing']
        coords = thing['Locations'][0]['location']['coordinates']
        length = len(values)

        return {
            'type': 'Coverage',
            'id': thing['@iot.id'],
            'domain': {
                'type': 'Domain',
                'domainType': 'PointSeries',
                'axes': {
                    'x': {'values': [coords[0]]},
                    'y': {'values': [coords[1]]},
                    't': {'values': times}
                },
                'referencing': [
                    {
                        'coordinates': ['x', 'y'],
                        'system': {
                            'type': 'GeographicCRS',
                            'id': 'http://www.opengis.net/def/crs/OGC/1.3/CRS84' # noqa
                        }
                    }, {
                        'coordinates': ['t'],
                        'system': {
                            'type': 'TemporalRS',
                            'calendar': 'Gregorian'
                        }
                    }
                ]
            },
            'ranges': {
                id: {
                    'type': 'NdArray',
                    'dataType': 'float',
                    'axisNames': ['t'],
                    'shape': [length],
                    'values': values
                }
            }
        }, length

    @staticmethod
    def _generate_paramters(datastream, label):
        return {
            'type': 'Parameter',
            'description': {'en': datastream['description']},
            'observedProperty': {
                'id': label,
                'label': {'en': label}
            },
            'unit': {
                'label': {'en': datastream['unitOfMeasurement']['name']},
                'symbol': datastream['unitOfMeasurement']['symbol']
            }
        }
    
    @staticmethod
    def _make_dtf(datetime_):
        dtf_r = []
        if '/' in datetime_:
            time_start, time_end = datetime_.split('/')
            if time_start != '..':
                dtf_r.append(f'phenomenonTime ge {time_start}')

            if time_end != '..':
                dtf_r.append(f'phenomenonTime le {time_end}')

        else:
            dtf_r.append(f'phenomenonTime eq {datetime_}')

        return ' and '.join(dtf_r)
    
    def _make_coverage_collection(self, feature, cc):

        id = feature['name'].replace(' ', '+')

        for datastream in feature['Datastreams']:
            coverage, length = self._generate_coverage(datastream, id)
            if length > 0:
                cc['coverages'].append(coverage)
                cc['parameters'][id] = \
                    self._generate_paramters(datastream,
                                                feature['name'])

        return cc

    @staticmethod
    def _expand_observations(datastream):
        times = []
        values = []
        # TODO: Expand observations when 'Observations@iot.nextLink'
        # or '@iot.nextLink' is present
        for obs in datastream['Observations']:
            resultTime = obs['resultTime'] or obs['phenomenonTime']
            if obs['result'] is not None and resultTime:
                try:
                    result = float(obs['result'])
                except ValueError:
                    result = obs['result']
                times.append(resultTime)
                values.append(result)

        return times, values
