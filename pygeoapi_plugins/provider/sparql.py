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

import logging

from pygeoapi.plugin import load_plugin
from pygeoapi.provider.base import (ProviderQueryError, ProviderNoDataError,
                                    BaseProvider)
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
        _provider_def = provider_def.copy()
        _provider_def['name'] = _provider_def.pop('sparql_provider')

        self.p = load_plugin('provider', _provider_def)

        query = provider_def.get('sparql_query', {})
        self.convert = query.get('convert', True)
        self.sparql_endpoint = query.get('endpoint')

        select = query.get('select', '*')
        self.select = _SELECT.format(select=select)

        if query.get('prefixes'):
            self.prefix = ' '.join([
                f'PREFIX {k}: {v}'
                for k, v in query.get('prefixes').items()
            ])

        bind = query.get('bind')
        self.bind = bind.get('name')
        self.alias = bind.get('variable').lstrip('?')

        self.where = query.get('where')

        self.filter = ' '.join(query.get('filter', []))
        self.groupby = f'GROUP BY {query["groupby"]}' if query.get('groupby') else ''

    def get_fields(self):
        if not self._fields:
            self._fields = self.p.get_fields()

            for prop in self.where:
                p = prop.get('object').lstrip('?')
                self._fields.update({p: {'type': 'string'}})

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

        :returns: dict of single GeoJSON fea
        """
        LOGGER.debug(f'SPARQL for: {identifier}')
        feature = self.p.get(identifier)

        subj, _subj = self._clean_subj(feature['properties'], self.bind)

        values = self._sparql(subj)
        feature['properties'] = self._combine(feature['properties'],
                                              values.get(_subj))

        return feature

    def _sparql(self, value):
        """
        Private function to request SPARQL context

        :param value: subject for SPARQL query

        :returns: dict of SPARQL feature data
        """
        LOGGER.debug('Requesting SPARQL data')

        where = ' '.join([
            '{s} {p} {o} .\n'.format(
                s=q.get('subject', f'?{self.alias}'),
                p=q.get('predicate'),
                o=q.get('object')
            ) for q in self.where
        ])

        qs = self._makeQuery(value, where, self.prefix,
                             self.select, self.filter)

        result = self._sendQuery(qs)

        return self._clean_result(result)

    def _clean_subj(self, properties, _subject):
        """
        Private function to clean SPARQL subject and return subject value

        :param properties: feature properties block
        :param _subject: subject field in properties block
        :param _subject: subject field in properties block

        :returns: subject value for properties block & SPARQL
        """
        if ':' in _subject:
            (_pref, _subject) = _subject.split(':')
        else:
            _pref = ''

        _subj = properties[_subject]
        if is_url(_subj):
            subj = f'<{_subj}>'
        elif is_url(_subj[1:-1]):
            subj = _subj
            _subj = subj[1:-1]
        elif _pref:
            __subj = _subj.replace(' ', '_')
            subj = f'{_pref}:{__subj}'
            if _pref == ' ':
                _subj = f'http://dbpedia.org/resource/{__subj}'

        return subj, _subj

    def _clean_result(self, result, ret={}):
        """
        Private function to clean SPARQL JSON result

        :param result: SPARQL response JSON
        :param ret: parsed return JSON

        :returns: dict of SPARQL feature results
        """

        for v in result['results']['bindings']:
            _id = v.pop(self.alias).get('value')

            if not ret.get(_id, ''):
                ret[_id] = v

            for _k, _v in v.items():
                if not isinstance(ret[_id][_k], list):
                    ret[_id][_k] = [
                        ret[_id][_k],
                    ]

                _ = [_['value'] == _v['value'] for _ in ret[_id][_k]]
                if True not in _:
                    ret[_id][_k].append(_v)

        return ret

    def _combine(self, properties, results):
        """
        Private function to add SPARQL context to feature properties.

        :param properties: dict of feature properties
        :param results: SPARQL data of feature

        :returns: dict of feature properties with SPARQL data
        """
        def parse(value):
            return value.split(',') if ',' in value else value

        def combine_lists(dict_data):
            LOGGER.error(dict_data)
            keys = list(dict_data.keys())
            
            # Ensure both lists have the same length
            if len(dict_data[keys[0]]) != len(dict_data[keys[1]]):
                return dict_data
            
            # Combine the items into a list of dictionaries
            combined_list = [
                {keys[0]: dict_data[keys[0]][i], keys[1]: dict_data[keys[1]][i]}
                for i in range(len(dict_data[keys[0]]))
            ]
            return {'datasets': combined_list}

        try:
            
            # Create a new dictionary for the updated properties
            tmp_props = {}

            # Iterate over the results and process them
            for k, v in results.items():
                values = [
                    parse(item.get('value') if isinstance(item, dict) else item)
                    for item in (v if isinstance(v, list) else [v])
                ]
                tmp_props[k] = values[-1] if len(values) == 1 else values

            properties.update(combine_lists(tmp_props))

        except TypeError as err:
            LOGGER.error(f'Error processing SPARQL data: {err}')
            raise ProviderNoDataError(err)

        return properties


    def _makeQuery(self, value, where, prefix=_PREFIX,
                   select=_SELECT, filter=''):
        """
        Private function to make SPARQL querystring

        :param value: str, collection of SPARQL subjects
        :param where: str, collection of SPARQL predicates
        :param prefix: str, Optional SPARQL prefixes (Default = _PREFIX)
        :param select: str, Optional SPARQL select
        :param filter: str, Optional SPARQL filter

        :returns: str, SPARQL query
        """

        _where = _WHERE.format(
            alias=self.alias, value=value, where=where, filter=filter)
        querystring = ''.join([prefix, select, _where, self.groupby])

        LOGGER.debug(f'SPARQL query: {querystring}')

        return querystring

    def _sendQuery(self, query):
        """
        Private function to send SPARQL query

        :param query: str, SPARQL query

        :returns: SPARQL query results
        """
        LOGGER.debug('Sending SPARQL query')
        sparql = SPARQLWrapper(self.sparql_endpoint)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)

        try:
            results = sparql.query().convert()
            LOGGER.debug('Received SPARQL results')
        except Exception as err:
            LOGGER.error(f'Error in SPARQL query: {err}')
            raise ProviderQueryError(err)

        return results

    def get_data_path(self, baseurl, urlpath, dirpath):
        return self.p.get_data_path(baseurl, urlpath, dirpath)

    def get_metadata(self):
        return self.p.get_metadata()

    def create(self, new_feature):
        return self.p.creat(new_feature)

    def update(self, identifier, new_feature):
        return self.p.update(identifier, new_feature)

    def get_coverage_domainset(self):
        return self.p.get_coverage_domainset()

    def get_coverage_rangetype(self):
        return self.p.get_coverage_rangetype()

    def delete(self, identifier):
        return self.p.delete(identifier)

    def __repr__(self):
        return f'<SPARQLProvider> {self.data}'
