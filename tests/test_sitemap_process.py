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

import importlib
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# The sitemap process reads the pygeoapi config when it is imported, so it
# is loaded with the config of the Docker pygeoapi instance it ships with
DOCKER_CONFIG = ROOT / 'docker' / 'pygeoapi.config.yml'
DOCKER_DATA = '/pygeoapi_plugins/'


@pytest.fixture(scope='module')
def sitemap_config(tmp_path_factory):
    """Docker pygeoapi config, with data paths pointing at this repo"""
    text = DOCKER_CONFIG.read_text(encoding='utf-8')
    config = yaml.safe_load(text.replace(DOCKER_DATA, f'{ROOT}/'))

    path = tmp_path_factory.mktemp('sitemap') / 'pygeoapi.config.yml'
    path.write_text(yaml.safe_dump(config), encoding='utf-8')
    return path


@pytest.fixture(scope='module')
def processor(sitemap_config):
    module = 'pygeoapi_plugins.process.sitemap'
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('PYGEOAPI_CONFIG', str(sitemap_config))
        sys.modules.pop(module, None)
        sitemap = importlib.import_module(module)

    yield sitemap.SitemapProcessor({'name': 'sitemap-generator'})

    # Drop the module so it is not reused with another config
    sys.modules.pop(module, None)


@pytest.fixture
def body():
    return {
        'include-common': True,
        'include-features': False,
        'zip': False,
    }


def test_sitemap_generator(processor, body):
    body['include-features'] = True
    mimetype, sitemap = processor.execute(body)
    assert mimetype == 'application/json'

    assert len(sitemap) == 4

    # Raw XML; over HTTP, pygeoapi escapes < and > in the JSON response
    common = sitemap.pop('common.xml')
    assert len(common) == 2548

    root = ET.fromstring(common)
    assert all(i.tag == j.tag for (i, j) in zip(root, root.findall('url')))

    assert set(sitemap) == {
        'places__0.xml',
        'populated__0.xml',
        'states__0.xml',
    }


def test_sitemap_no_common(processor, body):
    body['include-common'] = False
    mimetype, sitemap = processor.execute(body)
    assert mimetype == 'application/json'

    assert len(sitemap) == 0


def test_sitemap_no_features(processor, body):
    mimetype, sitemap = processor.execute(body)
    assert mimetype == 'application/json'

    assert len(sitemap) == 1

    common = sitemap.pop('common.xml')
    assert len(common) == 2548


def test_sitemap_zip(processor, body):
    body['zip'] = True
    mimetype, content = processor.execute(body)
    assert mimetype == 'application/zip'

    z = zipfile.ZipFile(io.BytesIO(content))
    assert len(z.namelist()) == 1
