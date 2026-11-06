# =================================================================
#
# Authors: Ben Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2026 Lincoln Institute of Land Policy
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


import pytest
from pygeoapi.provider.base import ProviderNotFoundError

from pygeoapi_plugins.provider.filesystem_xml import FileSystemXMLProvider

BASE_URL = 'http://localhost:5000/stac'

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>http://localhost:5000/stac/sitemap/places__0.xml</loc>
  </sitemap>
  <sitemap>
    <loc>http://localhost:5000/stac/sitemap/states__0.xml</loc>
  </sitemap>
</sitemapindex>
"""

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>http://dbpedia.org/resource/Berlin</loc>
    <lastmod>2026-01-01T00:00:00Z</lastmod>
  </url>
  <url>
    <loc>http://dbpedia.org/resource/Paris</loc>
    <lastmod>2026-01-01T00:00:00Z</lastmod>
  </url>
</urlset>
"""


@pytest.fixture()
def sitemap_dir(tmp_path):
    """
    sitemap/
        _sitemap.xml
        places__0.xml
        states__0.xml
        notes.txt       (not an XML file, so not listed)
        archive/
            old__0.xml
        tiles/          (always skipped)
    """
    root = tmp_path / 'sitemap'
    (root / 'archive').mkdir(parents=True)
    (root / 'tiles').mkdir()

    (root / '_sitemap.xml').write_text(SITEMAP_INDEX)
    (root / 'places__0.xml').write_text(URLSET)
    (root / 'states__0.xml').write_text(URLSET)
    (root / 'notes.txt').write_text('not a sitemap')
    (root / 'archive' / 'old__0.xml').write_text(URLSET)

    return root


@pytest.fixture()
def provider(sitemap_dir):
    return FileSystemXMLProvider(
        {
            'name': 'pygeoapi_plugins.provider.filesystem_xml.FileSystemXMLProvider',  # noqa
            'type': 'stac',
            'data': str(sitemap_dir),
            'file_types': ['.xml'],
        }
    )


def _links(content, rel):
    return [link for link in content['links'] if link['rel'] == rel]


def test_root_catalog(provider):
    content = provider.get_data_path(BASE_URL, 'sitemap', '')

    assert content['type'] == 'Catalog'

    [root_json, root_html] = _links(content, 'root')
    assert root_json['href'] == f'{BASE_URL}?f=json'
    assert root_html['href'] == BASE_URL

    [self_json, _] = _links(content, 'self')
    assert self_json['href'] == f'{BASE_URL}/sitemap?f=json'

    assert _links(content, 'parent') == []


def test_root_catalog_items(provider):
    content = provider.get_data_path(BASE_URL, 'sitemap', '')

    # The sitemap index is listed first, then the rest in name order
    items = _links(content, 'item')
    assert [item['title'] for item in items] == [
        '_sitemap.xml',
        'places__0.xml',
        'states__0.xml',
    ]

    sitemap = items[0]
    assert sitemap['href'] == f'{BASE_URL}/sitemap/_sitemap'
    assert sitemap['entry:type'] == 'Item'
    assert sitemap['file:size'] == len(SITEMAP_INDEX)
    assert sitemap['created']

    # Directories are child catalogs, except tiles
    [child] = _links(content, 'child')
    assert child['href'] == f'{BASE_URL}/sitemap/archive'
    assert child['entry:type'] == 'Catalog'


def test_sub_catalog(provider):
    content = provider.get_data_path(BASE_URL, 'sitemap/archive', '/archive')

    assert content['type'] == 'Catalog'

    [parent_json, parent_html] = _links(content, 'parent')
    assert parent_json['href'] == f'{BASE_URL}/sitemap?f=json'
    assert parent_html['href'] == f'{BASE_URL}/sitemap'

    [root_json, root_html] = _links(content, 'root')
    assert root_json['href'] == f'{BASE_URL}?f=json'
    assert root_html['href'] == BASE_URL

    [item] = _links(content, 'item')
    assert item['title'] == 'old__0.xml'
    assert item['href'] == f'{BASE_URL}/sitemap/archive/old__0'


def test_sitemap_index_item(provider):
    content = provider.get_data_path(BASE_URL, 'sitemap/_sitemap', '/_sitemap')

    assert content['type'] == 'Feature'
    assert content['id'] == '_sitemap'
    assert content['geometry'] is None

    links = content['properties']['links']
    assert links == [
        {
            'rel': 'child',
            'href': 'http://localhost:5000/stac/sitemap/places__0.xml',
            'title': 'places__0.xml',
            'type': 'application/ld+json',
        },
        {
            'rel': 'child',
            'href': 'http://localhost:5000/stac/sitemap/states__0.xml',
            'title': 'states__0.xml',
            'type': 'application/ld+json',
        },
    ]

    asset = content['assets']['default']
    assert asset['href'] == f'{BASE_URL}/sitemap/_sitemap.xml'
    assert asset['file:size'] == len(SITEMAP_INDEX)


def test_urlset_item(provider):
    content = provider.get_data_path(
        BASE_URL, 'sitemap/places__0', '/places__0'
    )

    # Only the <loc> URLs, not the lastmod dates
    hrefs = [link['href'] for link in content['properties']['links']]
    assert hrefs == [
        'http://dbpedia.org/resource/Berlin',
        'http://dbpedia.org/resource/Paris',
    ]


def test_other_xml_item(provider, sitemap_dir):
    # XML without <loc> elements lists each line of text
    (sitemap_dir / 'links.xml').write_text(
        '<links>\n<a>http://example.com/a</a>\n<a>http://example.com/b</a>\n'
        '</links>'
    )
    content = provider.get_data_path(BASE_URL, 'sitemap/links', '/links')

    hrefs = [link['href'] for link in content['properties']['links']]
    assert hrefs == ['http://example.com/a', 'http://example.com/b']


def test_item_parent(provider):
    content = provider.get_data_path(
        BASE_URL, 'sitemap/archive/old__0', '/archive/old__0'
    )

    [parent_json, _] = _links(content, 'parent')
    assert parent_json['href'] == f'{BASE_URL}/sitemap/archive?f=json'


def test_raw_file(provider):
    content = provider.get_data_path(
        BASE_URL, 'sitemap/_sitemap.xml', '/_sitemap.xml'
    )

    assert content == SITEMAP_INDEX.encode()


@pytest.mark.parametrize('dirpath', ['/missing', '/notes', '/archive/x'])
def test_not_found(provider, dirpath):
    with pytest.raises(ProviderNotFoundError):
        provider.get_data_path(BASE_URL, f'sitemap{dirpath}', dirpath)
