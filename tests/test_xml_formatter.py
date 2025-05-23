# =================================================================
#
# Author: Benjamin Webb <bwebb@lincolninst.edu>
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

from datetime import datetime
import pytest
import xml.etree.ElementTree as ET

from pygeoapi.provider.csv_ import CSVProvider

from pygeoapi_plugins.formatter.xml import XMLFormatter


@pytest.fixture()
def config():
    return {
        'name': 'CSV',
        'type': 'feature',
        'data': 'tests/data/places.csv',
        'id_field': 'index',
        'uri_field': 'uri',
        'geometry': {'x_field': 'lon', 'y_field': 'lat'},
    }


def test_xml_formatter(config):
    p = CSVProvider(config)
    f = XMLFormatter(config)
    fc = p.query()
    f_xml = f.write(data=fc)

    assert f.mimetype == 'application/xml; charset=utf-8'

    root = ET.fromstring(f_xml)
    assert all(i.tag == j.tag for (i, j) in zip(root, root.findall('url')))

    node = root.find('url')
    assert node.find('loc').text == 'http://dbpedia.org/resource/Berlin'

    lastmod = node.find('lastmod').text
    strptime = datetime.strptime(lastmod, '%Y-%m-%dT%H:%M:%SZ')
    assert isinstance(strptime, datetime)

    now = datetime.now().strftime('%Y-%m-%dT%H:%M')
    assert now in lastmod
