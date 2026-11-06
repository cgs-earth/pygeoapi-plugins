# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
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

import contextlib
import functools
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests
from pygeoapi.process.base import ProcessorExecuteError

import pygeoapi_plugins.process.intersect as intersect

DATA = Path(__file__).parent / 'data'

# Test files, served from tests/data by a local web server
STATES_08 = 'intersect/states_08.geojson'  # geoconnex.us/ref/states/08
STATES_36 = 'intersect/states_36.geojson'  # geoconnex.us/ref/states/36
STATES = 'states.gpkg'
HU02 = 'hu02.gpkg'
DUTCH = 'intersect/dutch_addresses_shape_28992.zip'
LANDING = 'intersect/landing.json'  # JSON, but not GeoJSON
RASTER = 'intersect/raster.png'  # Not vector data
PAGE = 'intersect/page.html'  # Not geospatial
MISSING = 'intersect/missing.geojson'  # 404

STATES_36_BOUNDS = [-79.762152, 40.496103, -71.856214, 45.01585]


class _RangeHandler(SimpleHTTPRequestHandler):
    """Static files, with the byte ranges GDAL uses to read remote zips"""

    def do_GET(self):
        match = re.fullmatch(
            r'bytes=(\d*)-(\d*)', self.headers.get('Range', '')
        )
        path = Path(self.translate_path(self.path))
        if not match or not path.is_file():
            return super().do_GET()

        data = path.read_bytes()
        start, end = match.groups()
        if start:
            start, end = int(start), int(end or len(data) - 1)
        else:  # The last n bytes
            start, end = len(data) - int(end), len(data) - 1
        end = min(end, len(data) - 1)

        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        self.wfile.write(data[start : end + 1])

    def log_message(self, *args):
        pass


@pytest.fixture(scope='module')
def server():
    """Base URL of a local web server for tests/data"""
    handler = functools.partial(_RangeHandler, directory=str(DATA))
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    host, port = httpd.server_address[:2]
    yield f'http://{host}:{port}'

    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def process_def():
    return {
        'name': 'Intersector',
        'data': 'pygeoapi_plugins.process.intersect.IntersectionProcessor',
    }


@pytest.fixture
def bytes_data():
    return '{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-109, 37], [-102, 37], [-102, 41], [-109, 41], [-109, 37]]]}}'  # noqa


def test_execute_raises_when_missing_collection(process_def, bytes_data):
    proc = intersect.IntersectionProcessor(process_def)
    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                'url': 'http://geoconnex.us/ref/states/08',
            }
        )

    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                'file': bytes_data,
            }
        )

    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                'url': 'http://geoconnex.us/ref/states/08',
                'file': bytes_data,
            }
        )


@pytest.mark.parametrize(
    'path,bounds,ctx',
    [
        (
            STATES_08,
            [-109.060253, 36.992426, -102.041524, 41.003443999999995],
            contextlib.nullcontext(),
        ),
        (
            STATES,
            [-179.148909, -14.548699, 179.77847011250077, 71.365162],
            contextlib.nullcontext(),
        ),
        (
            HU02,
            [-179.2294676, -14.42442, 179.8564841, 71.439451],
            contextlib.nullcontext(),
        ),
        (
            DUTCH,
            [
                52.04308374228452,
                5.670269218772358,
                52.12327124702764,
                5.829358202203319,
            ],
            contextlib.nullcontext(),
        ),
        (RASTER, None, pytest.raises(ProcessorExecuteError)),
        (PAGE, None, pytest.raises(ProcessorExecuteError)),
        (MISSING, None, pytest.raises(ProcessorExecuteError)),
    ],
)
def test_get_bbox(process_def, server, path, bounds, ctx):
    url = f'{server}/{path}'
    proc = intersect.IntersectionProcessor(process_def)
    with ctx:
        _, bbox = proc.get_layer(url=url)
        assert pytest.approx(bbox) == bounds

    with ctx:
        content = requests.get(url).content
        _, bbox = proc.get_layer(file=content)
        assert pytest.approx(bbox) == bounds


@pytest.mark.parametrize(
    'path,bounds,ctx',
    [
        (
            STATES_08,
            [-109.060253, 36.992426, -102.041524, 41.003443999999995],
            contextlib.nullcontext(),
        ),
        (
            STATES_36,
            STATES_36_BOUNDS,
            contextlib.nullcontext(),
        ),
        (LANDING, None, pytest.raises(ProcessorExecuteError)),
    ],
)
def test_literal_geojson(process_def, server, path, bounds, ctx):
    proc = intersect.IntersectionProcessor(process_def)
    content = requests.get(f'{server}/{path}').json()
    with ctx:
        _, bbox = proc.get_layer(file=content)
        assert pytest.approx(bbox) == bounds


@pytest.mark.parametrize(
    'path,hits,ctx',
    [
        (STATES_08, 0, contextlib.nullcontext()),
        (STATES_36, 2, contextlib.nullcontext()),
        (STATES, 3, contextlib.nullcontext()),
        (HU02, 5, contextlib.nullcontext()),
        (DUTCH, 0, contextlib.nullcontext()),
        (RASTER, None, pytest.raises(Exception)),
        (PAGE, None, pytest.raises(Exception)),
    ],
)
def test_execute(process_def, server, path, hits, ctx):
    url = f'{server}/{path}'
    proc = intersect.IntersectionProcessor(process_def)

    with ctx:
        _, response = proc.execute({'url': url, 'collection': 'obs'})
        assert hits == response['numberReturned']

    with ctx:
        content = requests.get(url).content
        _, response = proc.execute({'file': content, 'collection': 'obs'})
        assert hits == response['numberReturned']
