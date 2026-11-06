# =================================================================
#
# Authors: Ben Webb <bwebb@lincolninst.edu>
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
import logging
import os
import xml.etree.ElementTree as ET

from pygeoapi.provider.base import ProviderNotFoundError
from pygeoapi.provider.filesystem import FileSystemProvider
from pygeoapi.util import file_modified_iso8601, get_path_basename

LOGGER = logging.getLogger(__name__)


class FileSystemXMLProvider(FileSystemProvider):
    """filesystem Provider with XML"""

    def get_data_path(self, baseurl, urlpath, dirpath):
        """
        Gets directory listing or file description or raw file dump

        :param baseurl: base URL of endpoint
        :param urlpath: base path of URL
        :param dirpath: directory basepath (equivalent of URL)

        :returns: `dict` of file listing or `dict` of GeoJSON item or raw file
        """

        thispath = os.path.join(baseurl, urlpath)

        resource_type = None
        child_links = []

        data_path = os.path.join(self.data, dirpath)
        data_path = self.data + dirpath

        # Links to the STAC root, and to the catalog one level up
        root_link = baseurl
        if '/' in dirpath:
            parentpath = thispath.rstrip('/').rsplit('/', 1)[0]
            child_links.append(
                {
                    'rel': 'parent',
                    'href': f'{parentpath}?f=json',
                    'type': 'application/json',
                }
            )
            child_links.append(
                {'rel': 'parent', 'href': parentpath, 'type': 'text/html'}
            )

        content = {
            'links': [
                {
                    'rel': 'root',
                    'href': f'{root_link}?f=json',
                    'type': 'application/json',
                },
                {'rel': 'root', 'href': root_link, 'type': 'text/html'},
                {
                    'rel': 'self',
                    'href': f'{thispath}?f=json',
                    'type': 'application/json',
                },
                {'rel': 'self', 'href': thispath, 'type': 'text/html'},
            ]
        }

        LOGGER.debug('Checking if path exists as raw file or directory')
        if data_path.endswith(tuple(self.file_types)):
            resource_type = 'raw_file'
        elif os.path.exists(data_path):
            resource_type = 'directory'
        else:
            LOGGER.debug('Checking if path exists as file via file_types')
            for ft in self.file_types:
                tmp_path = f'{data_path}{ft}'
                if os.path.exists(tmp_path):
                    resource_type = 'file'
                    data_path = tmp_path
                    break

        if resource_type is None:
            msg = f'Resource does not exist: {data_path}'
            LOGGER.error(msg)
            raise ProviderNotFoundError(msg)

        if resource_type == 'raw_file':
            with io.open(data_path, 'rb') as fh:
                return fh.read()

        elif resource_type == 'directory':
            content['type'] = 'Catalog'
            dirpath2 = os.listdir(data_path)
            dirpath2.sort()
            try:
                idx = dirpath2.index('_sitemap.xml')
                dirpath2.insert(0, dirpath2.pop(idx))
            except ValueError:
                LOGGER.debug('sitemap.xml not in dir')
            for dc in dirpath2:
                # TODO: handle a generic directory for tiles
                if dc == 'tiles':
                    continue

                fullpath = os.path.join(data_path, dc)
                filectime = file_modified_iso8601(fullpath)
                filesize = os.path.getsize(fullpath)

                if os.path.isdir(fullpath):
                    newpath = os.path.join(baseurl, urlpath, dc)
                    child_links.append(
                        {
                            'rel': 'child',
                            'href': newpath,
                            'type': 'text/html',
                            'created': filectime,
                            'entry:type': 'Catalog',
                        }
                    )
                elif os.path.isfile(fullpath):
                    basename, extension = os.path.splitext(dc)
                    newpath = os.path.join(baseurl, urlpath, basename)
                    newpath2 = f'{newpath}{extension}'
                    if extension in self.file_types:
                        fullpath = os.path.join(data_path, dc)
                        child_links.append(
                            {
                                'rel': 'item',
                                'href': newpath,
                                'title': get_path_basename(newpath2),
                                'created': filectime,
                                'file:size': filesize,
                                'entry:type': 'Item',
                            }
                        )

        elif resource_type == 'file':
            filename = os.path.basename(data_path)

            id_ = os.path.splitext(filename)[0]
            if urlpath:
                filename = filename.replace(id_, '')
            url = f'{baseurl}/{urlpath}{filename}'

            filectime = file_modified_iso8601(data_path)
            filesize = os.path.getsize(data_path)

            content = {
                'id': id_,
                'type': 'Feature',
                'properties': {},
                'links': [],
                'assets': {},
            }

            content.update(_describe_file(data_path))

            content['assets']['default'] = {
                'href': url,
                'created': filectime,
                'file:size': filesize,
            }

        content['links'].extend(child_links)

        return content

    def __repr__(self):
        return f'<FileSystemXMLProvider> {self.data}'


def _describe_file(filepath):
    """
    Helper function to describe a geospatial data
    First checks if a sidecar mcf file is available, if so uses that
    if not, script will parse the file to retrieve some info from the file

    :param filepath: path to file

    :returns: `dict` of GeoJSON item
    """

    content = {'bbox': None, 'geometry': None, 'properties': {}}

    LOGGER.debug('Could not detect raster or vector data')
    root = ET.parse(filepath).getroot()
    content['properties']['links'] = []
    links = content['properties']['links']

    # Sitemaps list their URLs in <loc> elements
    hrefs = [
        el.text.strip()
        for el in root.iter()
        if el.tag.rsplit('}', 1)[-1] == 'loc' and el.text and el.text.strip()
    ]
    if not hrefs:
        # Other XML: every line of text
        text = ''.join(root.itertext())
        hrefs = [line.strip() for line in text.split('\n') if line.strip()]

    for href in hrefs:
        title = href.split('/')[-1]

        links.append(
            {
                'rel': 'child',
                'href': href,
                'title': title,
                'type': 'application/ld+json',
            }
        )

    return content
