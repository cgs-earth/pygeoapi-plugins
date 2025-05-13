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

import io
import pytest
from requests import Session
import xml
import zipfile

from pygeoapi.util import url_join

PYGEOAPI_URL = 'http://localhost:5000'
PROCESS_URL = url_join(PYGEOAPI_URL, 'processes/sitemap-generator/execution')
HTTP = Session()


@pytest.fixture
def body():
    return {'inputs': {'include-common': True, 'include-features': False, 'zip': False}}


def test_sitemap_generator(body):
    body['inputs']['include-features'] = True
    r = HTTP.post(PROCESS_URL, json=body)
    assert r.status_code == 200

    sitemap = r.json()
    assert len(sitemap) == 5

    common = sitemap.pop('common.xml')
    assert len(common) == 3134

    root = xml.etree.ElementTree.fromstring(common)
    assert all(i.tag == j.tag for (i, j) in zip(root, root.findall('url')))

    assert all(f.endswith('__0.xml') for f in sitemap)


def test_sitemap_no_common(body):
    body['inputs']['include-common'] = False
    r = HTTP.post(PROCESS_URL, json=body)
    assert r.status_code == 200

    sitemap = r.json()
    assert len(sitemap) == 0


def test_sitemap_no_features(body):
    r = HTTP.post(PROCESS_URL, json=body)
    assert r.status_code == 200

    sitemap = r.json()
    assert len(sitemap) == 1

    common = sitemap.pop('common.xml')
    assert len(common) == 3134


def test_sitemap_zip(body):
    body['inputs']['zip'] = True
    r = HTTP.post(PROCESS_URL, json=body)
    assert r.status_code == 200

    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(z.namelist()) == 1
