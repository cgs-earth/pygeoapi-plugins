# =================================================================
#
# Author: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2023 Center for Geospatial Solutions
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

from SPARQLWrapper import SPARQLWrapper, JSON

import json
import logging

from pygeoapi.plugin import load_plugin
from pygeoapi.provider.base import ProviderQueryError, ProviderNoDataError, BaseProvider
from pygeoapi.util import is_url


LOGGER = logging.getLogger(__name__)

_PREFIX = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX : <http://dbpedia.org/resource/>
PREFIX dbpedia2: <http://dbpedia.org/property/>
PREFIX dbpedia: <http://dbpedia.org/>
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

_SELECT = """
SELECT DISTINCT {select}
"""

_WHERE = """
WHERE {{
    VALUES ?{alias} {{ {value} }}
    {where}
    {filter}
}}
"""


class SPARQLProvider(BaseProvider):
    """SPARQL Wrapper API Provider"""

    prefix = _PREFIX

    def __init__(self, provider_def):
        """
        Class constructor

        :param provider_def: provider definitions from yml pygeoapi-config.
                             data, id_field, name set in parent class

        :returns: pygeoapi_plugins.provider.sparql.SPARQLProvider
        """
        super().__init__(provider_def)

        # Load Provider to class property
        _provider_def = provider_def.copy()
        _provider_def['name'] = _provider_def.pop('sparql_provider')
        self.p = load_plugin('provider', _provider_def)
        self._fields = {}
        self.get_fields()

        # Set SPARQL query parameters
        query = provider_def.get('sparql_query', {})
        self.convert = query.get('convert', True)
        self.sparql = SPARQLWrapper(query.get('endpoint'))
        self.sparql.setMethod('POST')
        self.sparql.setReturnFormat(JSON)

        select = query.get('select', '*')
        self.select = _SELECT.format(select=select)

        if query.get('prefixes'):
            prefix_parts = []
            for k, v in query.get('prefixes').items():
                prefix_parts.append(f'PREFIX {k}: {v}')
            self.prefix = ' '.join(prefix_parts)

        bind = query.get('bind')
        self.bind = bind.get('name')
        self.alias = bind.get('variable').lstrip('?')

        self.where = []
        for triple in query.get('where', []):
            if isinstance(triple, dict):
                self.where.append(triple)
            elif isinstance(triple, str):
                parts = triple.split()
                if len(parts) == 3:
                    keys = ('subject', 'predicate', 'object')
                    self.where.append(dict(zip(keys, parts)))
                else:
                    LOGGER.warning(f'Unable to add where filter for: {triple}')
            else:
                LOGGER.warning(f'Unable to add where filter for: {triple}')

        self.filter = ' '.join(query.get('filter', []))
        self.groupby = f'GROUP BY {query["groupby"]}' if query.get('groupby') else ''

    def get_fields(self):
        """
        Get fields of CKAN Provider

        :returns: dict of fields
        """
        if not self._fields:
            self._fields = self.p.get_fields()

        return self._fields

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
        **kwargs,
    ):
        """
        SPARQL query

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

        :returns: dict of GeoJSON FeatureCollection
        """
        content = self.p.query(
            offset,
            limit,
            resulttype,
            bbox,
            datetime_,
            properties,
            sortby,
            select_properties,
            skip_geometry,
            q,
            **kwargs,
        )

        # TODO: Determine if we want to run SPARQL on /items queries
        # v = []
        # for c in content['features']:
        #     subj, _ = self._clean_subj(c['properties'], self.bind)
        #     v.append(subj)

        # search = ' '.join(v)
        # values = self._sparql(search)

        # for item in content['features']:
        #     _, _subj = self._clean_subj(item['properties'], self.bind)

        #     item['properties'] = self._combine(item['properties'],
        #                                        values.get(_subj))

        return content

    def get(self, identifier, **kwargs):
        """
        Query by id

        :param identifier: feature id

        :returns: dict of single GeoJSON feature
        """
        feature = self.p.get(identifier)
        
        if not feature or 'properties' not in feature:
            LOGGER.warning(f'No properties found for identifier: {identifier}')
            return feature
        
        try:
            subj, _subj = self._clean_subj(feature['properties'], self.bind)
            LOGGER.debug(f'SPARQL for: {identifier}')
            values = self._sparql(subj)
            
            if values and _subj in values:
                feature['properties'] = self._combine(feature['properties'], values.get(_subj))
            else:
                LOGGER.debug(f'No SPARQL data found for: {_subj}')
        except (KeyError, AttributeError) as err:
            LOGGER.warning(f'Unable to add SPARQL context: {err}')

        return feature

    def _sparql(self, value):
        """
        Private function to request SPARQL context

        :param value: subject for SPARQL query

        :returns: dict of SPARQL feature data
        """
        LOGGER.debug('Requesting SPARQL data')
        
        # Build where clause more efficiently
        where_parts = []
        for q in self.where:
            subject = q.get('subject', f'?{self.alias}')
            predicate = q.get('predicate', '')
            object_ = q.get('object', '')
            where_parts.append(f'{subject} {predicate} {object_} .')
        
        where = ' '.join(where_parts)
        
        # Create query
        qs = self._makeQuery(value, where)
        
        # Send query and process results
        result = self._sendQuery(qs)

        return self._clean_result(result)

    def _clean_subj(self, properties, _subject):
        """
        Private function to clean SPARQL subject and return subject value

        :param properties: feature properties block
        :param _subject: subject field in properties block

        :returns: subject value for properties block & SPARQL
        """
        # Handle prefix more efficiently
        _pref = ''
        if ':' in _subject:
            _pref, _subject = _subject.split(':', 1)
        
        # Get the subject value
        if _subject not in properties:
            LOGGER.warning(f"Subject '{_subject}' not found in properties")
            return None, None
            
        _subj = properties[_subject]
        
        # Process URI efficiently
        if isinstance(_subj, str):
            if is_url(_subj):
                # If URI, encase in <>
                return f'<{_subj}>', _subj
            elif len(_subj) > 2 and _subj.startswith('<') and _subj.endswith('>') and is_url(_subj[1:-1]):
                # If already encased URI
                return _subj, _subj[1:-1]
            elif _pref:
                # Join with namespace
                _subj_clean = _subj.replace(' ', '_')
                subj = f'{_pref}:{_subj_clean}'
                
                # Handle DBpedia special case
                if _pref == ' ':
                    _subj = f'http://dbpedia.org/resource/{_subj_clean}'
                return subj, _subj
        
        # Default fallback
        return str(_subj), _subj

    def _clean_result(self, result):
        """
        Clean SPARQL JSON result ensuring list lengths are consistent

        :param result: `dict` representing a result row from the SPARQL query.

        :returns: `dict` where each key corresponds to a subject.
        """
        ret = {}

        # Iterate over each binding (result row) in the SPARQL result
        for v in result['results']['bindings']:
            # Pop subject from response body (this is already a property)
            _id = v.pop(self.alias, {}).get('value')

            # If this is a new subject, initialize its entry in the result dict
            if _id not in ret:
                ret[_id] = {k: [] for k in v.keys()}

            # Iterate over each property-value pair for this binding
            for k, v_ in v.items():
                # Ensure the property's entry is always a list
                if not isinstance(ret[_id][k], list):
                    ret[_id][k] = [ret[_id][k]]

                # If the current value is not already in the list, append it
                if v_ not in [item['value'] for item in ret[_id][k]]:
                    ret[_id][k].append(v_)
        return ret


    def _combine(self, properties, results):
        """
        Private function to add SPARQL context to feature properties.
        Processes all data in a single pass and correctly creates datasets.

        :param properties: `dict` of feature properties
        :param results: `dict` of SPARQL data of feature

        :returns: dict of feature properties with SPARQL data
        """
        if not results:
            return properties
            
        try:
            # Process all properties
            tmp_props = {}
            
            # First pass: extract and parse all values
            for k, v in results.items():
                values = v if isinstance(v, list) else list(v)
                
                # Parse all values in the list
                parsed_values = [
                    self.parse(item.get('value') if isinstance(item, dict) else item)
                    for item in values
                ]
                
                # Store parsed values (single value or list)
                tmp_props[k] = parsed_values[0] if len(parsed_values) == 1 else parsed_values
            
            # Second pass: check if we need to create datasets
            keys = list(tmp_props.keys())

            # Only create datasets if we have multiple keys
            if len(keys) > 1:
                # Check if all values are lists of the same length
                all_lists = all(isinstance(tmp_props[k], list) for k in keys)
                
                if all_lists:
                    # Get the length of each list
                    lengths = [len(tmp_props[k]) for k in keys]
                    
                    # Only proceed if all lists have the same length
                    if len(set(lengths)) == 1 and lengths[0] > 0:
                        # Create datasets
                        datasets = []
                        
                        for i in range(lengths[0]):
                            dataset = {}
                            for k in keys:
                                dataset[k] = tmp_props[k][i]
                            datasets.append(dataset)
                        
                        # Replace tmp_props with datasets
                        tmp_props = {'datasets': datasets}
            
            # Update properties with our processed data
            properties.update(tmp_props)
            
        except TypeError as err:
            LOGGER.error(f'Error processing SPARQL data: {err}')
            raise ProviderNoDataError(err)
            
        return properties


    def combine_lists(self, dict_data):
        """
        Combine lists from a dictionary into a list of dictionaries.
        This is a legacy method kept for compatibility, but functionality
        is now integrated into _combine.

        :param dict_data: `dict` where each key maps to a list of values.

        :returns: dict
        """
        # Extract keys from the dictionary
        keys = list(dict_data.keys())
        
        # Fast path for single key
        if len(keys) <= 1:
            LOGGER.debug('Returning unmodified data')
            return dict_data

        # Check if all values are lists
        all_lists = all(isinstance(dict_data[k], list) for k in keys)
        if not all_lists:
            LOGGER.debug('Not all values are lists, returning unmodified data')
            return dict_data
        
        # Check list lengths
        lengths = [len(dict_data[k]) for k in keys]
        if len(set(lengths)) != 1:
            LOGGER.debug('Lists have inconsistent lengths, returning unmodified data')
            return dict_data
        
        # Create datasets
        LOGGER.debug(f'Creating datasets for: {keys}')
        datasets = []
        
        for i in range(lengths[0]):
            dataset = {}
            for k in keys:
                dataset[k] = dict_data[k][i]
            datasets.append(dataset)
        
        return {'datasets': datasets}

    def _makeQuery(self, value, where):
        """
        Private function to make SPARQL querystring

        :param value: str, collection of SPARQL subjects
        :param where: str, collection of SPARQL predicates

        :returns: str, SPARQL query
        """
        # Build query more efficiently
        _where = _WHERE.format(
            alias=self.alias, 
            value=value, 
            where=where, 
            filter=self.filter
        )
        
        querystring = f"{self.prefix}\n{self.select}\n{_where}\n{self.groupby}"
        
        LOGGER.debug(f'SPARQL query: {querystring}')
        
        return querystring

    def _sendQuery(self, query):
        """
        Private function to send SPARQL query with error handling

        :param query: str, SPARQL query

        :returns: SPARQL query results
        """
        LOGGER.debug('Sending SPARQL query')
        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            LOGGER.debug('Received SPARQL results')
            return results
        except Exception as err:
            LOGGER.error(f'Error in SPARQL query: {err}')
            raise ProviderQueryError(f"SPARQL query failed: {err}")

    def get_data_path(self, baseurl, urlpath, dirpath):
        """
        Delegate to provider

        :returns: data path from provider
        """
        return self.p.get_data_path(baseurl, urlpath, dirpath)

    def get_metadata(self):
        """
        Delegate to provider
        
        :returns: metadata from provider
        """
        return self.p.get_metadata()

    def create(self, new_feature):
        """
        Delegate to provider
        
        :returns: feature from provider
        """
        return self.p.create(new_feature)  # Fixed typo: creat -> create

    def update(self, identifier, new_feature):
        """
        Delegate to provider
        
        :returns: feature from provider
        """
        return self.p.update(identifier, new_feature)

    def get_coverage_domainset(self):
        """
        Delegate to provider
        
        :returns: coverage domainset from provider
        """
        return self.p.get_coverage_domainset()

    def get_coverage_rangetype(self):
        """
        Delegate to provider
        
        :returns: coverage rangetype from provider
        """
        return self.p.get_coverage_rangetype()

    def delete(self, identifier):
        """
        Delegate to provider
        
        :returns: result from provider
        """
        return self.p.delete(identifier)

    def __repr__(self):
        """
        Return representation of provider
        
        :returns: string representation
        """
        return f'<SPARQLProvider> {self.data}'

    @staticmethod
    def parse(value):
        """
        Parse a string by splitting it on delimiters.

        :param value: Value to be parsed.

        :returns: A list of strings if delimiters are present,
                  otherwise the original value.
        """
        if not isinstance(value, str):
            return value
        
        try:
            return json.parse(value)
        except json.JSONDecodeError:
            pass
            
        if '|' in value:
            return value.strip('|').split('|')
        return value