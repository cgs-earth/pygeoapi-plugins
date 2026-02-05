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

import requests
import pytest
import contextlib
from pygeoapi.process.base import ProcessorExecuteError

import pygeoapi_plugins.process.intersect as intersect


@pytest.fixture
def process_def():
    return {
        "name": "Intersector",
        "data": "pygeoapi_plugins.process.intersect.IntersectionProcessor",
    }


@pytest.fixture
def bytes_data():
    return '{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-109, 37], [-102, 37], [-102, 41], [-109, 41], [-109, 37]]]}}'


def test_execute_raises_when_missing_collection(process_def, bytes_data):
    proc = intersect.IntersectionProcessor(process_def)
    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                "url": "http://geoconnex.us/ref/states/08",
            }
        )

    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                "file": bytes_data,
            }
        )

    with pytest.raises(ProcessorExecuteError):
        proc.execute(
            {
                "url": "http://geoconnex.us/ref/states/08",
                "file": bytes_data,
            }
        )


@pytest.mark.parametrize(
    "url,bounds,ctx",
    [
        (
            "http://geoconnex.us/ref/states/08",
            [-109.060253, 36.992426, -102.041524, 41.003443999999995],
            contextlib.nullcontext(),
        ),
        (
            "https://reference.geoconnex.us/collections/states/items",
            [-179.148909, -14.548699, 179.77847011250077, 71.365162],
            contextlib.nullcontext(),
        ),
        (
            "https://www.hydroshare.org/resource/3295a17b4cc24d34bd6a5c5aaf753c50/data/contents/hu02.gpkg",
            [-179.2294676, -14.42442,  179.8564841, 71.439451],
            contextlib.nullcontext(),
        ),
        (
            "https://github.com/geopython/pygeoapi/raw/refs/heads/master/tests/data/dutch_addresses_shape_28992.zip",
            [
                52.04308374228452,
                5.670269218772358,
                52.12327124702764,
                5.829358202203319,
            ],
            contextlib.nullcontext(),
        ),
        (
            "https://github.com/geopython/pygeoapi/raw/refs/heads/master/tests/data/coads_sst.nc",
            None,
            pytest.raises(Exception),
        ),  # Error case - non-vector
        ("https://example.com", None, pytest.raises(Exception)),  # Error case - bad URL
    ],
)
def test_get_bbox(process_def, url, bounds, ctx):
    proc = intersect.IntersectionProcessor(process_def)
    with ctx:
        _, bbox = proc.get_layer(url=url, as_bbox=True)
        assert pytest.approx(bbox) == bounds

    with ctx:
        content = requests.get(url).content
        _, bbox= proc.get_layer(file=content, as_bbox=True)
        assert pytest.approx(bbox) == bounds


@pytest.mark.parametrize(
    "url,hits,ctx",
    [
        (
            "http://geoconnex.us/ref/states/08",
            0,
            contextlib.nullcontext(),
        ),
        (
            "http://geoconnex.us/ref/states/36",
            2,
            contextlib.nullcontext(),
        ),
        (
            "https://reference.geoconnex.us/collections/states/items",
            3,
            contextlib.nullcontext(),
        ),
        (
            "https://www.hydroshare.org/resource/3295a17b4cc24d34bd6a5c5aaf753c50/data/contents/hu02.gpkg",
            5,
            contextlib.nullcontext(),
        ),
        (
            "https://github.com/geopython/pygeoapi/raw/refs/heads/master/tests/data/dutch_addresses_shape_28992.zip",
            0,
            contextlib.nullcontext(),
        ),
        (
            "https://github.com/geopython/pygeoapi/raw/refs/heads/master/tests/data/coads_sst.nc",
            None,
            pytest.raises(Exception),
        ),  # Error case - non-vector
        ("https://example.com", None, pytest.raises(Exception)),  # Error case - bad URL
    ],
)
def test_execute(process_def, url, hits, ctx):
    proc = intersect.IntersectionProcessor(process_def)

    with ctx:
        _, response = proc.execute({"url": url, "collection": "obs"})
        assert hits == response['numberReturned']

    with ctx:
        content = requests.get(url).content
        _, response = proc.execute({"file": content, "collection": "obs"})
        assert hits == response['numberReturned']
